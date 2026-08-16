#!/usr/bin/env python3
"""Write deterministic vocabulary-candidate JSON from a canonical EPUB analysis."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.book_analysis import extract_book  # noqa: E402
from furiganalyse.jmdict import SqliteJmdictProvider  # noqa: E402
from furiganalyse.vocabulary_analysis import (  # noqa: E402
    analyze_vocabulary,
    enrich_vocabulary_report,
    write_vocabulary_report,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_epub", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument(
        "--jmdict-index",
        type=Path,
        help="Optional local SQLite JMdict index; dictionary lookup is off by default",
    )
    parser.add_argument(
        "--expressions",
        action="store_true",
        help="Add deterministic adjacent-token expression matches (requires --jmdict-index)",
    )
    args = parser.parse_args()

    if args.expressions and not args.jmdict_index:
        parser.error("--expressions requires --jmdict-index")

    report = analyze_vocabulary(extract_book(args.input_epub))
    if args.jmdict_index:
        provider = SqliteJmdictProvider(args.jmdict_index)
        try:
            report = enrich_vocabulary_report(
                report, provider, include_expressions=args.expressions
            )
        finally:
            provider.close()
    write_vocabulary_report(report, args.output_json)
    print(
        f"Wrote vocabulary schema v{report.schema_version} with "
        f"{len(report.tokens)} tokens and {len(report.candidates)} candidates "
        f"to {args.output_json}"
    )


if __name__ == "__main__":
    main()
