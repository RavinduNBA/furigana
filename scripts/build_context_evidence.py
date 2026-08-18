#!/usr/bin/env python3
"""Build deterministic recurring-term and proper-name evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

from furiganalyse.book_context import serialize
from furiganalyse.context_evidence import (
    build_evidence_report,
    disabled_evidence,
    load_json,
    safe_failure,
)


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("index")
    build.add_argument("vocabulary")
    build.add_argument("plan")
    build.add_argument("output")
    build.add_argument("--minimum-occurrences", type=int, default=2)
    fallback = subparsers.add_parser("fallback")
    fallback.add_argument("plan")
    fallback.add_argument("report")
    fallback.add_argument("fallback_plan")
    fallback.add_argument(
        "--reason",
        choices=[
            "disabled",
            "invalid-input",
            "schema-mismatch",
            "source-mismatch",
            "corrupt-input",
            "unsupported-version",
        ],
        default="disabled",
    )
    args = parser.parse_args()
    if args.command == "build":
        value = build_evidence_report(
            load_json(args.index),
            load_json(args.vocabulary),
            load_json(args.plan),
            minimum_occurrences=args.minimum_occurrences,
        )
        output_path = args.output
    else:
        plan = load_json(args.plan)
        if args.reason == "disabled":
            value, unchanged = disabled_evidence(plan)
        else:
            value, unchanged = safe_failure(plan, args.reason)
        fallback = Path(args.fallback_plan)
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text(serialize(unchanged), encoding="utf-8")
        output_path = args.report
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialize(value), encoding="utf-8")


if __name__ == "__main__":
    main()
