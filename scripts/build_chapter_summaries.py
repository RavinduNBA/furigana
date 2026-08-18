#!/usr/bin/env python3
"""Build Phase 6 chapter packets, explicit summaries, and bounded retrieval."""

from __future__ import annotations

import argparse
from pathlib import Path

from furiganalyse.book_context import serialize
from furiganalyse.chapter_summaries import (
    build_chapter_packets,
    build_summary_report,
    disabled_summaries,
    load_json,
    retrieve_summaries,
    safe_failure,
)


def _write(path, value):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialize(value), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    packets = commands.add_parser("packets")
    for name in ("index", "evidence", "terminology", "output"):
        packets.add_argument(name)
    report = commands.add_parser("report")
    for name in ("packets", "registry", "output"):
        report.add_argument(name)
    retrieve = commands.add_parser("retrieve")
    for name in ("packets", "report", "queries", "output"):
        retrieve.add_argument(name)
    fallback = commands.add_parser("fallback")
    fallback.add_argument("plan")
    fallback.add_argument("report")
    fallback.add_argument("fallback_plan")
    fallback.add_argument("--reason", default="disabled", choices=[
        "disabled", "stale-packet-hash", "invalid-registry", "corrupt-registry",
        "unknown-chapter-or-packet",
    ])
    args = parser.parse_args()
    if args.command == "packets":
        value = build_chapter_packets(
            load_json(args.index), load_json(args.evidence), load_json(args.terminology)
        )
        _write(args.output, value)
    elif args.command == "report":
        _write(args.output, build_summary_report(load_json(args.packets), load_json(args.registry)))
    elif args.command == "retrieve":
        _write(args.output, retrieve_summaries(
            load_json(args.packets), load_json(args.report), load_json(args.queries)
        ))
    else:
        plan = load_json(args.plan)
        value, unchanged = (
            disabled_summaries(plan)
            if args.reason == "disabled"
            else safe_failure(plan, args.reason)
        )
        _write(args.report, value)
        _write(args.fallback_plan, unchanged)


if __name__ == "__main__":
    main()
