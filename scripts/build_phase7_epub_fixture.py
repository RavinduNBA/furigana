#!/usr/bin/env python3
"""Build the deterministic legal Phase 7 vocabulary-only EPUB fixture."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.grammar_epub import build_vocabulary_fixture, validate_archive  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    files = build_vocabulary_fixture(args.source_dir, args.output)
    validate_archive(args.output, grammar=False)
    print(f"Wrote deterministic Phase 7 vocabulary EPUB with {len(files)} members")


if __name__ == "__main__":
    main()
