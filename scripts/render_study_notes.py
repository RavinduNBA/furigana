#!/usr/bin/env python3
"""Render deterministic standalone study-note XHTML from an annotation plan."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.study_notes import load_annotation_plan, write_study_notes  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_plan_json", type=Path)
    parser.add_argument("output_xhtml", type=Path)
    parser.add_argument("--title", default="Study Notes")
    args = parser.parse_args()
    plan = load_annotation_plan(args.input_plan_json)
    write_study_notes(plan, args.output_xhtml, args.title)
    print(
        f"Wrote study-note XHTML with {len(plan['items'])} notes "
        f"to {args.output_xhtml}"
    )


if __name__ == "__main__":
    main()
