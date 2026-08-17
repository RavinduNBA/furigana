import copy
import json
from pathlib import Path
import pytest
from furiganalyse.enrichment import (
    EnrichmentError,
    ScriptedProvider,
    build_enrichment_requests,
    cache_key,
    enrich_requests,
    serialize,
    validate_request_report,
    validate_response,
)

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text())


@pytest.fixture
def requests():
    return build_enrichment_requests(
        load("artifacts/phase2/run-a/book.json"),
        load("artifacts/phase3/jmnedict/run-a/vocabulary.json"),
        load("artifacts/phase4/run-a/annotation-plan.json"),
    )


def response(q, provider, meaning="context meaning"):
    e = q["dictionary_entries"][0]
    name = q["dictionary_kind"] == "jmnedict"
    return {
        "schema_version": 1,
        "request_id": q["id"],
        "item_id": q["item_id"],
        "context_hash": q["context_hash"],
        "selected_entry_id": e["entry_id"],
        "selected_sense_id": None if name else e["senses"][0]["id"],
        "selected_translation_id": e["translations"][0]["id"] if name else None,
        "display_meaning": meaning,
        "ambiguity_note": None,
        "provider_id": provider.provider_id,
        "model_id": provider.model_id,
        "prompt_version": q["prompt_version"],
    }


def test_requests_are_stable_bounded_and_preserve_provenance(requests):
    assert serialize(requests) == serialize(copy.deepcopy(requests))
    assert len(requests["requests"]) == 5
    for q in requests["requests"]:
        assert 1 <= len(q["context"]) <= 3 and q["sentence_id"] in [
            x["id"] for x in q["context"]
        ]
        assert q["precedence"] == ["publisher", "user", "dictionary", "model"]
    assert requests["requests"][2]["authoritative_reading"] == "おもてぶたい"
    assert all(
        "おもてぶたい" not in x["text"] for x in requests["requests"][2]["context"]
    )


def test_disabled_mode_is_dictionary_only(requests):
    report = enrich_requests(requests)
    assert not report["diagnostics"] and all(
        x["source"] == "dictionary" and x["cache"] == "disabled"
        for x in report["results"]
    )


def test_valid_scripted_response_and_cache_hit(requests, tmp_path):
    q = requests["requests"][0]
    provider = ScriptedProvider(
        {q["id"]: response(q, ScriptedProvider({}), "pleasant weather")}
    )
    first = enrich_requests(
        {"schema_version": 1, "book_id": requests["book_id"], "requests": [q]},
        provider,
        tmp_path,
    )
    assert (
        first["results"][0]["source"] == "model"
        and first["results"][0]["cache"] == "miss"
        and provider.calls == [q["id"]]
    )
    second = enrich_requests(
        {"schema_version": 1, "book_id": requests["book_id"], "requests": [q]},
        provider,
        tmp_path,
    )
    assert second["results"][0]["source"] == "cache" and provider.calls == [q["id"]]


def test_cache_key_changes_with_context_or_provider(requests):
    q = requests["requests"][0]
    a = ScriptedProvider({})
    first = cache_key(q, a)
    changed = copy.deepcopy(q)
    changed["context"][0]["text"] += "x"
    changed["context_hash"] = "changed"
    assert first != cache_key(changed, a)


def test_corrupt_cache_falls_back_without_provider_call(requests, tmp_path):
    q = requests["requests"][0]
    provider = ScriptedProvider({q["id"]: response(q, ScriptedProvider({}))})
    (tmp_path / f"{cache_key(q,provider)}.json").write_text("{broken")
    report = enrich_requests(
        {"schema_version": 1, "book_id": requests["book_id"], "requests": [q]},
        provider,
        tmp_path,
    )
    assert (
        report["results"][0]["source"] == "dictionary"
        and provider.calls == []
        and report["diagnostics"][0]["reason"] == "JSONDecodeError"
    )


@pytest.mark.parametrize(
    "change,message",
    [
        (lambda r: r.update(selected_entry_id="missing"), "unsupplied entry"),
        (lambda r: r.update(selected_sense_id="missing"), "JMdict sense"),
        (lambda r: r.update(display_meaning="<script>"), "Unsafe"),
        (lambda r: r.update(context_hash="wrong"), "identity"),
        (lambda r: r.update(extra="bad"), "unsupported fields"),
    ],
)
def test_response_validation_rejects_invalid_output(requests, change, message):
    q = requests["requests"][0]
    provider = ScriptedProvider({})
    r = response(q, provider)
    change(r)
    with pytest.raises(EnrichmentError, match=message):
        validate_response(q, r, provider)


def test_name_requires_jmnedict_translation(requests):
    q = requests["requests"][3]
    provider = ScriptedProvider({})
    r = response(q, provider)
    assert validate_response(q, r, provider)["selected_translation_id"]
    r["selected_sense_id"] = "bad"
    with pytest.raises(EnrichmentError, match="JMnedict"):
        validate_response(q, r, provider)


@pytest.mark.parametrize(
    "error", [TimeoutError(), RuntimeError("unavailable"), EnrichmentError("invalid")]
)
def test_provider_failures_fall_back(requests, tmp_path, error):
    q = requests["requests"][0]
    provider = ScriptedProvider({q["id"]: error})
    report = enrich_requests(
        {"schema_version": 1, "book_id": requests["book_id"], "requests": [q]},
        provider,
        tmp_path,
    )
    assert (
        report["results"][0]["display_meaning"] == q["dictionary_only_meaning"]
        and report["diagnostics"]
    )


def test_request_validation_rejects_hash_and_name_dictionary_mix(requests):
    bad = copy.deepcopy(requests)
    bad["requests"][0]["context_hash"] = "bad"
    with pytest.raises(EnrichmentError, match="hash"):
        validate_request_report(bad)
    bad = copy.deepcopy(requests)
    bad["requests"][3]["dictionary_kind"] = "jmdict"
    with pytest.raises(EnrichmentError, match="Name"):
        validate_request_report(bad)
