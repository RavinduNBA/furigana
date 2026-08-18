import copy
import json
import subprocess
from pathlib import Path

import pytest

from furiganalyse.book_context import (
    BookContextError,
    build_context_index,
    build_retrieval_report,
    disabled_context,
    retrieve_context,
    safe_failure,
    serialize,
    validate_context_index,
    validate_retrieval,
)

ROOT = Path(__file__).resolve().parents[1]


def _json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


@pytest.fixture
def sources():
    return (
        _json("artifacts/phase2/run-a/book.json"),
        _json("artifacts/phase3/jmnedict/run-a/vocabulary.json"),
        _json("artifacts/phase5/enriched-plan/run-a/annotation-plan.json"),
    )


@pytest.fixture
def context_index(sources):
    return build_context_index(*sources)


def test_index_is_deterministic_ordered_and_canonical(context_index, sources):
    second = build_context_index(*sources)
    assert serialize(context_index) == serialize(second)
    assert [record["id"] for record in context_index["records"]] == [
        f"book-context-record-{number:04d}" for number in range(1, 14)
    ]
    assert len(
        [
            occurrence
            for record in context_index["records"]
            for occurrence in record["study_occurrences"]
        ]
    ) == 6
    book_sentences = [
        sentence["text"]
        for chapter in sources[0]["chapters"]
        for block in chapter["blocks"]
        for sentence in block["sentences"]
    ]
    assert [record["text"] for record in context_index["records"]] == book_sentences
    assert "おもてぶたい" not in "\n".join(book_sentences)
    assert context_index["precedence"] == [
        "publisher",
        "user",
        "dictionary",
        "book_context",
        "model",
    ]


@pytest.mark.parametrize(
    ("item_id", "surface", "kind"),
    [
        ("study-item-0001", "良い天気だ", "expression"),
        ("study-item-0002", "言葉", "vocabulary"),
        ("study-item-0004", "雪乃", "name"),
        ("study-item-0005", "振り返っ", "vocabulary"),
    ],
)
def test_retrieves_all_item_kinds(context_index, item_id, surface, kind):
    result = retrieve_context(context_index, item_id=item_id)
    assert result["target"]["surface"] == surface
    assert result["target"]["item_kind"] == kind
    assert len([x for x in result["contexts"] if x["reason"] == "containing"]) == 1
    validate_retrieval(result, context_index)


def test_repeated_item_can_be_retrieved_by_occurrence(context_index):
    first = retrieve_context(
        context_index, occurrence_id="study-item-0003-occ-0001"
    )
    second = retrieve_context(
        context_index, occurrence_id="study-item-0003-occ-0002"
    )
    assert first["target"]["publisher_ruby_id"] == "ch-0001-b-0004-r-0001"
    assert second["target"]["publisher_ruby_id"] == "ch-0001-b-0004-r-0002"
    assert first["target"]["authoritative_reading"] == "おもてぶたい"
    assert second["target"]["authoritative_reading"] == "おもてぶたい"
    assert first["target"]["occurrence_id"] != second["target"]["occurrence_id"]


def test_default_scope_never_crosses_block(context_index):
    result = retrieve_context(context_index, item_id="study-item-0002")
    assert [x["sentence_id"] for x in result["contexts"]] == [
        "ch-0001-b-0003-s-0001"
    ]
    assert all(x["block_id"] == "ch-0001-b-0003" for x in result["contexts"])


def test_same_chapter_scope_crosses_blocks_but_not_chapters(context_index):
    result = retrieve_context(
        context_index,
        item_id="study-item-0002",
        scope="chapter",
        previous=1,
        following=1,
    )
    assert [x["sentence_id"] for x in result["contexts"]] == [
        "ch-0001-b-0002-s-0001",
        "ch-0001-b-0003-s-0001",
        "ch-0001-b-0004-s-0001",
    ]
    assert {x["chapter_id"] for x in result["contexts"]} == {"ch-0001"}


def test_first_last_and_block_boundaries(context_index):
    name = retrieve_context(context_index, item_id="study-item-0004")
    verb = retrieve_context(context_index, item_id="study-item-0005")
    assert [x["reason"] for x in name["contexts"]] == ["containing", "following"]
    assert [x["reason"] for x in verb["contexts"]] == ["previous", "containing"]


def test_sentence_and_character_budgets_use_whole_sentences(context_index):
    one = retrieve_context(
        context_index,
        item_id="study-item-0004",
        sentence_budget=1,
        character_budget=6,
    )
    assert len(one["contexts"]) == 1
    assert one["contexts"][0]["text"] == "名前は雪乃。"
    limited = retrieve_context(
        context_index,
        item_id="study-item-0004",
        sentence_budget=3,
        character_budget=16,
    )
    assert len(limited["contexts"]) == 1
    with pytest.raises(BookContextError, match="exceeds character budget"):
        retrieve_context(
            context_index, item_id="study-item-0004", character_budget=5
        )


def test_queries_and_hashes_are_stable(context_index):
    queries = [
        {"item_id": f"study-item-{number:04d}"} for number in range(1, 6)
    ]
    first = build_retrieval_report(context_index, queries)
    second = build_retrieval_report(context_index, queries)
    assert serialize(first) == serialize(second)
    assert len({x["query_hash"] for x in first["results"]}) == 5
    assert len({x["result_hash"] for x in first["results"]}) == 5


