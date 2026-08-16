#!/usr/bin/env python3
"""Write deterministic canonical book JSON from an EPUB."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.book_analysis import extract_book, write_book_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_epub", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()

    book = extract_book(args.input_epub)
    write_book_json(book, args.output_json)
    print(
        f"Wrote schema v{book.schema_version} analysis for "
        f"{len(book.chapters)} chapters to {args.output_json}"
    )


if __name__ == "__main__":
    main()
