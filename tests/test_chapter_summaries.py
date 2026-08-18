import copy
import json
import subprocess
from pathlib import Path

import pytest

from furiganalyse.book_context import serialize
from furiganalyse.chapter_summaries import (
    ChapterSummaryError,
    build_chapter_packets,
    build_summary_report,
    disabled_summaries,
    retrieve_summaries,
    safe_failure,
    validate_packet_report,
    validate_summary_registry,
    with_decision_hash,
)

ROOT = Path(__file__).resolve().parents[1]


def _json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


@pytest.fixture
def sources():
    return (
        _json("artifacts/phase6/run-a/context-index.json"),
        _json("artifacts/phase6/evidence/run-a/evidence.json"),
        _json("artifacts/phase6/terminology/run-a/consistency.json"),
    )


@pytest.fixture
def packets(sources):
    return build_chapter_packets(*sources)


@pytest.fixture
def registry():
    return _json("tests/fixtures/phase6-chapter-summary-registry-v1.json")


@pytest.fixture
def report(packets, registry):
    return build_summary_report(packets, registry)


def _rehash(decision):
    decision["decision_hash"] = with_decision_hash(decision)["decision_hash"]


def test_packets_are_reference_only_ordered_and_deterministic(sources, packets):
    assert serialize(packets) == serialize(build_chapter_packets(*sources))
    assert [value["chapter_id"] for value in packets["packets"]] == ["ch-0001", "ch-0002"]
    assert [value["sentence_count"] for value in packets["packets"]] == [7, 6]
    assert [value["character_count"] for value in packets["packets"]] == [80, 88]
    assert [len(value["sentence_record_ids"]) for value in packets["packets"]] == [7, 6]
    assert all("text" not in value for value in packets["packets"])
    assert all("summary" not in value for value in packets["packets"])


def test_packets_keep_chapter_evidence_names_and_terminology_separate(packets):
    first, second = packets["packets"]
    assert first["evidence_group_ids"] == [
        "evidence-group-0001", "evidence-group-0002", "evidence-group-0003"
    ]
    assert first["recurring_term_group_ids"] == ["evidence-group-0003"]
    assert first["effective_terminology"][0]["term"] == "public stage"
    assert first["proper_name_group_ids"] == []
    assert second["proper_name_group_ids"] == ["evidence-group-0004"]
    assert second["effective_terminology"] == []
    assert second["jmnedict_references"]["translation_ids"] == [
        "jmnedict-2001-translation-0001"
    ]


def test_packets_preserve_publisher_readings(packets):
    ruby = {
        value["id"]: value
        for packet in packets["packets"]
        for value in packet["publisher_ruby"]
    }
    assert ruby["ch-0001-b-0004-r-0001"]["reading"] == "おもてぶたい"
    assert ruby["ch-0001-b-0004-r-0002"]["reading"] == "おもてぶたい"
    assert ruby["ch-0002-b-0002-r-0001"]["reading"] == "ゆきの"
    assert ruby["ch-0002-b-0003-r-0001"]["reading"] is None


def test_summary_report_uses_only_explicit_approved_decision(packets, registry, report):
    first, second = report["results"]
    assert first["consistency_status"] == "approved-user-summary"
    assert first["effective_summary_source"] == "user"
    assert first["effective_summary"] == (
        "Good weather, a word, and the public stage are observed."
    )
    assert second["consistency_status"] == "deferred-by-user"
    assert second["effective_summary"] is None
    assert report["diagnostics"] == []
    assert registry["fixture_notice"].startswith("Synthetic test-fixture")


def test_outputs_match_checked_in_goldens_and_review_cases(packets, report):
    queries = _json("tests/phase6_golden/chapter-summary-queries-v1.json")
    retrieval = retrieve_summaries(packets, report, queries)
    assert serialize(packets) == (
        ROOT / "tests/phase6_golden/chapter-context-packets-v1.json"
    ).read_text(encoding="utf-8")
    assert serialize(report) == (
        ROOT / "tests/phase6_golden/chapter-summary-report-v1.json"
    ).read_text(encoding="utf-8")
    assert serialize(retrieval) == (
        ROOT / "tests/phase6_golden/chapter-summary-retrieval-v1.json"
    ).read_text(encoding="utf-8")
    review = _json("tests/phase6_golden/chapter-summary-review-cases-v1.json")
    assert review["expected"]["packets"] == 2
    assert review["expected"]["approved_summaries"] == 1