def test_legal_fixture_matches_checked_in_goldens(context_index):
    queries = _json("tests/phase6_golden/retrieval-queries-v1.json")
    retrieval = build_retrieval_report(context_index, queries)
    assert serialize(context_index) == (
        ROOT / "tests/phase6_golden/context-index-v1.json"
    ).read_text(encoding="utf-8")
    assert serialize(retrieval) == (
        ROOT / "tests/phase6_golden/retrieval-v1.json"
    ).read_text(encoding="utf-8")
    assert all(len(result["contexts"]) < len(context_index["records"]) for result in retrieval["results"])


def test_reviewed_cases_match_retrieval_golden(context_index):
    review = _json("tests/phase6_golden/retrieval-review-cases-v1.json")
    retrieval = _json("tests/phase6_golden/retrieval-v1.json")
    assert review["expected"]["index_records"] == len(context_index["records"])
    assert review["expected"]["retrieval_results"] == len(retrieval["results"])
    by_item = {}
    for result in retrieval["results"]:
        by_item.setdefault(result["target"]["item_id"], []).append(result)
    for case in review["cases"][:5]:
        results = by_item[case["item_id"]]
        target = results[0]["target"]
        assert target["surface"] == case["surface"]
        assert target["item_kind"] == case["kind"]
        if "containing_sentence" in case:
            assert any(
                value["reason"] == "containing"
                and value["text"] == case["containing_sentence"]
                for result in results
                for value in result["contexts"]
            )


def test_invalid_hash_order_and_scope_are_rejected(context_index):
    result = retrieve_context(
        context_index,
        item_id="study-item-0004",
        scope="chapter",
    )
    corrupt = copy.deepcopy(result)
    corrupt["result_hash"] = "0" * 64
    with pytest.raises(BookContextError, match="hash mismatch"):
        validate_retrieval(corrupt, context_index)
    corrupt = copy.deepcopy(result)
    corrupt["contexts"].reverse()
    corrupt["result_hash"] = __import__("hashlib").sha256(
        json.dumps(
            corrupt["contexts"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with pytest.raises(BookContextError, match="ordering or budget"):
        validate_retrieval(corrupt, context_index)
    corrupt = copy.deepcopy(result)
    corrupt["query"]["previous"] = 0
    corrupt["query_hash"] = __import__("hashlib").sha256(
        json.dumps(
            corrupt["query"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with pytest.raises(BookContextError, match="adjacency window"):
        validate_retrieval(corrupt, context_index)


@pytest.mark.parametrize(
    ("source_number", "mutation", "message"),
    [
        (0, lambda value: value.update(book_id="other"), "identity mismatch"),
        (1, lambda value: value.update(schema_version=3), "must be 4"),
        (
            2,
            lambda value: value["items"][0]["occurrences"][0].update(
                sentence_start=0
            ),
            "offset mismatch",
        ),
        (
            2,
            lambda value: value["items"][3].update(reading="せつの"),
            "Publisher-reading precedence",
        ),
    ],
)
def test_mismatched_sources_are_rejected(sources, source_number, mutation, message):
    values = copy.deepcopy(sources)
    mutation(values[source_number])
    with pytest.raises(BookContextError, match=message):
        build_context_index(*values)


def test_unknown_dictionary_and_source_references_are_rejected(sources):
    values = copy.deepcopy(sources)
    values[2]["items"][0]["source_entry_ids"] = ["jmdict-unknown"]
    with pytest.raises(BookContextError, match="Unknown dictionary reference"):
        build_context_index(*values)
    values = copy.deepcopy(sources)
    values[2]["items"][0]["occurrences"][0]["token_ids"] = ["unknown-token"]
    with pytest.raises(BookContextError, match="Unknown token reference"):
        build_context_index(*values)


def test_index_validation_rejects_duplicate_and_unsupported_records(context_index):
    corrupt = copy.deepcopy(context_index)
    corrupt["records"][1]["id"] = corrupt["records"][0]["id"]
    with pytest.raises(BookContextError, match="Unstable or duplicate"):
        validate_context_index(corrupt)
    corrupt = copy.deepcopy(context_index)
    corrupt["records"][0]["unsupported"] = True
    with pytest.raises(BookContextError, match="Unsupported"):
        validate_context_index(corrupt)


def test_disabled_and_failure_preserve_plan_bytes(sources):
    plan = sources[2]
    original = serialize(plan)
    disabled, disabled_plan = disabled_context(plan)
    failure, failure_plan = safe_failure(plan, "corrupt-input")
    assert disabled["status"] == "disabled"
    assert failure["diagnostics"] == [
        {"id": "book-context-diagnostic-0001", "reason": "corrupt-input"}
    ]
    assert serialize(disabled_plan) == original
    assert serialize(failure_plan) == original
    assert "artifacts/" not in serialize(failure)


def test_fallback_cli_writes_safe_report_and_identical_plan(tmp_path):
    plan_path = ROOT / "artifacts/phase5/enriched-plan/run-a/annotation-plan.json"
    report = tmp_path / "report.json"
    fallback = tmp_path / "annotation-plan.json"
    subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/build_book_context.py"),
            "fallback",
            str(plan_path),
            str(report),
            str(fallback),
            "--reason",
            "corrupt-input",
        ],
        check=True,
        cwd=ROOT,
    )
    assert fallback.read_bytes() == plan_path.read_bytes()
    value = json.loads(report.read_text(encoding="utf-8"))
    assert value["status"] == "fallback"
    assert value["diagnostics"][0]["reason"] == "corrupt-input"
