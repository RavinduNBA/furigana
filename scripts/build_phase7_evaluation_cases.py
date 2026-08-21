#!/usr/bin/env python3
"""Build deterministic rule-control and safe-failure evaluation artifacts."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path

from furiganalyse.grammar_evaluation import (
    PRIMARY_RULE_IDS,
    evaluate_grammar,
    load_json,
    prepare_corpus,
    prepare_rule_control,
    safe_evaluate,
    serialize_evaluation,
    stable_hash,
)


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_evaluation(value), encoding="utf-8")


def _control(disabled: list[str], name: str) -> dict:
    return prepare_rule_control({
        "schema_version": 1, "id": name,
        "fixture_notice": "Synthetic local evaluation rule control.",
        "disabled_rule_ids": disabled, "hash": "",
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--control", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--matrix-output")
    args = parser.parse_args()
    source = Path(args.input_dir)
    values = [
        load_json(source / "book.json"), load_json(source / "vocabulary.json"),
        load_json(source / "annotation-plan.json"), load_json(source / "grammar.json"),
        load_json(args.dataset), load_json(args.corpus), load_json(args.control),
    ]
    output = Path(args.output_dir)
    baseline = evaluate_grammar(*values)
    baseline_results = {item["case_id"]: item["hash"] for item in baseline["results"]}
    matrix_rows = []
    for rule_id in PRIMARY_RULE_IDS:
        control = _control([rule_id, "grammar-rule-0006"], f"phase7-disable-{rule_id}")
        report = evaluate_grammar(*values[:-1], control)
        unaffected = {item["case_id"]: item["hash"] for item in report["results"]}
        if any(baseline_results[case_id] != value for case_id, value in unaffected.items()):
            raise SystemExit("unaffected result changed")
        directory = output / rule_id
        _write(directory / "control.json", control)
        _write(directory / "evaluation.json", report)
        row = {
            "rule_id": rule_id,
            "excluded_case_ids": report["excluded_case_ids"],
            "unaffected_result_hashes": unaffected,
            "true_positive_count": report["metrics"]["true_positive_count"],
            "true_negative_count": report["metrics"]["true_negative_count"],
        }
        row["hash"] = stable_hash(row)
        matrix_rows.append(row)
    reenabled = evaluate_grammar(*values[:-1], _control([], "phase7-all-rules-enabled"))
    _write(output / "all-rules-enabled.json", reenabled)
    _write(output / "mechanics-disabled.json", baseline)
    _write(output / "disabled.json", safe_evaluate(*values, disabled=True))

    stale = copy.deepcopy(values)
    stale[5]["source_hashes"]["canonical_book"] = "0" * 64
    stale[5] = prepare_corpus(stale[5])
    _write(output / "stale.json", safe_evaluate(*stale))

    invalid = copy.deepcopy(values)
    invalid[5]["cases"][0]["sentence_end"] += 1
    invalid[5] = prepare_corpus(invalid[5])
    _write(output / "invalid.json", safe_evaluate(*invalid))
    corrupt = copy.deepcopy(values)
    corrupt[5] = {}
    _write(output / "corrupt.json", safe_evaluate(*corrupt))

    unknown = copy.deepcopy(values)
    unknown[6]["disabled_rule_ids"] = ["unknown-rule"]
    unknown[6]["hash"] = stable_hash({key: value for key, value in unknown[6].items() if key != "hash"})
    _write(output / "unknown-rule.json", safe_evaluate(*unknown))
    duplicate = copy.deepcopy(values)
    duplicate[6]["disabled_rule_ids"] = ["grammar-rule-0006", "grammar-rule-0006"]
    duplicate[6]["hash"] = stable_hash({key: value for key, value in duplicate[6].items() if key != "hash"})
    _write(output / "duplicate-rule.json", safe_evaluate(*duplicate))

    matrix = {
        "schema_version": 1,
        "id": "phase7-primary-rule-disable-matrix-v1",
        "baseline_report_hash": baseline["hash"],
        "rows": matrix_rows,
        "fixture_notice": "Synthetic rule-disable matrix; not production evidence.",
    }
    matrix["hash"] = stable_hash(matrix)
    _write(Path(args.matrix_output) if args.matrix_output else output / "matrix.json", matrix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
