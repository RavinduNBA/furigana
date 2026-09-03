import json
import pytest
from pathlib import Path
from furiganalyse.llm_provider import (
    get_llm_provider,
    resolve_provider_api_key,
    _resolve_alibaba_credentials,
    OpenAICompatibleProvider,
    ResilientFallbackProvider,
    MockLLMProvider,
    LLMRequest,
    LLMMessage,
    LLMProviderError,
    log_llm_debug,
)
from furiganalyse.proper_noun_resolver import (
    collect_unresolved_proper_nouns,
    resolve_proper_nouns,
)
from furiganalyse.contextual_gloss import enrich_glosses


def test_alibaba_credentials_discovery():
    key, url = _resolve_alibaba_credentials()
    assert key is not None and key.startswith("sk-ws-")
    assert url is not None and "aliyuncs.com" in url

    prov = get_llm_provider("alibaba")
    assert isinstance(prov, OpenAICompatibleProvider)
    assert prov.default_model == "qwen-plus-character"
    assert "aliyuncs.com" in prov.base_url

    prov_flash = get_llm_provider("alibaba", model="qwen-flash-character")
    assert prov_flash.default_model == "qwen-flash-character"


def test_resilient_fallback_provider_flow():
    class FailingProvider(MockLLMProvider):
        def generate(self, req, stream_callback=None):
            raise LLMProviderError("LLM API HTTP 429 from primary (qwen-plus): rate limit reached")

    primary = FailingProvider()
    fallback = MockLLMProvider(default_response={"status": "ok", "source": "fallback"})

    captured_logs = []

    def on_progress(event):
        if "log" in event:
            captured_logs.append(event["log"])

    resilient = ResilientFallbackProvider(
        primary_provider=primary,
        primary_name="primary_ali",
        fallback_providers=[(fallback, "fallback_google", "gemini-flash-latest")],
        progress_callback=on_progress,
    )

    resp = resilient.generate(LLMRequest(messages=[LLMMessage(role="user", content="ping")]))
    data = json.loads(resp.content)
    assert data.get("source") == "fallback"
    assert any("rate limit reached" in msg for msg in captured_logs)
    assert any("attempting service 'fallback_google'" in msg for msg in captured_logs)
    assert any("Fallback to service 'fallback_google' (gemini-flash-latest) succeeded!" in msg for msg in captured_logs)


def test_llm_debug_logger_writes_file(tmp_path):
    log_file = tmp_path / "test_debug.log"
    req = LLMRequest(messages=[
        LLMMessage(role="system", content="You are a helper."),
        LLMMessage(role="user", content="Secret prompt text for testing.")
    ])
    log_llm_debug(
        provider_name="test_provider",
        model="test-model-1",
        request=req,
        error="HTTP 429: quota exhausted",
        extra_path=log_file,
    )

    assert log_file.is_file()
    content = log_file.read_text(encoding="utf-8")
    assert "PROVIDER: test_provider" in content
    assert "Secret prompt text for testing." in content
    assert "HTTP 429: quota exhausted" in content


def test_series_memory_zero_redundancy_proper_nouns():
    # Setup series profile with known characters and ruby overrides
    series_profile = {
        "characters": {
            "司波達也": {"reading": "しばたつや", "romanized": "Shiba Tatsuya", "role": "protagonist"},
            "深雪": {"reading": "みゆき", "romanized": "Miyuki", "role": "heroine"},
        },
        "ruby_overrides": {
            "魔法科高校": "まほうかこうこう",
        },
        "glossary": {},
    }

    candidates = [
        {"surface": "司波達也", "context_sentences": ["司波達也は静かに言った。"]},
        {"surface": "深雪", "context_sentences": ["深雪が微笑んだ。"]},
        {"surface": "魔法科高校", "context_sentences": ["魔法科高校に入学する。"]},
    ]

    # Use a mock provider that raises an exception if called, to prove ZERO LLM calls occur
    class StrictNoCallProvider(MockLLMProvider):
        def generate(self, req, stream_callback=None):
            raise AssertionError("LLM should NOT be called for words already in Series Memory!")

    provider = StrictNoCallProvider()
    logs = []
    overrides = resolve_proper_nouns(
        candidates,
        provider,
        series_profile=series_profile,
        progress_callback=lambda evt: logs.append(evt.get("log", "")),
    )

    assert "司波達也" in overrides
    assert overrides["司波達也"]["reading"] == "しばたつや"
    assert overrides["司波達也"]["romanized"] == "Shiba Tatsuya"
    assert "深雪" in overrides
    assert overrides["深雪"]["reading"] == "みゆき"
    assert "魔法科高校" in overrides
    assert overrides["魔法科高校"]["reading"] == "まほうかこうこう"
    assert any("zero LLM calls needed" in l for l in logs)


def test_series_memory_zero_redundancy_contextual_gloss():
    series_profile = {
        "glossary": {
            "CAD": {
                "preferred_translation": "Casting Assistant Device",
                "notes": "magic tool",
            },
            "想子": {
                "preferred_translation": "Psions",
                "definition": "non-physical particles used for magic",
            },
        }
    }

    candidates = [
        {"id": "study-1", "surface": "CAD", "reading": "キャド", "context_sentences": ["CADを取り出す。"]},
        {"id": "study-2", "surface": "想子", "reading": "そうし", "context_sentences": ["想子波を感知する。"]},
    ]

    class StrictNoCallProvider(MockLLMProvider):
        def generate(self, req, stream_callback=None):
            raise AssertionError("LLM should NOT be called for terms already in Series Memory glossary!")

    provider = StrictNoCallProvider()
    logs = []
    glosses = enrich_glosses(
        candidates,
        provider,
        series_profile=series_profile,
        progress_callback=lambda evt: logs.append(evt.get("log", "")),
    )

    assert glosses["study-1"]["gloss"] == "Casting Assistant Device"
    assert glosses["study-2"]["gloss"] == "Psions"
    assert any("zero LLM calls needed" in l for l in logs)


def test_local_context_backup_created(tmp_path):
    cache_dir = tmp_path / "test_cache"
    cache_dir.mkdir()

    # When candidates have unresolved words, context backup is saved to disk
    candidates = [
        {"id": "study-new", "surface": "新用語", "reading": "しんようご", "context_sentences": ["新しい用語の例文。"]},
    ]

    mock_provider = MockLLMProvider(default_response=[
        {"id": "study-new", "gloss": "New Terminology", "selected_sense_id": "sense-1"}
    ])

    enrich_glosses(candidates, mock_provider, cache_dir=cache_dir)

    backup_dir = cache_dir / "context_backups"
    assert backup_dir.is_dir()
    files = list(backup_dir.glob("module3_batch_*.json"))
    assert len(files) >= 1
    ctx_data = json.loads(files[0].read_text(encoding="utf-8"))
    assert ctx_data.get("module") == "module_3_contextual_glosses"
    assert ctx_data.get("status") == "completed"
