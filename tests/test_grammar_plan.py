import copy
import json
from pathlib import Path

import pytest

from furiganalyse.grammar_analysis import detect_grammar, load_json, stable_hash
from furiganalyse.grammar_plan import (
    GrammarPlanError,
    build_grammar_plan,
    safe_build_grammar_plan,
    serialize_grammar_plan,
    validate_grammar_plan,
)
from scripts.build_phase7_fixture import build

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inputs():
    spec = load_json(ROOT / "tests/fixtures/phase7-passages-v1.json")
    dataset = load_json(ROOT / "tests/fixtures/phase7-grammar-rules-v1.json")
    book, vocabulary, annotation_plan = build(spec)
    grammar_report = detect_grammar(book, vocabulary, annotation_plan, dataset)
    return book, vocabulary, annotation_plan, grammar_report, dataset


def selected(inputs, **options):
    return build_grammar_plan(*inputs, enabled=True, **options)


def test_default_selects_five_primary_rules_and_excludes_synthetic(inputs):
    plan = selected(inputs)
    assert [item["canonical_key"] for item in plan["items"]] == [
        "〜ている", "〜たことがある", "〜ようにする", "〜てしまう", "〜なければならない"
    ]
    assert len(plan["items"]) == 5
    assert len(plan["occurrences"]) == 7
    assert any(value["reason"] == "synthetic-mechanics-rule" for value in plan["diagnostics"])


def test_explicit_test_only_synthetic_rule_inclusion(inputs):
    plan = selected(inputs, include_synthetic_mechanics=True, per_chapter_limit=5)
    assert [item["canonical_key"] for item in plan["items"]] == [
        "〜ている", "〜たことがある", "〜ようにする", "〜てしまう", "〜て", "〜なければならない"
    ]
    assert len(plan["occurrences"]) == 8
    assert not any(value["reason"] == "synthetic-mechanics-rule" for value in plan["diagnostics"])


def test_repeated_rule_deduplicates_item_but_preserves_occurrences(inputs):
    plan = selected(inputs)
    item = plan["items"][0]
    assert item["canonical_key"] == "〜ている"
    assert len(item["occurrence_ids"]) == 3
    assert item["book_count"] == 3


def test_overlap_dispositions_and_vocabulary_precedence(inputs):
    plan = selected(inputs)
    dispositions = {
        value["source_grammar_occurrence_id"]: (
            value["overlap_disposition"], value["link_disposition"]
        )
        for value in plan["occurrences"]
    }
    assert dispositions["grammar-occurrence-0001"] == (
        "contains-vocabulary", "grammar-note-reference-only"
    )
    assert dispositions["grammar-occurrence-0003"] == (
        "partial-overlap", "rejected-ambiguous-overlap"
    )
    assert dispositions["grammar-occurrence-0004"] == (
        "exact-span", "grammar-note-reference-only"
    )
    assert dispositions["grammar-occurrence-0005"] == ("no-overlap", "grammar-link")
    assert all(value["vocabulary_link_preserved"] for value in plan["overlaps"])


def test_publisher_ruby_and_name_expression_separation(inputs):
    plan = selected(inputs)
    publisher = next(
        value for value in plan["occurrences"]
        if value["source_grammar_occurrence_id"] == "grammar-occurrence-0007"
    )
    assert publisher["overlap_disposition"] == "publisher-ruby-protected"
    assert publisher["link_disposition"] == "publisher-ruby-preserved"
    kinds = {value["vocabulary_kind"] for value in plan["overlaps"]}
    assert {"vocabulary", "expression", "name"} <= kinds
    assert any(
        value["relationship"] == "no-overlap" and value["vocabulary_kind"] == "name"
        for value in plan["overlaps"]
    )


def test_per_chapter_limit_is_deterministic(inputs):
    plan = selected(inputs, per_chapter_limit=2)
    assert [item["canonical_key"] for item in plan["items"]] == [
        "〜ている", "〜たことがある", "〜なければならない"
    ]
    assert sum(value["reason"] == "per-chapter-limit" for value in plan["diagnostics"]) == 2


def test_disabled_plan_is_empty_and_sources_unchanged(inputs):
    before = [json.dumps(value, sort_keys=True, ensure_ascii=False) for value in inputs]
    plan = build_grammar_plan(*inputs)
    assert plan["items"] == plan["occurrences"] == plan["overlaps"] == plan["diagnostics"] == []
    after = [json.dumps(value, sort_keys=True, ensure_ascii=False) for value in inputs]
    assert before == after


