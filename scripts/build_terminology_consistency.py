#!/usr/bin/env python3
"""Build an explicit user-approved terminology consistency report."""

from __future__ import annotations

import argparse
from pathlib import Path

from furiganalyse.book_context import serialize
from furiganalyse.terminology import (
    build_consistency_report,
    disabled_terminology,
    load_json,
    safe_failure,
)


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("evidence")
    build.add_argument("index")
    build.add_argument("plan")
    build.add_argument("registry")
    build.add_argument("output")
    fallback = subparsers.add_parser("fallback")
    fallback.add_argument("plan")
    fallback.add_argument("report")
    fallback.add_argument("fallback_plan")
    fallback.add_argument(
        "--reason",
        choices=[
            "disabled",
            "stale-evidence-hash",
            "invalid-registry",
            "corrupt-registry",
            "unknown-evidence-group",
            "duplicate-decision",
        ],
        default="disabled",
    )
    args = parser.parse_args()
    if args.command == "build":
        value = build_consistency_report(
            load_json(args.evidence),
            load_json(args.index),
            load_json(args.plan),
            load_json(args.registry),
        )
        output_path = args.output
    else:
        plan = load_json(args.plan)
        if args.reason == "disabled":
            value, unchanged = disabled_terminology(plan)
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
