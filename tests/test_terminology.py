import copy
import json
import subprocess
from pathlib import Path

import pytest

from furiganalyse.book_context import serialize
from furiganalyse.terminology import (
    TerminologyError,
    build_consistency_report,
    disabled_terminology,
    safe_failure,
    validate_consistency_report,
    validate_registry,
    with_decision_hash,
)

ROOT = Path(__file__).resolve().parents[1]


def _json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


@pytest.fixture
def sources():
    return (
        _json("artifacts/phase6/evidence/run-a/evidence.json"),
        _json("artifacts/phase6/run-a/context-index.json"),
        _json("artifacts/phase5/enriched-plan/run-a/annotation-plan.json"),
        _json("tests/fixtures/phase6-terminology-registry-v1.json"),
    )


@pytest.fixture
def report(sources):
    return build_consistency_report(*sources)


def _rehash(decision):
    decision["decision_hash"] = with_decision_hash(decision)["decision_hash"]


def test_reviewed_baseline_statuses_and_no_automatic_terms(report):
    assert [value["consistency_status"] for value in report["results"]] == [
        "single-occurrence-observation",
        "single-occurrence-observation",
        "consistent-user-approved",
        "deferred-by-user",
        "single-occurrence-observation",
    ]
    assert [value["approved_term"] for value in report["results"]] == [
        None,
        None,
        "public stage",
        None,
        None,
    ]
    assert report["diagnostics"] == []
    assert all(
        value["effective_terminology_source"] is None
        for value in report["results"]
        if value["decision_status"] != "approved"
    )


def test_approved_table_applies_to_both_occurrences_without_changing_reading(report):
    result = report["results"][2]
    assert result["surface_forms"] == ["表舞台"]
    assert result["authoritative_reading"] == "おもてぶたい"
    assert result["reading_source"] == "publisher"
    assert result["decision_id"] == "terminology-decision-0001"
    assert result["approved_term"] == "public stage"
    assert result["effective_terminology_source"] == "user"
    assert [value["publisher_ruby_id"] for value in result["occurrences"]] == [
        "ch-0001-b-0004-r-0001",
        "ch-0001-b-0004-r-0002",
    ]


def test_deferred_name_stays_jmnedict_name_without_term(report):
    result = report["results"][3]
    assert result["evidence_kind"] == "publisher_ruby_name"
    assert result["authoritative_reading"] == "ゆきの"
    assert result["reading_source"] == "publisher"
    assert result["sense_ids"] == []
    assert result["translation_ids"] == ["jmnedict-2001-translation-0001"]
    assert result["consistency_status"] == "deferred-by-user"
    assert result["approved_term"] is None


def test_registry_and_report_are_deterministic_and_plan_is_unchanged(sources):
    original = serialize(sources[2])
    first = build_consistency_report(*sources)
    second = build_consistency_report(*sources)
    assert serialize(first) == serialize(second)
    assert serialize(sources[2]) == original
    assert [value["id"] for value in first["results"]] == [
        f"terminology-result-{number:04d}" for number in range(1, 6)
    ]
    assert len({value["result_hash"] for value in first["results"]}) == 5


def test_legal_fixture_matches_checked_in_golden_and_review_cases(sources):
    report = build_consistency_report(*sources)
    assert serialize(report) == (
        ROOT / "tests/phase6_golden/terminology-consistency-v1.json"
    ).read_text(encoding="utf-8")
    review = _json("tests/phase6_golden/terminology-review-cases-v1.json")
    assert review["expected"]["results"] == len(report["results"])
    assert review["expected"]["decisions"] == len(sources[3]["decisions"])
    for expected, result in zip(review["cases"], report["results"]):
        assert expected["surface"] == result["surface_forms"][0]
        assert expected["decision_status"] == result["decision_status"]
        assert expected["approved_term"] == result["approved_term"]
        assert expected["consistency_status"] == result["consistency_status"]


def test_rejected_decision_is_auditable_and_has_no_term(sources):
    values = copy.deepcopy(sources)
    decision = values[3]["decisions"][0]
    decision["status"] = "rejected"
    decision["approved_term"] = None
    decision["reviewer_note"] = "Rejected for this terminology registry."
    _rehash(decision)
    report = build_consistency_report(*values)
    result = report["results"][2]
    assert result["consistency_status"] == "rejected-by-user"
    assert result["decision_status"] == "rejected"
    assert result["approved_term"] is None


def test_missing_decision_for_recurring_group_is_diagnostic(sources):
    values = copy.deepcopy(sources)
    values[3]["decisions"] = [values[3]["decisions"][1]]
    values[3]["decisions"][0]["id"] = "terminology-decision-0001"
    _rehash(values[3]["decisions"][0])
    report = build_consistency_report(*values)
    table = report["results"][2]
    assert table["consistency_status"] == "unapproved-recurring-evidence"
    assert table["approved_term"] is None
    assert report["diagnostics"] == [
        {
            "id": "terminology-diagnostic-0001",
            "group_id": "evidence-group-0003",
            "decision_id": None,
            "reason": "missing-recurring-decision",
        }
    ]


