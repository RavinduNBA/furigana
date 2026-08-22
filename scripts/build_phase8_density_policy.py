#!/usr/bin/env python3
"""Build the checked-in synthetic Phase 8 density-policy dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from furiganalyse.assistance_density import add_hash


def build() -> dict:
    specifications = (
        ("n5", {"reading": 8, "meaning": 7, "grammar": 6}, 4),
        ("n4", {"reading": 4, "meaning": 4, "grammar": 2}, 3),
        ("n3", {"reading": 2, "meaning": 2, "grammar": 1}, 2),
    )
    policies = []
    for level, targets, maximum in specifications:
        policies.append(add_hash({
            "id": f"phase8-density-{level}",
            "schema_version": 1,
            "preset_id": f"phase8-preset-{level}",
            "targets_per_1000": targets,
            "minimum_per_chapter": {"reading": 1, "meaning": 1, "grammar": 1},
            "maximum_per_chapter": {
                "reading": maximum, "meaning": maximum, "grammar": maximum,
            },
            "rounding_policy": "ceiling-integer",
            "source_order_tie_breaking": "canonical-source-order",
            "publisher_ruby_counting_policy": "preserve-without-generated-reading-budget",
            "explicit_override_handling": "show-forced-hide-suppressed-dimension-only",
            "repeated_occurrence_handling": "first-eligible-source-occurrence-before-later",
            "rationale_codes": [
                f"synthetic-{level}-density-target",
                "independent-dimension-budgets",
                "canonical-source-order",
            ],
            "source_provenance": "local-synthetic-density-fixture",
        }))
    return add_hash({
        "schema_version": 1,
        "dataset_id": "furiganalyse-synthetic-density-policies",
        "dataset_version": "2026-08-21",
        "fixture_notice": "Synthetic deterministic density mechanics fixture; not a pedagogical recommendation.",
        "source_provenance": "local-synthetic-density-fixture",
        "policies": policies,
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
