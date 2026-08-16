#!/usr/bin/env python3
"""Write deterministic vocabulary-candidate JSON from a canonical EPUB analysis."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.book_analysis import extract_book  # noqa: E402
from furiganalyse.vocabulary_analysis import (  # noqa: E402
    analyze_vocabulary,
    write_vocabulary_report,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_epub", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()

    report = analyze_vocabulary(extract_book(args.input_epub))
    write_vocabulary_report(report, args.output_json)
    print(
        f"Wrote vocabulary schema v{report.schema_version} with "
        f"{len(report.tokens)} tokens and {len(report.candidates)} candidates "
        f"to {args.output_json}"
    )


if __name__ == "__main__":
    main()
