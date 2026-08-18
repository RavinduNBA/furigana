import copy
import json
import subprocess
from pathlib import Path

import pytest

from furiganalyse.book_context import serialize
from furiganalyse.context_evidence import (
    ContextEvidenceError,
    _identity,
    build_evidence_report,
    disabled_evidence,
    safe_failure,
    validate_evidence_report,
)

ROOT = Path(__file__).resolve().parents[1]


def _json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


@pytest.fixture
def sources():
    return (
        _json("artifacts/phase6/run-a/context-index.json"),
        _json("artifacts/phase3/jmnedict/run-a/vocabulary.json"),
        _json("artifacts/phase5/enriched-plan/run-a/annotation-plan.json"),
    )


@pytest.fixture
def report(sources):
    return build_evidence_report(*sources)


def test_baseline_groups_counts_order_and_diagnostics(report):
    assert report["schema_version"] == 1
    assert len(report["groups"]) == 5
    assert sum(x["book_occurrence_count"] for x in report["groups"]) == 6
    assert [x["id"] for x in report["groups"]] == [
        f"evidence-group-{number:04d}" for number in range(1, 6)
    ]
    assert [x["surface_forms"][0] for x in report["groups"]] == [
        "良い天気だ",
        "言葉",
        "表舞台",
        "雪乃",
        "振り返っ",
    ]
    assert [x["reason"] for x in report["diagnostics"]] == [
        "insufficient-recurrence"
    ] * 4
    assert all("preferred" not in key and "model" not in key for key in report)


def test_repeated_publisher_ruby_vocabulary_is_grouped(report):
    group = report["groups"][2]
    assert group["evidence_kind"] == "publisher_ruby_vocabulary"
    assert group["lemma"] == "表舞台"
    assert group["authoritative_reading"] == "おもてぶたい"
    assert group["reading_source"] == "publisher"
    assert group["book_occurrence_count"] == 2
    assert group["eligible_for_terminology_review"] is True
    assert [x["publisher_ruby_id"] for x in group["occurrences"]] == [
        "ch-0001-b-0004-r-0001",
        "ch-0001-b-0004-r-0002",
    ]
    assert [x["source_occurrence_id"] for x in group["occurrences"]] == [
        "study-item-0003-occ-0001",
        "study-item-0003-occ-0002",
    ]
    assert group["chapter_occurrence_counts"] == [
        {"chapter_id": "ch-0001", "count": 2}
    ]


def test_expression_vocabulary_and_name_remain_separate(report):
    expression, word, _, name, verb = report["groups"]
    assert expression["evidence_kind"] == "jmdict_expression"
    assert expression["normalized_form"] == "良い天気"
    assert expression["lemma"] is None
    assert word["evidence_kind"] == verb["evidence_kind"] == "jmdict_vocabulary"
    assert word["lemma"] == "言葉"
    assert verb["lemma"] == "振り返る"
    assert name["evidence_kind"] == "publisher_ruby_name"
    assert name["translation_ids"] == ["jmnedict-2001-translation-0001"]
    assert name["sense_ids"] == []
    assert all(x["translation_ids"] == [] for x in (expression, word, verb))


def test_exact_references_offsets_locations_and_hashes(report, sources):
    records = {x["id"]: x for x in sources[0]["records"]}
    plan_items = {x["id"]: x for x in sources[2]["items"]}
    occurrence_ids = []
    for group in report["groups"]:
        assert len(group["evidence_hash"]) == 64
        assert group["first_location"]["record_id"] == group["occurrences"][0]["record_id"]
        assert group["last_location"]["record_id"] == group["occurrences"][-1]["record_id"]
        for occurrence in group["occurrences"]:
            occurrence_ids.append(occurrence["id"])
            record = records[occurrence["record_id"]]
            item = plan_items[occurrence["item_id"]]
            assert (
                record["text"][
                    occurrence["sentence_start"] : occurrence["sentence_end"]
                ]
                == item["surface"]
            )
            assert occurrence["chapter_id"] == record["chapter_id"]
            assert occurrence["block_id"] == record["block_id"]
            assert occurrence["sentence_id"] == record["sentence_id"]
    assert occurrence_ids == [
        f"evidence-occurrence-{number:04d}" for number in range(1, 7)
    ]


def test_minimum_one_marks_all_groups_eligible_without_diagnostics(sources):
    report = build_evidence_report(*sources, minimum_occurrences=1)
    assert all(x["eligible_for_terminology_review"] for x in report["groups"])
    assert all(x["eligibility_reason"] == "meets-minimum-occurrences" for x in report["groups"])
    assert report["diagnostics"] == []


def test_output_is_deterministic_and_does_not_copy_context_text(sources):
    first = build_evidence_report(*sources)
    second = build_evidence_report(*sources)
    assert serialize(first) == serialize(second)
    serialized = serialize(first)
    assert "「今日は良い天気だね」と彼女は言った。" not in serialized
    assert "怪訝な顔で振り返った。" not in serialized
    assert "preferred_translation" not in serialized


