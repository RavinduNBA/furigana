#!/usr/bin/env python3
"""Write a deterministic structural report for a Phase 7 grammar EPUB."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.grammar_epub import validate_archive  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epub", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--vocabulary-only", action="store_true")
    args = parser.parse_args()
    report = validate_archive(args.epub, grammar=not args.vocabulary_only)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Validated deterministic EPUB with {report['member_count']} members")


if __name__ == "__main__":
    main()
