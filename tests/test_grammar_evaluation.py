import copy
import json
from pathlib import Path

import pytest

from furiganalyse.grammar_evaluation import (
    GrammarEvaluationError,
    PRIMARY_RULE_IDS,
    evaluate_grammar,
    load_json,
    prepare_corpus,
    prepare_rule_control,
    safe_evaluate,
    serialize_evaluation,
    stable_hash,
    validate_corpus,
    validate_evaluation_report,
)
from furiganalyse.grammar_analysis import detect_grammar
from scripts.build_phase7_evaluation_fixture import build_inputs

ROOT = Path(__file__).resolve().parents[1]
@pytest.fixture
def inputs():
    spec = load_json(ROOT / "tests/fixtures/phase7-evaluation-source-v1.json")
    book, vocabulary, plan, _case_sources = build_inputs(spec)
    dataset = load_json(ROOT / "tests/fixtures/phase7-grammar-rules-v1.json")
    return (
        book, vocabulary, plan, detect_grammar(book, vocabulary, plan, dataset),
        dataset,
        load_json(ROOT / "tests/fixtures/phase7-evaluation-corpus-v1.json"),
        load_json(ROOT / "tests/fixtures/phase7-evaluation-control-v1.json"),
    )


def _control(disabled):
    return prepare_rule_control({
        "schema_version": 1,
        "id": "phase7-evaluation-control-test",
        "fixture_notice": "Synthetic local evaluation rule control.",
        "disabled_rule_ids": disabled,
        "hash": "",
    })


def test_baseline_metrics_and_per_rule_recall(inputs):
    report = evaluate_grammar(*inputs)
    metrics = report["metrics"]
    assert (metrics["true_positive_count"], metrics["false_positive_count"]) == (20, 0)
    assert (metrics["false_negative_count"], metrics["true_negative_count"]) == (0, 12)
    assert metrics["precision"] == {"numerator": 20, "denominator": 20}
    assert metrics["recall"] == {"numerator": 20, "denominator": 20}
    assert all(item["recall"] == {"numerator": 4, "denominator": 4} for item in metrics["per_rule"])
    assert report["disabled_rule_ids"] == ["grammar-rule-0006"]
    validate_evaluation_report(report)


def test_ground_truth_has_exact_required_counts_and_categories(inputs):
    corpus = inputs[5]
    positives = [case for case in corpus["cases"] if case["kind"] == "positive"]
    negatives = [case for case in corpus["cases"] if case["kind"] == "negative"]
    assert len(positives) == 20
    assert len(negatives) == 13
    assert {case["category"] for case in negatives} == {
        "sentence-boundary-separation", "block-boundary-separation",
        "chapter-boundary-separation", "punctuation-interruption",
        "incomplete-formation", "ordinary-lexical-text",
        "jmdict-lexical-expression", "proper-name-adjacency",
        "publisher-ruby-covered", "publisher-ruby-adjacency",
        "rt-rp-only-text", "shorter-competing-pattern",
        "whitespace-interruption",
    }
    assert all(sum(case["rule_id"] == rule for case in positives) == 4 for rule in PRIMARY_RULE_IDS)
    validate_corpus(inputs[5], inputs[0], inputs[1], inputs[2], inputs[4], inputs[3])


@pytest.mark.parametrize("rule_id", PRIMARY_RULE_IDS)
def test_each_primary_rule_can_be_disabled_without_changing_other_results(inputs, rule_id):
    baseline = evaluate_grammar(*inputs)
    disabled = evaluate_grammar(*inputs[:-1], _control([rule_id, "grammar-rule-0006"]))
    assert len(disabled["excluded_case_ids"]) == 4
    assert disabled["metrics"]["true_positive_count"] == 16
    assert disabled["metrics"]["false_positive_count"] == 0
    baseline_by_case = {item["case_id"]: item for item in baseline["results"]}
    for result in disabled["results"]:
        assert result == baseline_by_case[result["case_id"]]