def test_deterministic_serialization_ids_hashes_and_anchors(inputs):
    first = selected(inputs)
    second = selected(inputs)
    assert serialize_grammar_plan(first) == serialize_grammar_plan(second)
    validate_grammar_plan(*inputs, first)
    all_records = first["items"] + first["occurrences"] + first["overlaps"] + first["diagnostics"]
    assert all(value["hash"] == stable_hash({k: v for k, v in value.items() if k != "hash"}) for value in all_records)
    anchors = [value["note_anchor_id"] for value in first["items"]] + [
        value["source_anchor_id"] for value in first["occurrences"]
    ]
    assert len(anchors) == len(set(anchors))


@pytest.mark.parametrize("source_index", [0, 1, 2, 3])
def test_mismatched_source_books_are_rejected(inputs, source_index):
    values = copy.deepcopy(inputs)
    values[source_index]["book_id"] = "other"
    with pytest.raises(GrammarPlanError):
        build_grammar_plan(*values, enabled=True)


def test_stale_rule_hash_and_unknown_references_are_rejected(inputs):
    values = copy.deepcopy(inputs)
    values[4]["rules"][0]["hash"] = "stale"
    with pytest.raises(GrammarPlanError):
        build_grammar_plan(*values, enabled=True)
    values = copy.deepcopy(inputs)
    values[3]["occurrences"][0]["component_token_ids"][0] = "unknown-token"
    values[3]["occurrences"][0]["hash"] = stable_hash({
        k: v for k, v in values[3]["occurrences"][0].items() if k != "hash"
    })
    with pytest.raises(GrammarPlanError):
        build_grammar_plan(*values, enabled=True)


@pytest.mark.parametrize("limit", [0, -1, "4"])
def test_invalid_configuration_is_rejected(inputs, limit):
    with pytest.raises(GrammarPlanError):
        build_grammar_plan(*inputs, enabled=True, per_chapter_limit=limit)


def test_changed_offsets_and_anchor_collisions_are_rejected(inputs):
    values = copy.deepcopy(inputs)
    values[2]["items"][0]["occurrences"][0]["sentence_end"] = 99
    with pytest.raises(GrammarPlanError):
        selected(values)
    values = copy.deepcopy(inputs)
    plan = selected(values)
    broken = copy.deepcopy(plan)
    broken["occurrences"][0]["source_anchor_id"] = values[2]["items"][0]["occurrences"][0]["source_anchor_id"]
    broken["occurrences"][0]["hash"] = stable_hash({
        k: v for k, v in broken["occurrences"][0].items() if k != "hash"
    })
    with pytest.raises(GrammarPlanError):
        validate_grammar_plan(*values, broken)


def test_contained_by_vocabulary_relationship(inputs):
    values = copy.deepcopy(inputs)
    occurrence = values[2]["items"][0]["occurrences"][0]
    occurrence.update({"sentence_start": 0, "sentence_end": 8, "block_start": 0, "block_end": 8})
    plan = selected(values)
    first = plan["occurrences"][0]
    assert first["overlap_disposition"] == "contained-by-vocabulary"
    assert first["link_disposition"] == "grammar-note-reference-only"


def test_safe_failure_is_non_enriched_and_deterministic(inputs):
    values = copy.deepcopy(inputs)
    values[3]["schema_version"] = 99
    first = safe_build_grammar_plan(*values, enabled=True)
    second = safe_build_grammar_plan(*values, enabled=True)
    assert first == second
    assert not first["items"] and not first["occurrences"] and not first["overlaps"]
    assert [value["reason"] for value in first["diagnostics"]] == ["invalid-input"]


def test_plan_validation_rejects_vocabulary_suppression(inputs):
    plan = selected(inputs)
    broken = copy.deepcopy(plan)
    broken["overlaps"][0]["vocabulary_link_preserved"] = False
    broken["overlaps"][0]["hash"] = stable_hash({
        k: v for k, v in broken["overlaps"][0].items() if k != "hash"
    })
    with pytest.raises(GrammarPlanError):
        validate_grammar_plan(*inputs, broken)


def test_plan_validation_rejects_reclassified_overlap(inputs):
    plan = selected(inputs)
    broken = copy.deepcopy(plan)
    broken["overlaps"][0]["relationship"] = "exact-span"
    broken["overlaps"][0]["hash"] = stable_hash({
        k: v for k, v in broken["overlaps"][0].items() if k != "hash"
    })
    with pytest.raises(GrammarPlanError):
        validate_grammar_plan(*inputs, broken)
