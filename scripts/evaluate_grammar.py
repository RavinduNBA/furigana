#!/usr/bin/env python3
"""Evaluate deterministic grammar output against explicit synthetic ground truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from furiganalyse.grammar_evaluation import (
    evaluate_grammar,
    load_json,
    safe_evaluate,
    serialize_evaluation,
)


def _safe_load(path: str | None) -> dict:
    if not path:
        return {}
    try:
        return load_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book")
    parser.add_argument("--vocabulary")
    parser.add_argument("--annotation-plan")
    parser.add_argument("--grammar-report")
    parser.add_argument("--dataset")
    parser.add_argument("--corpus")
    parser.add_argument("--rule-control")
    parser.add_argument("--output", required=True)
    parser.add_argument("--disabled", action="store_true")
    parser.add_argument("--safe", action="store_true")
    args = parser.parse_args()
    values = [
        _safe_load(args.book), _safe_load(args.vocabulary),
        _safe_load(args.annotation_plan), _safe_load(args.grammar_report),
        _safe_load(args.dataset), _safe_load(args.corpus),
        _safe_load(args.rule_control),
    ]
    if args.disabled or args.safe:
        report = safe_evaluate(*values, disabled=args.disabled)
    else:
        report = evaluate_grammar(*values)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialize_evaluation(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