def test_legal_fixture_matches_checked_in_evidence_golden(sources):
    report = build_evidence_report(*sources)
    assert serialize(report) == (
        ROOT / "tests/phase6_golden/evidence-v1.json"
    ).read_text(encoding="utf-8")
    review = _json("tests/phase6_golden/evidence-review-cases-v1.json")
    assert review["expected"]["groups"] == len(report["groups"])
    assert review["expected"]["occurrences"] == sum(
        value["book_occurrence_count"] for value in report["groups"]
    )
    assert review["expected"]["eligible_groups"] == sum(
        value["eligible_for_terminology_review"] for value in report["groups"]
    )
    for expected, group in zip(review["cases"], report["groups"]):
        assert expected["surface"] == group["surface_forms"][0]
        assert expected["evidence_kind"] == group["evidence_kind"]
        assert expected["occurrences"] == group["book_occurrence_count"]
        assert expected["eligible"] == group["eligible_for_terminology_review"]


def test_same_lemma_with_incompatible_readings_has_different_identity(sources):
    item = sources[2]["items"][1]
    changed = copy.deepcopy(item)
    changed["reading"] = "ことのは"
    assert _identity(item, "jmdict_vocabulary") != _identity(
        changed, "jmdict_vocabulary"
    )


def test_ambiguous_name_candidates_are_reported_not_resolved(sources):
    values = copy.deepcopy(sources)
    match = values[1]["name_dictionary_matches"][0]
    alternate = copy.deepcopy(match["entries"][0])
    alternate["entry_id"] = "jmnedict-2999"
    alternate["sequence"] = 2999
    match["entries"].append(alternate)
    report = build_evidence_report(*values)
    diagnostic = next(
        value
        for value in report["diagnostics"]
        if value["reason"] == "ambiguous-name-candidates"
    )
    assert diagnostic == {
        "id": "evidence-diagnostic-0004",
        "group_id": "evidence-group-0004",
        "item_id": "study-item-0004",
        "reason": "ambiguous-name-candidates",
    }
    assert report["groups"][3]["item_ids"] == ["study-item-0004"]


@pytest.mark.parametrize(
    ("source", "mutation", "message"),
    [
        (0, lambda x: x.update(book_id="other"), "identity mismatch"),
        (1, lambda x: x.update(schema_version=3), "must be 4"),
        (
            2,
            lambda x: x["items"][3].update(reading="せつの"),
            "Publisher-reading conflict",
        ),
        (
            1,
            lambda x: x.update(
                tokens=[
                    value
                    for value in x["tokens"]
                    if value["id"] != "ch-0001-b-0002-s-0001-tok-0004"
                ]
            ),
            "Unknown token",
        ),
        (
            2,
            lambda x: x["items"][0]["occurrences"][0].update(sentence_start=0),
            "offset mismatch",
        ),
    ],
)
def test_invalid_or_mismatched_sources_are_rejected(
    sources, source, mutation, message
):
    values = copy.deepcopy(sources)
    mutation(values[source])
    with pytest.raises(ContextEvidenceError, match=message):
        build_evidence_report(*values)


def test_validation_rejects_ids_counts_hashes_order_and_unsupported_fields(report):
    corrupt = copy.deepcopy(report)
    corrupt["groups"][1]["id"] = corrupt["groups"][0]["id"]
    with pytest.raises(ContextEvidenceError, match="Unstable or invalid"):
        validate_evidence_report(corrupt)
    corrupt = copy.deepcopy(report)
    corrupt["groups"][0]["book_occurrence_count"] = 2
    with pytest.raises(ContextEvidenceError, match="locations or count"):
        validate_evidence_report(corrupt)
    corrupt = copy.deepcopy(report)
    corrupt["groups"][0]["evidence_hash"] = "0" * 64
    with pytest.raises(ContextEvidenceError, match="evidence hash"):
        validate_evidence_report(corrupt)
    corrupt = copy.deepcopy(report)
    corrupt["groups"][0]["preferred_translation"] = "forbidden"
    with pytest.raises(ContextEvidenceError, match="Unsupported"):
        validate_evidence_report(corrupt)


def test_disabled_and_failure_preserve_plan_bytes(sources):
    original = serialize(sources[2])
    disabled, disabled_plan = disabled_evidence(sources[2])
    failure, failure_plan = safe_failure(sources[2], "corrupt-input")
    assert disabled == {
        "schema_version": 1,
        "status": "disabled",
        "groups": [],
        "diagnostics": [],
    }
    assert failure["diagnostics"] == [
        {"id": "evidence-diagnostic-0001", "reason": "corrupt-input"}
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
            str(ROOT / "scripts/build_context_evidence.py"),
            "fallback",
            str(plan),
            str(report),
            str(fallback),
            "--reason",
            "corrupt-input",
        ],
        check=True,
        cwd=ROOT,
    )
    assert fallback.read_bytes() == plan.read_bytes()
    assert json.loads(report.read_text(encoding="utf-8"))["status"] == "fallback"
