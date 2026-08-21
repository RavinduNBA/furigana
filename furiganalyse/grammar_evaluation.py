"""Deterministic scoring for explicit synthetic grammar ground truth."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .grammar_analysis import validate_dataset, validate_grammar_report

SCHEMA_VERSION = 1
CORPUS_SCHEMA_VERSION = 1
CONTROL_SCHEMA_VERSION = 1
DETECTOR_VERSION = "grammar-analysis-v1"
PRIMARY_RULE_IDS = tuple(f"grammar-rule-{value:04d}" for value in range(1, 6))
MECHANICS_RULE_ID = "grammar-rule-0006"
SAFE_TEXT = re.compile(r"^[^<>\x00-\x1f]*$")


class GrammarEvaluationError(ValueError):
    """Raised when evaluation inputs violate deterministic invariants."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def serialize_evaluation(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GrammarEvaluationError("JSON root must be an object")
    return value


def prepare_rule_control(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result["hash"] = stable_hash({key: item for key, item in result.items() if key != "hash"})
    validate_rule_control(result)
    return result


def validate_rule_control(value: dict[str, Any], dataset: dict[str, Any] | None = None) -> None:
    required = {"schema_version", "id", "fixture_notice", "disabled_rule_ids", "hash"}
    if set(value) != required or value.get("schema_version") != CONTROL_SCHEMA_VERSION:
        raise GrammarEvaluationError("unsupported-schema-or-field")
    if not isinstance(value.get("id"), str) or not SAFE_TEXT.fullmatch(value["id"]):
        raise GrammarEvaluationError("invalid-rule-control")
    if "synthetic" not in str(value.get("fixture_notice", "")).lower():
        raise GrammarEvaluationError("invalid-rule-control")
    disabled = value.get("disabled_rule_ids")
    if not isinstance(disabled, list) or len(disabled) != len(set(disabled)):
        raise GrammarEvaluationError("duplicate-disabled-rule")
    known_order = [rule["id"] for rule in dataset["rules"]] if dataset else [*PRIMARY_RULE_IDS, MECHANICS_RULE_ID]
    known = set(known_order)
    if any(rule_id not in known for rule_id in disabled):
        raise GrammarEvaluationError("unknown-rule")
    order = {rule_id: index for index, rule_id in enumerate(known_order)}
    if disabled != sorted(disabled, key=lambda rule_id: order[rule_id]):
        raise GrammarEvaluationError("invalid-rule-control")
    body = {key: item for key, item in value.items() if key != "hash"}
    if value["hash"] != stable_hash(body):
        raise GrammarEvaluationError("invalid-rule-control")


def prepare_corpus(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    for case in result["cases"]:
        case["hash"] = stable_hash({key: item for key, item in case.items() if key != "hash"})
    result["hash"] = stable_hash({key: item for key, item in result.items() if key != "hash"})
    return result


def _source_maps(book: dict[str, Any], vocabulary: dict[str, Any]) -> tuple[dict, dict, dict]:
    sentences = {
        sentence["id"]: (chapter, block, sentence)
        for chapter in book.get("chapters", [])
        for block in chapter.get("blocks", [])
        for sentence in block.get("sentences", [])
    }
    tokens = {token["id"]: token for token in vocabulary.get("tokens", [])}
    ruby = {
        record["id"]: record
        for chapter in book.get("chapters", [])
        for block in chapter.get("blocks", [])
        for record in block.get("publisher_ruby", [])
    }
    return sentences, tokens, ruby


def validate_corpus(
    corpus: dict[str, Any], book: dict[str, Any], vocabulary: dict[str, Any],
    plan: dict[str, Any], dataset: dict[str, Any], report: dict[str, Any],
) -> None:
    required = {
        "schema_version", "id", "version", "fixture_notice", "book_id",
        "source_hashes", "cases", "hash",
    }
    if set(corpus) != required or corpus.get("schema_version") != CORPUS_SCHEMA_VERSION:
        raise GrammarEvaluationError("unsupported-schema-or-field")
    if "synthetic" not in str(corpus.get("fixture_notice", "")).lower():
        raise GrammarEvaluationError("unsafe-fixture-text")
    if corpus.get("book_id") != book.get("book_id"):
        raise GrammarEvaluationError("source-mismatch")
    expected_hashes = {
        "canonical_book": stable_hash(book),
        "vocabulary_report": stable_hash(vocabulary),
        "annotation_plan": stable_hash(plan),
        "grammar_report": stable_hash(report),
        "grammar_dataset": stable_hash(dataset),
    }
    if corpus.get("source_hashes", {}).get("grammar_dataset") != expected_hashes["grammar_dataset"]:
        raise GrammarEvaluationError("dataset-mismatch")
    if corpus.get("source_hashes") != expected_hashes:
        raise GrammarEvaluationError("stale-corpus-hash")
    sentences, tokens, ruby = _source_maps(book, vocabulary)
    rules = {rule["id"]: rule for rule in dataset["rules"]}
    case_keys = {
        "id", "kind", "category", "rule_id", "canonical_key", "surface",
        "chapter_id", "block_id", "sentence_id", "token_ids", "sentence_start",
        "sentence_end", "block_start", "block_end", "expected_confidence",
        "expected_selection_reason", "publisher_ruby_interaction",
        "expected_nonmatch_reason", "publisher_ruby_ids", "hash",
    }
    seen: set[str] = set()
    previous: tuple[str, str, str, int, str] | None = None
    positives = 0
    for index, case in enumerate(corpus.get("cases", []), 1):
        if set(case) != case_keys or case.get("id") != f"grammar-eval-case-{index:04d}":
            raise GrammarEvaluationError("duplicate-or-unstable-case")
        if case["id"] in seen:
            raise GrammarEvaluationError("duplicate-or-unstable-case")
        seen.add(case["id"])
        if case["kind"] not in {"positive", "negative"}:
            raise GrammarEvaluationError("unsupported-case-kind")
        if case["rule_id"] is not None and case["rule_id"] not in rules:
            raise GrammarEvaluationError("unknown-rule")
        if case["sentence_id"] not in sentences:
            raise GrammarEvaluationError("missing-expected-reference")
        chapter, block, sentence = sentences[case["sentence_id"]]
        if case["chapter_id"] != chapter["id"] or case["block_id"] != block["id"]:
            raise GrammarEvaluationError("source-mismatch")
        start, end = case["sentence_start"], case["sentence_end"]
        if not (0 <= start <= end <= len(sentence["text"])):
            raise GrammarEvaluationError("invalid-expected-offset")
        if case["surface"] is not None and sentence["text"][start:end] != case["surface"]:
            raise GrammarEvaluationError("invalid-expected-offset")
        if case["block_start"] != sentence["start"] + start or case["block_end"] != sentence["start"] + end:
            raise GrammarEvaluationError("invalid-expected-offset")
        if any(token_id not in tokens for token_id in case["token_ids"]):
            raise GrammarEvaluationError("missing-expected-reference")
        if any(ruby_id not in ruby for ruby_id in case["publisher_ruby_ids"]):
            raise GrammarEvaluationError("missing-expected-reference")
        if case["kind"] == "positive":
            positives += 1
            if case["rule_id"] not in PRIMARY_RULE_IDS or not case["surface"]:
                raise GrammarEvaluationError("missing-expected-reference")
            rule = rules[case["rule_id"]]
            if case["canonical_key"] != rule["canonical_key"]:
                raise GrammarEvaluationError("dataset-mismatch")
            if case["expected_nonmatch_reason"] is not None:
                raise GrammarEvaluationError("unsupported-case-kind")
        elif case["expected_nonmatch_reason"] is None:
            raise GrammarEvaluationError("missing-expected-reference")
        body = {key: item for key, item in case.items() if key != "hash"}
        if case["hash"] != stable_hash(body):
            raise GrammarEvaluationError("invalid-case-hash")
        order = (case["chapter_id"], case["block_id"], case["sentence_id"], start, case["id"])
        if previous is not None and order < previous:
            raise GrammarEvaluationError("unordered-cases")
        previous = order
    if positives != 20 or len(corpus["cases"]) - positives < 12:
        raise GrammarEvaluationError("invalid-metric-total")
    if any(
        sum(case["kind"] == "positive" and case["rule_id"] == rule_id for case in corpus["cases"]) != 4
        for rule_id in PRIMARY_RULE_IDS
    ):
        raise GrammarEvaluationError("invalid-metric-total")
    body = {key: item for key, item in corpus.items() if key != "hash"}
    if corpus["hash"] != stable_hash(body):
        raise GrammarEvaluationError("stale-corpus-hash")


def _fraction(numerator: int, denominator: int) -> dict[str, int]:
    return {"numerator": numerator, "denominator": denominator}


def evaluate_grammar(
    book: dict[str, Any], vocabulary: dict[str, Any], plan: dict[str, Any],
    grammar_report: dict[str, Any], dataset: dict[str, Any], corpus: dict[str, Any],
    control: dict[str, Any], *, disabled: bool = False,
) -> dict[str, Any]:
    if disabled:
        return _empty_report(book.get("book_id", "unknown"), "disabled")
    if plan.get("schema_version") != 2 or plan.get("book_id") != book.get("book_id"):
        raise GrammarEvaluationError("source-mismatch")
    validate_dataset(dataset)
    validate_grammar_report(book, vocabulary, grammar_report)
    validate_rule_control(control, dataset)
    validate_corpus(corpus, book, vocabulary, plan, dataset, grammar_report)
    disabled_rules = control["disabled_rule_ids"]
    active_rules = [rule["id"] for rule in dataset["rules"] if rule["id"] not in disabled_rules]
    scored_rules = [rule_id for rule_id in PRIMARY_RULE_IDS if rule_id in active_rules]
    actual = [item for item in grammar_report["occurrences"] if item["rule_id"] in active_rules]
    claimed: set[str] = set()
    excluded_case_ids: list[str] = []
    results: list[dict[str, Any]] = []
    tp = fp = fn = tn = 0
    for case in corpus["cases"]:
        if case["kind"] == "positive" and case["rule_id"] in disabled_rules:
            excluded_case_ids.append(case["id"])
            continue
        compatible = [item for item in actual if _matches_case(item, case)]
        if case["kind"] == "positive":
            if len(compatible) == 1:
                outcome, reason = "true-positive", "exact-compatible-match"
                tp += 1
                claimed.add(compatible[0]["id"])
            elif not compatible:
                outcome, reason = "false-negative", "missing-detection"
                fn += 1
            else:
                outcome, reason = "false-positive", "duplicate-actual-match"
                fp += len(compatible)
                claimed.update(item["id"] for item in compatible)
        else:
            if compatible:
                outcome, reason = "false-positive", "unexpected-detection"
                fp += len(compatible)
                claimed.update(item["id"] for item in compatible)
            else:
                outcome = "excluded-mechanics" if case["rule_id"] == MECHANICS_RULE_ID else "true-negative"
                reason = "synthetic-mechanics-disabled" if outcome == "excluded-mechanics" else case["expected_nonmatch_reason"]
                if outcome == "true-negative":
                    tn += 1
        result = {
            "id": case["id"].replace("grammar-eval-case-", "grammar-evaluation-result-"),
            "case_id": case["id"],
            "case_hash": case["hash"],
            "classification": case["kind"],
            "expected_rule_id": case["rule_id"],
            "expected_surface": case["surface"],
            "actual_occurrence_ids": [item["id"] for item in compatible],
            "actual": [{
                "rule_id": item["rule_id"], "surface": item["surface"],
                "chapter_id": item["chapter_id"], "block_id": item["block_id"],
                "sentence_id": item["sentence_id"], "sentence_start": item["sentence_start"],
                "sentence_end": item["sentence_end"], "hash": item["hash"],
            } for item in compatible],
            "outcome": outcome,
            "reason": reason,
        }
        result["hash"] = stable_hash(result)
        results.append(result)
    extras = [item for item in actual if item["rule_id"] in PRIMARY_RULE_IDS and item["id"] not in claimed]
    fp += len(extras)
    diagnostics = []
    for rule_id in disabled_rules:
        diagnostic = {
            "id": f"grammar-evaluation-diagnostic-{len(diagnostics) + 1:04d}",
            "reason": "rule-disabled",
            "rule_id": rule_id,
        }
        diagnostic["hash"] = stable_hash(diagnostic)
        diagnostics.append(diagnostic)
    if extras:
        diagnostic = {
            "id": f"grammar-evaluation-diagnostic-{len(diagnostics) + 1:04d}",
            "reason": "unexpected-detection",
            "occurrence_ids": [item["id"] for item in extras],
        }
        diagnostic["hash"] = stable_hash(diagnostic)
        diagnostics.append(diagnostic)
    negative_count = sum(
        case["kind"] == "negative" and case["rule_id"] != MECHANICS_RULE_ID
        for case in corpus["cases"]
    )
    per_rule = []
    for rule_id in PRIMARY_RULE_IDS:
        expected = sum(case["kind"] == "positive" and case["rule_id"] == rule_id for case in corpus["cases"])
        if rule_id in disabled_rules:
            rule_tp = rule_fp = rule_fn = 0
            scored = 0
        else:
            relevant = [result for result in results if result["classification"] == "positive" and result["expected_rule_id"] == rule_id]
            rule_tp = sum(result["outcome"] == "true-positive" for result in relevant)
            rule_fn = sum(result["outcome"] == "false-negative" for result in relevant)
            rule_fp = sum(result["outcome"] == "false-positive" for result in results if result["expected_rule_id"] == rule_id)
            scored = expected
        per_rule.append({
            "rule_id": rule_id, "active": rule_id not in disabled_rules,
            "expected_positive_count": expected, "scored_positive_count": scored,
            "true_positive_count": rule_tp, "false_positive_count": rule_fp,
            "false_negative_count": rule_fn,
            "precision": _fraction(rule_tp, rule_tp + rule_fp),
            "recall": _fraction(rule_tp, rule_tp + rule_fn),
        })
    scored_count = sum(result["outcome"] != "excluded-mechanics" for result in results)
    metrics = {
        "true_positive_count": tp, "false_positive_count": fp,
        "false_negative_count": fn, "true_negative_count": tn,
        "precision": _fraction(tp, tp + fp), "recall": _fraction(tp, tp + fn),
        "false_positive_rate": _fraction(fp, negative_count),
        "exact_match_accuracy": _fraction(tp + tn, scored_count),
        "per_rule": per_rule,
        "negative_categories": [{
            "category": category,
            "count": sum(case["kind"] == "negative" and case["category"] == category for case in corpus["cases"]),
        } for category in dict.fromkeys(case["category"] for case in corpus["cases"] if case["kind"] == "negative")],
    }
    metrics["hash"] = stable_hash(metrics)
    report = {
        "schema_version": SCHEMA_VERSION,
        "id": "grammar-evaluation-report-v1",
        "book_id": book["book_id"],
        "corpus": {"id": corpus["id"], "version": corpus["version"], "hash": corpus["hash"]},
        "dataset": {
            "id": dataset["dataset_id"], "version": dataset["dataset_version"],
            "provenance": dataset["source_provenance"], "hash": stable_hash(dataset),
        },
        "source_hashes": corpus["source_hashes"],
        "detector_version": DETECTOR_VERSION,
        "configuration": control,
        "active_rule_ids": active_rules,
        "disabled_rule_ids": disabled_rules,
        "scored_rule_ids": scored_rules,
        "excluded_case_ids": excluded_case_ids,
        "results": results,
        "unclaimed_actual_occurrence_ids": [item["id"] for item in extras],
        "metrics": metrics,
        "diagnostics": diagnostics,
    }
    report["hash"] = stable_hash(report)
    validate_evaluation_report(report)
    return report


def _matches_case(item: dict[str, Any], case: dict[str, Any]) -> bool:
    if case["rule_id"] is None:
        return item["sentence_id"] == case["sentence_id"]
    return (
        item["rule_id"] == case["rule_id"]
        and item["surface"] == case["surface"]
        and item["chapter_id"] == case["chapter_id"]
        and item["block_id"] == case["block_id"]
        and item["sentence_id"] == case["sentence_id"]
        and item["sentence_start"] == case["sentence_start"]
        and item["sentence_end"] == case["sentence_end"]
    )


def validate_evaluation_report(report: dict[str, Any]) -> None:
    if report.get("schema_version") != SCHEMA_VERSION:
        raise GrammarEvaluationError("unsupported-schema-or-field")
    if report.get("hash") != stable_hash({key: item for key, item in report.items() if key != "hash"}):
        raise GrammarEvaluationError("invalid-report-hash")
    for result in report.get("results", []):
        if result.get("hash") != stable_hash({key: item for key, item in result.items() if key != "hash"}):
            raise GrammarEvaluationError("invalid-result-hash")
    metrics = report.get("metrics", {})
    if metrics.get("hash") != stable_hash({key: item for key, item in metrics.items() if key != "hash"}):
        raise GrammarEvaluationError("invalid-metrics-hash")
    if metrics["true_positive_count"] + metrics["false_negative_count"] != sum(
        result["classification"] == "positive" for result in report["results"]
    ):
        raise GrammarEvaluationError("invalid-metric-total")


def _empty_report(book_id: str, reason: str) -> dict[str, Any]:
    diagnostic = {"id": "grammar-evaluation-diagnostic-0001", "reason": reason}
    diagnostic["hash"] = stable_hash(diagnostic)
    value = {
        "schema_version": SCHEMA_VERSION, "id": "grammar-evaluation-report-v1",
        "book_id": book_id, "corpus": None, "dataset": None, "source_hashes": {},
        "detector_version": DETECTOR_VERSION, "configuration": None,
        "active_rule_ids": [], "disabled_rule_ids": [], "scored_rule_ids": [],
        "excluded_case_ids": [], "results": [], "unclaimed_actual_occurrence_ids": [],
        "metrics": None, "diagnostics": [diagnostic],
    }
    value["hash"] = stable_hash(value)
    return value


def safe_evaluate(*args: Any, disabled: bool = False) -> dict[str, Any]:
    book = args[0] if args and isinstance(args[0], dict) else {}
    if disabled:
        return _empty_report(book.get("book_id", "unknown"), "disabled")
    if len(args) < 6 or not isinstance(args[5], dict) or not args[5]:
        return _empty_report(book.get("book_id", "unknown"), "corrupt-corpus")
    try:
        return evaluate_grammar(*args)
    except GrammarEvaluationError as error:
        reason = str(error)
        allowed = {
            "unknown-rule", "duplicate-disabled-rule", "stale-corpus-hash",
            "dataset-mismatch", "source-mismatch", "invalid-expected-offset",
            "missing-expected-reference", "unsupported-case-kind",
            "invalid-metric-total", "corrupt-corpus", "unsupported-schema-or-field",
            "invalid-rule-control", "invalid-case-hash", "unordered-cases",
            "duplicate-or-unstable-case", "unsafe-fixture-text",
        }
        return _empty_report(book.get("book_id", "unknown"), reason if reason in allowed else "invalid-input")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _empty_report(book.get("book_id", "unknown"), "corrupt-corpus")
