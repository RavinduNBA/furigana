#!/usr/bin/env python3
"""Render linked chapter copies and study notes without packaging an EPUB."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.linked_output import (  # noqa: E402
    create_linked_output,
    load_json,
    write_linked_output,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_epub_or_directory", type=Path)
    parser.add_argument("canonical_json", type=Path)
    parser.add_argument("annotation_plan_json", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    output = create_linked_output(
        args.input_epub_or_directory,
        load_json(args.canonical_json),
        load_json(args.annotation_plan_json),
    )
    write_linked_output(output, args.output_directory)
    print(
        f"Wrote {len(output.files)} linked XHTML documents to "
        f"{args.output_directory}"
    )


if __name__ == "__main__":
    main()
