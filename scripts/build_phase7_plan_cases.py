#!/usr/bin/env python3
"""Build deterministic stale-input cases for the Phase 7 grammar-plan gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--grammar-report", required=True)
    parser.add_argument("--stale-output", required=True)
    args = parser.parse_args()
    report = json.loads(Path(args.grammar_report).read_text(encoding="utf-8"))
    report["dataset"]["rules"][0]["hash"] = "0" * 64
    output = Path(args.stale_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
