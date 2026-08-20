#!/usr/bin/env python3
"""Create deterministic grammar study items and overlap dispositions."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from furiganalyse.grammar_analysis import load_json
from furiganalyse.grammar_plan import (
    build_grammar_plan,
    safe_build_grammar_plan,
    serialize_grammar_plan,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--vocabulary", required=True)
    parser.add_argument("--annotation-plan", required=True)
    parser.add_argument("--grammar-report", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--fallback-plan-output")
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--include-synthetic-mechanics", action="store_true")
    parser.add_argument("--per-chapter-limit", type=int, default=4)
    parser.add_argument("--safe", action="store_true")
    args = parser.parse_args()
    failure_reason = None
    values = []
    for path in (
        args.book,
        args.vocabulary,
        args.annotation_plan,
        args.grammar_report,
        args.dataset,
    ):
        try:
            values.append(load_json(path))
        except (OSError, ValueError):
            if not args.safe:
                raise
            values.append({})
            failure_reason = "corrupt-input"
    options = {
        "enabled": args.enabled,
        "per_chapter_limit": args.per_chapter_limit,
        "include_synthetic_mechanics": args.include_synthetic_mechanics,
    }
    report = (
        safe_build_grammar_plan(*values, **options, _failure_reason=failure_reason)
        if args.safe
        else build_grammar_plan(*values, **options)
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialize_grammar_plan(report), encoding="utf-8")
    if args.fallback_plan_output and (not args.enabled or not report["items"]):
        target = Path(args.fallback_plan_output)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.annotation_plan, target)


if __name__ == "__main__":
    main()