def test_approved_term_difference_is_diagnostic_only(sources):
    values = copy.deepcopy(sources)
    decision = values[3]["decisions"][0]
    decision["approved_term"] = "public arena"
    _rehash(decision)
    original = serialize(values[2])
    report = build_consistency_report(*values)
    assert report["results"][2]["approved_term"] == "public arena"
    assert report["diagnostics"] == [
        {
            "id": "terminology-diagnostic-0001",
            "group_id": "evidence-group-0003",
            "decision_id": "terminology-decision-0001",
            "reason": "approved-term-differs-current-meaning",
        }
    ]
    assert serialize(values[2]) == original


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda registry: registry["decisions"][0].update(
                source_evidence_hash="0" * 64
            ),
            "Stale evidence",
        ),
        (
            lambda registry: registry["decisions"][0].update(
                evidence_group_id="evidence-group-9999"
            ),
            "Unknown evidence group",
        ),
        (
            lambda registry: registry["decisions"][0].update(status="automatic"),
            "Invalid decision status",
        ),
        (
            lambda registry: registry["decisions"][0].update(
                approved_term="<script>bad</script>"
            ),
            "Unsafe or missing",
        ),
        (
            lambda registry: registry["decisions"][0].update(
                approved_term=r"C:\\Users\\secret"
            ),
            "Unsafe or missing",
        ),
        (
            lambda registry: registry["decisions"][0].update(
                approved_term="api_key=secret"
            ),
            "Unsafe or missing",
        ),
        (
            lambda registry: registry["decisions"][1].update(
                approved_term="Yukino"
            ),
            "Term supplied",
        ),
        (
            lambda registry: registry["decisions"][0].update(reviewer=""),
            "Missing reviewer",
        ),
        (
            lambda registry: registry["decisions"][0].update(
                authoritative_reading="おもてまい"
            ),
            "Stale evidence",
        ),
    ],
)
def test_invalid_registry_decisions_are_rejected(sources, mutation, message):
    registry = copy.deepcopy(sources[3])
    mutation(registry)
    _rehash(registry["decisions"][0])
    if len(registry["decisions"]) > 1:
        _rehash(registry["decisions"][1])
    with pytest.raises(TerminologyError, match=message):
        validate_registry(registry, sources[0])


def test_duplicate_group_decision_is_rejected(sources):
    registry = copy.deepcopy(sources[3])
    duplicate = copy.deepcopy(registry["decisions"][0])
    duplicate["id"] = "terminology-decision-0003"
    _rehash(duplicate)
    registry["decisions"].append(duplicate)
    with pytest.raises(TerminologyError, match="Unordered|duplicate"):
        validate_registry(registry, sources[0])


def test_changed_source_models_are_rejected(sources):
    values = copy.deepcopy(sources)
    values[1]["records"][0]["text"] = "changed"
    with pytest.raises(TerminologyError, match="hash mismatch"):
        build_consistency_report(*values)
    values = copy.deepcopy(sources)
    values[2]["items"][2]["reading"] = "おもてまい"
    with pytest.raises(TerminologyError, match="hash mismatch"):
        build_consistency_report(*values)


def test_validation_rejects_result_changes_hashes_and_unsupported_fields(
    report, sources
):
    corrupt = copy.deepcopy(report)
    corrupt["results"][2]["authoritative_reading"] = "おもてまい"
    with pytest.raises(TerminologyError, match="changed evidence"):
        validate_consistency_report(corrupt, sources[0], sources[3])
    corrupt = copy.deepcopy(report)
    corrupt["results"][0]["result_hash"] = "0" * 64
    with pytest.raises(TerminologyError, match="result hash"):
        validate_consistency_report(corrupt, sources[0], sources[3])
    corrupt = copy.deepcopy(report)
    corrupt["results"][0]["automatic_term"] = "forbidden"
    with pytest.raises(TerminologyError, match="unsupported"):
        validate_consistency_report(corrupt, sources[0], sources[3])


def test_disabled_and_failure_preserve_plan_bytes(sources):
    original = serialize(sources[2])
    disabled, disabled_plan = disabled_terminology(sources[2])
    failure, failure_plan = safe_failure(sources[2], "corrupt-registry")
    assert disabled == {
        "schema_version": 1,
        "status": "disabled",
        "results": [],
        "diagnostics": [],
    }
    assert failure["diagnostics"] == [
        {"id": "terminology-diagnostic-0001", "reason": "corrupt-registry"}
    ]
    assert serialize(disabled_plan) == original
    assert serialize(failure_plan) == original


def test_fallback_cli_preserves_plan_bytes(tmp_path):
    plan = ROOT / "artifacts/phase5/enriched-plan/run-a/annotation-plan.json"
    report = tmp_path / "report.json"
    fallback = tmp_path / "plan.json"
    subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/build_terminology_consistency.py"),
            "fallback",
            str(plan),
            str(report),
            str(fallback),
            "--reason",
            "stale-evidence-hash",
        ],
        check=True,
        cwd=ROOT,
    )
    assert fallback.read_bytes() == plan.read_bytes()
    value = json.loads(report.read_text(encoding="utf-8"))
    assert value["status"] == "fallback"
    assert value["diagnostics"][0]["reason"] == "stale-evidence-hash"
