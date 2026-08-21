import copy
import json
from pathlib import Path

import pytest

from furiganalyse.grammar_analysis import (
    GrammarAnalysisError,
    detect_grammar,
    load_json,
    prepare_dataset,
    serialize_grammar_report,
    stable_hash,
    validate_dataset,
    validate_grammar_report,
)
from scripts.build_phase7_fixture import build

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inputs():
    spec = load_json(ROOT / "tests/fixtures/phase7-passages-v1.json")
    book, vocabulary, plan = build(spec)
    dataset = load_json(ROOT / "tests/fixtures/phase7-grammar-rules-v1.json")
    return book, vocabulary, plan, dataset


def test_all_curated_rules_and_repeated_occurrence(inputs):
    report = detect_grammar(*inputs)
    keys = [candidate["canonical_key"] for candidate in report["candidates"]]
    assert keys == ["〜ている", "〜たことがある", "〜ようにする", "〜てしまう", "〜て", "〜なければならない"]
    ongoing = next(value for value in report["candidates"] if value["canonical_key"] == "〜ている")
    assert ongoing["book_count"] == 3
    assert ongoing["chapter_counts"] == [{"chapter_id": "ch-0001", "count": 3}]


def test_exact_offsets_components_and_vocabulary_overlaps(inputs):
    book, vocabulary, plan, dataset = inputs
    report = detect_grammar(book, vocabulary, plan, dataset)
    for occurrence in report["occurrences"]:
        sentence = next(
            sentence for chapter in book["chapters"] for block in chapter["blocks"]
            for sentence in block["sentences"] if sentence["id"] == occurrence["sentence_id"]
        )
        assert sentence["text"][occurrence["sentence_start"]:occurrence["sentence_end"]] == occurrence["surface"]
        assert occurrence["overlapping_candidate_ids"]


def test_boundaries_lexical_expression_and_publisher_ruby(inputs):
    report = detect_grammar(*inputs)
    selected_surfaces = [value["surface"] for value in report["occurrences"]]
    assert "読んでいる" in selected_surfaces
    assert all(value["sentence_id"] != "ch-0001-b-0007-s-0001" for value in report["occurrences"] if value["canonical_key"] == "〜ている")
    reasons = [value["reason"] for value in report["diagnostics"]]
    assert "publisher-ruby-protected" in reasons
    assert "lexical-expression-not-grammar" in reasons
    assert "overlap-rejected-longest-specific-rule" in reasons
    assert any(
        value["publisher_ruby_interaction"] == "adjacent-preserved-publisher-ruby"
        for value in report["occurrences"]
    )
    assert all(
        value["publisher_ruby_interaction"] in {"none", "adjacent-preserved-publisher-ruby"}
        for value in report["occurrences"]
    )


def test_longest_match_wins_over_short_competitor(inputs):
    report = detect_grammar(*inputs)
    first = report["occurrences"][0]
    assert first["surface"] == "読んでいる"
    assert first["canonical_key"] == "〜ている"
    assert any(
        value["rule_id"] == "grammar-rule-0006"
        and value["reason"] == "overlap-rejected-longest-specific-rule"
        for value in report["diagnostics"]
    )


def test_deterministic_serialization_and_validation(inputs):
    first = detect_grammar(*inputs)
    second = detect_grammar(*inputs)
    assert serialize_grammar_report(first) == serialize_grammar_report(second)
    validate_grammar_report(inputs[0], inputs[1], first)
    assert all(value["hash"] == stable_hash({k: v for k, v in value.items() if k != "hash"}) for value in first["occurrences"])


def test_disabled_is_empty_and_preserves_inputs(inputs):
    book, vocabulary, plan, dataset = inputs
    before_vocabulary = json.dumps(vocabulary, sort_keys=True)
    before_plan = json.dumps(plan, sort_keys=True)
    report = detect_grammar(book, vocabulary, plan, dataset, disabled=True)
    assert report["dataset"] is None
    assert report["occurrences"] == report["candidates"] == report["diagnostics"] == []
    assert json.dumps(vocabulary, sort_keys=True) == before_vocabulary
    assert json.dumps(plan, sort_keys=True) == before_plan


@pytest.mark.parametrize("mutation", ["hash", "unsafe", "duplicate", "schema"])
def test_invalid_rule_datasets_are_rejected(inputs, mutation):
    dataset = copy.deepcopy(inputs[3])
    if mutation == "hash":
        dataset["rules"][0]["hash"] = "bad"
    elif mutation == "unsafe":
        dataset["rules"][0]["label"] = "<script>"
    elif mutation == "duplicate":
        dataset["rules"][1]["id"] = dataset["rules"][0]["id"]
    else:
        dataset["schema_version"] = 99
    with pytest.raises(GrammarAnalysisError):
        validate_dataset(dataset)


def test_prepare_dataset_supplies_valid_hashes(inputs):
    dataset = copy.deepcopy(inputs[3])
    for rule in dataset["rules"]:
        rule["hash"] = ""
    prepared = prepare_dataset(dataset)
    validate_dataset(prepared)


@pytest.mark.parametrize("source", ["book", "vocabulary", "plan"])
def test_mismatched_sources_are_rejected(inputs, source):
    book, vocabulary, plan, dataset = copy.deepcopy(inputs)
    {"book": book, "vocabulary": vocabulary, "plan": plan}[source]["book_id"] = "other"
    with pytest.raises(GrammarAnalysisError):
        detect_grammar(book, vocabulary, plan, dataset)


def test_unknown_token_reference_is_rejected(inputs):
    book, vocabulary, plan, dataset = copy.deepcopy(inputs)
    vocabulary["tokens"][0]["sentence_id"] = "missing"
    with pytest.raises(GrammarAnalysisError):
        detect_grammar(book, vocabulary, plan, dataset)


def test_invalid_occurrence_hash_and_overlap_are_rejected(inputs):
    book, vocabulary, plan, dataset = inputs
    report = detect_grammar(book, vocabulary, plan, dataset)
    broken = copy.deepcopy(report)
    broken["occurrences"][0]["hash"] = "bad"
    with pytest.raises(GrammarAnalysisError):
        validate_grammar_report(book, vocabulary, broken)
    broken = copy.deepcopy(report)
    duplicate = copy.deepcopy(broken["occurrences"][0])
    duplicate["id"] = f"grammar-occurrence-{len(broken['occurrences']) + 1:04d}"
    duplicate["hash"] = stable_hash({k: v for k, v in duplicate.items() if k != "hash"})
    broken["occurrences"].append(duplicate)
    with pytest.raises(GrammarAnalysisError):
        validate_grammar_report(book, vocabulary, broken)
