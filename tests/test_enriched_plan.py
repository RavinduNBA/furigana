import copy
import json
from pathlib import Path

import pytest

from furiganalyse.enriched_plan import EnrichedPlanError, apply_enrichment
from furiganalyse.enrichment import serialize

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


@pytest.fixture
def inputs():
    return (
        load("artifacts/phase4/run-a/annotation-plan.json"),
        load("artifacts/phase5/run-a/requests.json"),
        load("artifacts/phase5/provider/run-a/report.json"),
    )


def test_all_reviewed_meanings_are_applied_and_auditable(inputs):
    plan, requests, report = inputs
    enriched, diagnostics = apply_enrichment(plan, requests, report)
    assert not diagnostics and enriched["schema_version"] == 2
    assert [x["display_meaning"] for x in enriched["items"]] == [
        "pleasant weather",
        "word",
        "public stage",
        "Yukino (female given name)",
        "to turn around",
    ]
    assert [x["dictionary_only_display_meaning"] for x in enriched["enrichments"]] == [
        "fine weather",
        "language",
        "public stage",
        "Yukino (person; female given name)",
        "to turn around",
    ]
    assert enriched["items"][2]["reading"] == "おもてぶたい"
    assert enriched["items"][2]["reading_source"] == "publisher"
    assert enriched["items"][3]["kind"] == "name"
    assert enriched["items"][3]["reading"] == "ゆきの"


def test_enriched_plan_matches_golden_and_is_deterministic(inputs):
    enriched, _ = apply_enrichment(*inputs)
    assert serialize(enriched) == serialize(apply_enrichment(*copy.deepcopy(inputs))[0])
    assert serialize(enriched) == (ROOT / "tests/phase5_golden/enriched-plan-v2.json").read_text()


def test_cache_results_are_accepted(inputs):
    plan, requests, _ = inputs
    cache = load("artifacts/phase5/provider/run-a/cache-hit.json")
    enriched, _ = apply_enrichment(plan, requests, cache)
    assert all(x["meaning_provenance"] == "validated-cache" for x in enriched["enrichments"])
    assert all(x["cache_status"] == "hit" for x in enriched["enrichments"])


@pytest.mark.parametrize("artifact", ["disabled.json", "failure.json"])
def test_disabled_and_failure_return_pure_fallback(inputs, artifact):
    plan, requests, _ = inputs
    report = load(
        "artifacts/phase5/run-a/disabled.json"
        if artifact == "disabled.json"
        else "artifacts/phase5/provider/run-a/failure.json"
    )
    enriched, diagnostics = apply_enrichment(plan, requests, report)
    assert enriched is None and len(diagnostics) == 5


def test_mixed_success_and_fallback_is_ordered(inputs):
    plan, requests, report = copy.deepcopy(inputs)
    report["results"] = report["results"][:2] + load(
        "artifacts/phase5/provider/run-a/failure.json"
    )["results"][2:]
    enriched, diagnostics = apply_enrichment(plan, requests, report)
    assert [x["item_id"] for x in enriched["enrichments"]] == [
        "study-item-0001",
        "study-item-0002",
    ]
    assert len(diagnostics) == 3
    assert [x["display_meaning"] for x in enriched["items"]] == [
        "pleasant weather",
        "word",
        "public stage",
        "Yukino (person; female given name)",
        "to turn around",
    ]


def test_missing_result_is_safe_fallback(inputs):
    plan, requests, report = copy.deepcopy(inputs)
    report["results"].pop()
    enriched, diagnostics = apply_enrichment(plan, requests, report)
    assert len(enriched["enrichments"]) == 4
    assert diagnostics[0]["reason"] == "missing-result"
    assert "怪訝" not in serialize(diagnostics)


def test_duplicate_and_unknown_results_are_rejected(inputs):
    plan, requests, report = copy.deepcopy(inputs)
    report["results"].append(copy.deepcopy(report["results"][0]))
    with pytest.raises(EnrichedPlanError, match="Duplicate"):
        apply_enrichment(plan, requests, report)
    plan, requests, report = copy.deepcopy(inputs)
    report["results"][0]["item_id"] = "unknown"
    with pytest.raises(EnrichedPlanError, match="Unknown"):
        apply_enrichment(plan, requests, report)


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("request_id", "wrong", "mismatch"),
        ("selected_entry_id", "wrong", "Unsupplied"),
        ("selected_sense_id", "wrong", "Unsupplied"),
        ("provider_id", "unsupported", "Unsupported provider"),
        ("cache_key", "bad", "cache identity"),
        ("display_meaning", "<script>", "Unsafe"),
        ("display_meaning", "x" * 121, "Unsafe"),
    ],
)
def test_invalid_accepted_results_are_rejected(inputs, field, value, message):
    plan, requests, report = copy.deepcopy(inputs)
    report["results"][0][field] = value
    with pytest.raises(EnrichedPlanError, match=message):
        apply_enrichment(plan, requests, report)


def test_name_cannot_use_jmdict_sense(inputs):
    plan, requests, report = copy.deepcopy(inputs)
    name = report["results"][3]
    name["selected_sense_id"] = "jmdict-1001-sense-0001"
    name["selected_translation_id"] = None
    with pytest.raises(EnrichedPlanError, match="Unsupplied"):
        apply_enrichment(plan, requests, report)


def test_changed_request_metadata_and_context_are_rejected(inputs):
    plan, requests, report = copy.deepcopy(inputs)
    requests["requests"][2]["authoritative_reading"] = "changed"
    with pytest.raises(EnrichedPlanError, match="metadata"):
        apply_enrichment(plan, requests, report)
    plan, requests, report = copy.deepcopy(inputs)
    requests["requests"][0]["context_hash"] = "wrong"
    with pytest.raises(Exception, match="hash"):
        apply_enrichment(plan, requests, report)


def test_unsupported_fields_and_invalid_fallback_are_rejected(inputs):
    plan, requests, report = copy.deepcopy(inputs)
    report["results"][0]["reading"] = "changed"
    with pytest.raises(EnrichedPlanError, match="fields"):
        apply_enrichment(plan, requests, report)
    plan, requests, _ = inputs
    disabled = load("artifacts/phase5/run-a/disabled.json")
    disabled["results"][0]["display_meaning"] = "changed"
    with pytest.raises(EnrichedPlanError, match="fallback"):
        apply_enrichment(plan, requests, disabled)


def test_unsafe_or_unknown_source_diagnostics_are_rejected(inputs):
    plan, requests, report = copy.deepcopy(inputs)
    report["diagnostics"] = [
        {
            "id": "diagnostic-1",
            "request_id": "enrichment-request-0001",
            "reason": "failure with raw context",
        }
    ]
    with pytest.raises(EnrichedPlanError, match="diagnostic"):
        apply_enrichment(plan, requests, report)
    report["diagnostics"][0]["reason"] = "TimeoutError"
    report["diagnostics"][0]["request_id"] = "unknown"
    with pytest.raises(EnrichedPlanError, match="Unknown"):
        apply_enrichment(plan, requests, report)
