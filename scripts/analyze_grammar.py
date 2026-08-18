#!/usr/bin/env python3
"""Build a deterministic curated grammar-candidate report."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from furiganalyse.grammar_analysis import (
    detect_grammar,
    load_json,
    safe_detect,
    serialize_grammar_report,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--vocabulary", required=True)
    parser.add_argument("--annotation-plan", required=True)
    parser.add_argument("--dataset")
    parser.add_argument("--output", required=True)
    parser.add_argument("--fallback-plan-output")
    parser.add_argument("--disabled", action="store_true")
    parser.add_argument("--safe", action="store_true")
    args = parser.parse_args()

    book = load_json(args.book)
    vocabulary = load_json(args.vocabulary)
    plan = load_json(args.annotation_plan)
    dataset = None
    if args.dataset:
        try:
            dataset = load_json(args.dataset)
        except (OSError, ValueError):
            if not args.safe:
                raise
    if args.safe:
        report = safe_detect(book, vocabulary, plan, dataset, disabled=args.disabled)
    else:
        report = detect_grammar(book, vocabulary, plan, dataset, disabled=args.disabled)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialize_grammar_report(report), encoding="utf-8")
    if args.fallback_plan_output and (args.disabled or report["diagnostics"] and not report["occurrences"]):
        target = Path(args.fallback_plan_output)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.annotation_plan, target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
