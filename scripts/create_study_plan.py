#!/usr/bin/env python3
"""Create deterministic dictionary-only study-item annotation-plan JSON."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.study_plan import (  # noqa: E402
    StudyPlanConfig,
    create_annotation_plan,
    load_vocabulary_report,
    write_annotation_plan,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_vocabulary_json", type=Path)
    parser.add_argument("output_plan_json", type=Path)
    parser.add_argument(
        "--per-chapter-limit",
        type=int,
        default=10,
        help="Maximum unique study items selected by primary chapter (default: 10)",
    )
    args = parser.parse_args()
    plan = create_annotation_plan(
        load_vocabulary_report(args.input_vocabulary_json),
        StudyPlanConfig(per_chapter_item_limit=args.per_chapter_limit),
    )
    write_annotation_plan(plan, args.output_plan_json)
    print(
        f"Wrote annotation-plan schema v{plan.schema_version} with "
        f"{len(plan.items)} items and "
        f"{sum(len(item.occurrences) for item in plan.items)} occurrences "
        f"to {args.output_plan_json}"
    )


if __name__ == "__main__":
    main()