def test_missing_and_rejected_decisions_do_not_create_summaries(packets, registry):
    missing = copy.deepcopy(registry)
    missing["decisions"] = missing["decisions"][:1]
    report = build_summary_report(packets, missing)
    assert report["results"][1]["consistency_status"] == "missing-summary-decision"
    assert report["diagnostics"][0]["reason"] == "missing-summary-decision"
    rejected = copy.deepcopy(registry)
    rejected["decisions"][0]["status"] = "rejected"
    rejected["decisions"][0]["summary"] = None
    _rehash(rejected["decisions"][0])
    report = build_summary_report(packets, rejected)
    assert report["results"][0]["consistency_status"] == "rejected-by-user"
    assert report["results"][0]["effective_summary"] is None


def test_retrieval_is_bounded_previous_only_and_deterministic(packets, report):
    queries = _json("tests/phase6_golden/chapter-summary-queries-v1.json")
    value = retrieve_summaries(packets, report, queries)
    assert serialize(value) == serialize(retrieve_summaries(packets, report, queries))
    assert [len(result["summaries"]) for result in value["results"]] == [1, 1, 1]
    assert value["results"][0]["summaries"][0]["inclusion_reason"] == "target"
    assert value["results"][1]["target_chapter_id"] == "ch-0002"
    assert value["results"][1]["summaries"][0]["chapter_id"] == "ch-0001"
    assert value["results"][1]["summaries"][0]["inclusion_reason"] == "previous"
    assert all(
        summary["chapter_id"] != "ch-0002"
        for result in value["results"]
        for summary in result["summaries"]
    )


def test_retrieval_honors_count_and_character_budgets(packets, report):
    queries = _json("tests/phase6_golden/chapter-summary-queries-v1.json")
    queries["queries"] = [copy.deepcopy(queries["queries"][0])]
    queries["queries"][0]["character_budget"] = 10
    value = retrieve_summaries(packets, report, queries)
    assert value["results"][0]["summaries"] == []
    assert value["diagnostics"][0]["reason"] == "budget-exclusion"
    queries["queries"][0]["character_budget"] = 500
    queries["queries"][0]["summary_budget"] = 1
    assert len(retrieve_summaries(packets, report, queries)["results"][0]["summaries"]) == 1


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda d: d.update(source_packet_hash="0" * 64), "Stale packet"),
        (lambda d: d.update(packet_id="chapter-context-packet-9999"), "Unknown chapter"),
        (lambda d: d.update(status="automatic"), "Invalid summary"),
        (lambda d: d.update(summary="<script>bad</script>"), "Unsafe"),
        (lambda d: d.update(summary="api_key=secret"), "Unsafe"),
        (lambda d: d.update(reviewer=""), "Missing"),
        (lambda d: d.update(evidence_group_ids=["evidence-group-9999"]), "unsupported"),
        (
            lambda d: d.update(terminology_decision_ids=["terminology-decision-9999"]),
            "unsupported",
        ),
    ],
)
def test_invalid_summary_decisions_are_rejected(packets, registry, mutation, message):
    value = copy.deepcopy(registry)
    mutation(value["decisions"][0])
    _rehash(value["decisions"][0])
    with pytest.raises(ChapterSummaryError, match=message):
        validate_summary_registry(value, packets)


def test_changed_packet_hash_and_unknown_records_are_rejected(sources, packets):
    corrupt = copy.deepcopy(packets)
    corrupt["packets"][0]["sentence_record_ids"][0] = "unknown"
    with pytest.raises(ChapterSummaryError, match="sentence records"):
        validate_packet_report(corrupt, *sources)
    corrupt = copy.deepcopy(packets)
    corrupt["packets"][0]["packet_hash"] = "0" * 64
    with pytest.raises(ChapterSummaryError, match="packet hash"):
        validate_packet_report(corrupt, *sources)


def test_disabled_and_failure_preserve_phase5_plan_bytes():
    plan = _json("artifacts/phase5/enriched-plan/run-a/annotation-plan.json")
    original = serialize(plan)
    disabled, disabled_plan = disabled_summaries(plan)
    failure, failure_plan = safe_failure(plan, "corrupt-registry")
    assert disabled["results"] == [] and disabled["diagnostics"] == []
    assert failure["diagnostics"][0]["reason"] == "corrupt-registry"
    assert serialize(disabled_plan) == original
    assert serialize(failure_plan) == original


def test_cli_fallback_preserves_plan_bytes(tmp_path):
    plan = ROOT / "artifacts/phase5/enriched-plan/run-a/annotation-plan.json"
    report = tmp_path / "report.json"
    fallback = tmp_path / "plan.json"
    subprocess.run([
        str(ROOT / ".venv/bin/python"),
        str(ROOT / "scripts/build_chapter_summaries.py"),
        "fallback", str(plan), str(report), str(fallback), "--reason", "corrupt-registry",
    ], check=True, cwd=ROOT)
    assert fallback.read_bytes() == plan.read_bytes()
