import os
from pathlib import Path
import tempfile
import pytest
from furiganalyse.llm_provider import get_llm_provider, resolve_provider_api_key, OpenAICompatibleProvider, MockLLMProvider


def test_resolve_provider_api_key_explicit():
    assert resolve_provider_api_key("google", "my-custom-key") == "my-custom-key"
    assert resolve_provider_api_key("openrouter", "sk-custom") == "sk-custom"


def test_resolve_provider_api_key_files(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        g_file = Path(tmpdir) / "googleaistidioapi.txt"
        g_file.write_text("test-google-key-1234\n", encoding="utf-8")
        
        or_file = Path(tmpdir) / "openrouterapi.txt"
        or_file.write_text("test-openrouter-key-5678\n", encoding="utf-8")

        monkeypatch.setattr("furiganalyse.llm_provider.Path", lambda p: Path(tmpdir) / Path(p).name if Path(p).name in {"googleaistidioapi.txt", "openrouterapi.txt"} else Path(p))

        # Test Google
        key_g = resolve_provider_api_key("google")
        assert key_g == "test-google-key-1234"

        # Test OpenRouter
        key_or = resolve_provider_api_key("openrouter")
        assert key_or == "test-openrouter-key-5678"


def test_get_llm_provider_google():
    prov = get_llm_provider("google", api_key="dummy-key")
    assert isinstance(prov, OpenAICompatibleProvider)
    assert prov.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert prov.default_model == "gemini-flash-latest"
    assert prov.api_key == "dummy-key"


def test_get_llm_provider_openrouter():
    prov = get_llm_provider("openrouter", api_key="dummy-key")
    assert isinstance(prov, OpenAICompatibleProvider)
    assert prov.base_url == "https://openrouter.ai/api/v1"
    assert prov.default_model == "nvidia/nemotron-3.5-lightning:free"
    assert prov.api_key == "dummy-key"
