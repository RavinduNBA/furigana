#!/usr/bin/env python3
"""Package deterministic linked study notes into an EPUB."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from furiganalyse.epub_packaging import build_study_epub  # noqa: E402
from furiganalyse.linked_output import load_json  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_epub", type=Path)
    p.add_argument("canonical_json", type=Path)
    p.add_argument("annotation_plan_json", type=Path)
    p.add_argument("output_epub", type=Path)
    a = p.parse_args()
    files = build_study_epub(
        a.input_epub,
        load_json(a.canonical_json),
        load_json(a.annotation_plan_json),
        a.output_epub,
    )
    print(
        f"Wrote deterministic study EPUB with {len(files)} members to {a.output_epub}"
    )


if __name__ == "__main__":
    main()
