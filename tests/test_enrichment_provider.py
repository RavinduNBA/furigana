import copy
import json
from pathlib import Path

import pytest

from furiganalyse.enrichment import enrich_requests, serialize
from furiganalyse.enrichment_provider import (
    OpenAICompatibleProvider,
    OpenAISDKTransport,
    ProviderConfigurationError,
    build_prompt_report,
    render_prompt,
)

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


@pytest.fixture
def requests():
    return load("artifacts/phase5/run-a/requests.json")


class FakeTransport:
    def __init__(self, responses=None, error=None):
        self.responses = responses or {}
        self.error = error
        self.calls = []

    def create(self, payload, api_key, timeout):
        self.calls.append((payload, api_key, timeout))
        if self.error:
            raise self.error
        request_id = json.loads(payload["input"])["study_item"]["request_id"]
        return self.responses[request_id]


def provider(transport):
    return OpenAICompatibleProvider(
        model_id="fake-enrichment-v1",
        api_key="unit-test-credential",
        transport=transport,
    )


def one(requests, index=0):
    return {
        "schema_version": 1,
        "book_id": requests["book_id"],
        "requests": [requests["requests"][index]],
    }


def test_prompts_are_deterministic_bounded_and_match_golden(requests):
    report = build_prompt_report(requests)
    assert serialize(report) == serialize(build_prompt_report(copy.deepcopy(requests)))
    assert serialize(report) == (ROOT / "tests/phase5_golden/prompts-v1.json").read_text()
    assert len(report["prompts"]) == 5
    for prompt, request in zip(report["prompts"], requests["requests"]):
        content = prompt["content"]
        assert prompt["prompt_hash"] == render_prompt(request)["prompt_hash"]
        assert content["context"] == request["context"]
        assert len(content["context"]) <= 3
        assert "dictionary_only_meaning" not in serialize(prompt)


def test_fake_provider_payload_success_and_cache_hit(requests, tmp_path):
    responses = load("tests/fixtures/phase5-openai-responses-v1.json")
    transport = FakeTransport(responses)
    adapter = provider(transport)
    first = enrich_requests(one(requests), adapter, tmp_path)
    assert first["results"][0]["source"] == "model"
    payload, credential, timeout = transport.calls[0]
    assert credential == "unit-test-credential" and timeout == 20
    assert payload["temperature"] == 0 and payload["max_output_tokens"] == 300
    assert payload["response_format"]["strict"] is True
    second = enrich_requests(one(requests), adapter, tmp_path)
    assert second["results"][0]["source"] == "cache" and len(transport.calls) == 1


@pytest.mark.parametrize(
    "value",
    [
        TimeoutError("secret timeout details"),
        PermissionError("authentication secret"),
        ConnectionError("rate limited at private endpoint"),
        RuntimeError("transport leaked credential"),
    ],
)
def test_transport_failures_fall_back_without_leaking(requests, tmp_path, value):
    report = enrich_requests(one(requests), provider(FakeTransport(error=value)), tmp_path)
    assert report["results"][0]["source"] == "dictionary"
    assert report["diagnostics"][0]["reason"] == type(value).__name__
    assert "secret" not in serialize(report) and "private endpoint" not in serialize(report)
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda _: "not-json",
        lambda _: {"refusal": "no"},
        lambda r: {**r, "selected_entry_id": "unknown"},
        lambda r: {**r, "unsupported": True},
        lambda r: {**r, "display_meaning": "x" * 121},
    ],
)
def test_invalid_outputs_fall_back_and_are_not_cached(requests, tmp_path, mutate):
    response = load("tests/fixtures/phase5-openai-responses-v1.json")[
        "enrichment-request-0001"
    ]
    transport = FakeTransport({"enrichment-request-0001": mutate(response)})
    report = enrich_requests(one(requests), provider(transport), tmp_path)
    assert report["results"][0]["source"] == "dictionary"
    assert report["diagnostics"] and not list(tmp_path.glob("*.json"))


def test_configuration_rejects_absent_credentials_and_invalid_limits():
    with pytest.raises(ProviderConfigurationError, match="credentials"):
        OpenAICompatibleProvider(model_id="model", api_key="", transport=FakeTransport())
    with pytest.raises(ProviderConfigurationError, match="model"):
        OpenAICompatibleProvider(model_id="", api_key="key", transport=FakeTransport())
    with pytest.raises(ProviderConfigurationError, match="timeout"):
        OpenAICompatibleProvider(
            model_id="model", api_key="key", transport=FakeTransport(), timeout_seconds=0
        )


def test_missing_optional_sdk_falls_back(monkeypatch, requests, tmp_path):
    def missing(_):
        raise ImportError("not installed")

    monkeypatch.setattr("furiganalyse.enrichment_provider.importlib.import_module", missing)
    adapter = provider(OpenAISDKTransport())
    report = enrich_requests(one(requests), adapter, tmp_path)
    assert report["results"][0]["source"] == "dictionary"
    assert report["diagnostics"][0]["reason"] == "ProviderConfigurationError"
    assert not list(tmp_path.glob("*.json"))


def test_prompt_and_artifacts_exclude_credentials_and_paths(requests, tmp_path):
    responses = load("tests/fixtures/phase5-openai-responses-v1.json")
    report = enrich_requests(requests, provider(FakeTransport(responses)), tmp_path)
    combined = serialize(build_prompt_report(requests)) + serialize(report)
    combined += "".join(path.read_text() for path in tmp_path.glob("*.json"))
    assert "unit-test-credential" not in combined
    assert "/home/" not in combined and "API_KEY" not in combined
