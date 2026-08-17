#!/usr/bin/env python3
"""Build a deterministic mixed success/fallback report for Phase 5 regression."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.enrichment import serialize  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("success_report", type=Path)
    parser.add_argument("fallback_report", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--accepted", type=int, default=2)
    args = parser.parse_args()
    success = json.loads(args.success_report.read_text(encoding="utf-8"))
    fallback = json.loads(args.fallback_report.read_text(encoding="utf-8"))
    if not 0 <= args.accepted <= len(success["results"]):
        parser.error("--accepted is outside the result range")
    mixed = {
        "schema_version": success["schema_version"],
        "book_id": success["book_id"],
        "results": success["results"][: args.accepted]
        + fallback["results"][args.accepted :],
        "diagnostics": fallback["diagnostics"][args.accepted :],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialize(mixed), encoding="utf-8")
    print(f"Wrote mixed report with {args.accepted} accepted results")


if __name__ == "__main__":
    main()
