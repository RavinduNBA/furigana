#!/usr/bin/env python3
"""Build or query the deterministic Phase 6 context index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from furiganalyse.book_context import (
    build_context_index,
    build_retrieval_report,
    disabled_context,
    load_json,
    safe_failure,
    serialize,
)


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("book")
    build.add_argument("vocabulary")
    build.add_argument("plan")
    build.add_argument("output")
    retrieve = subparsers.add_parser("retrieve")
    retrieve.add_argument("index")
    retrieve.add_argument("queries")
    retrieve.add_argument("output")
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
        value = build_context_index(
            load_json(args.book), load_json(args.vocabulary), load_json(args.plan)
        )
    elif args.command == "retrieve":
        index = load_json(args.index)
        queries = json.loads(Path(args.queries).read_text(encoding="utf-8"))
        if not isinstance(queries, list):
            raise SystemExit("Queries JSON must be a list")
        value = build_retrieval_report(index, queries)
    else:
        plan = load_json(args.plan)
        if args.reason == "disabled":
            value, unchanged_plan = disabled_context(plan)
        else:
            value, unchanged_plan = safe_failure(plan, args.reason)
        fallback_plan = Path(args.fallback_plan)
        fallback_plan.parent.mkdir(parents=True, exist_ok=True)
        fallback_plan.write_text(serialize(unchanged_plan), encoding="utf-8")
    output = Path(args.report if args.command == "fallback" else args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialize(value), encoding="utf-8")


if __name__ == "__main__":
    main()