def test_mechanics_disable_and_reenable_do_not_change_primary_results(inputs):
    baseline = evaluate_grammar(*inputs)
    enabled = evaluate_grammar(*inputs[:-1], _control([]))
    baseline_primary = [item for item in baseline["results"] if item["classification"] == "positive"]
    enabled_primary = [item for item in enabled["results"] if item["classification"] == "positive"]
    assert enabled_primary == baseline_primary
    assert enabled["metrics"]["true_positive_count"] == 20


def test_exact_offsets_hashes_order_and_serialization(inputs):
    first = evaluate_grammar(*inputs)
    second = evaluate_grammar(*inputs)
    assert serialize_evaluation(first) == serialize_evaluation(second)
    assert first["hash"] == stable_hash({key: value for key, value in first.items() if key != "hash"})
    assert [item["case_id"] for item in first["results"]] == [case["id"] for case in inputs[5]["cases"]]


@pytest.mark.parametrize("mutation,reason", [
    ("unknown-rule", "unknown-rule"),
    ("duplicate-rule", "duplicate-disabled-rule"),
    ("stale-corpus", "stale-corpus-hash"),
    ("offset", "invalid-expected-offset"),
])
def test_invalid_controls_and_ground_truth_fail_safely(inputs, mutation, reason):
    values = list(copy.deepcopy(inputs))
    if mutation == "unknown-rule":
        values[6] = _control(["grammar-rule-0006"])
        values[6]["disabled_rule_ids"] = ["missing-rule"]
        values[6]["hash"] = stable_hash({key: value for key, value in values[6].items() if key != "hash"})
    elif mutation == "duplicate-rule":
        values[6] = _control(["grammar-rule-0006"])
        values[6]["disabled_rule_ids"] *= 2
        values[6]["hash"] = stable_hash({key: value for key, value in values[6].items() if key != "hash"})
    elif mutation == "stale-corpus":
        values[5]["source_hashes"]["canonical_book"] = "0" * 64
        values[5] = prepare_corpus(values[5])
    else:
        values[5]["cases"][0]["sentence_end"] += 1
        values[5] = prepare_corpus(values[5])
    report = safe_evaluate(*values)
    assert report["results"] == []
    assert report["diagnostics"][0]["reason"] == reason


def test_dataset_and_source_mismatch_are_rejected(inputs):
    values = list(copy.deepcopy(inputs))
    values[4]["dataset_version"] = "stale"
    with pytest.raises(GrammarEvaluationError):
        evaluate_grammar(*values)
    values = list(copy.deepcopy(inputs))
    values[2]["book_id"] = "other"
    report = safe_evaluate(*values)
    assert report["diagnostics"][0]["reason"] == "source-mismatch"


def test_disabled_and_corrupt_modes_are_empty(inputs):
    disabled = safe_evaluate(*inputs, disabled=True)
    assert disabled["results"] == [] and disabled["metrics"] is None
    assert disabled["diagnostics"][0]["reason"] == "disabled"
    corrupt = safe_evaluate(inputs[0], inputs[1], inputs[2], {}, inputs[4], inputs[5], inputs[6])
    assert corrupt["results"] == []
    assert corrupt["diagnostics"][0]["reason"] in {"corrupt-corpus", "invalid-input"}


def test_inputs_and_approved_phase7_checksum_are_unchanged(inputs):
    before = [json.dumps(value, ensure_ascii=False, sort_keys=True) for value in inputs]
    evaluate_grammar(*inputs)
    assert [json.dumps(value, ensure_ascii=False, sort_keys=True) for value in inputs] == before
    import hashlib
    epub = ROOT / "artifacts/phase7/epub/run-a.epub"
    assert hashlib.sha256(epub.read_bytes()).hexdigest() == "df4c4bf0f072c01ac0a8d8aff316ee92613760c1822274cecd7ec9ce409a9619"
