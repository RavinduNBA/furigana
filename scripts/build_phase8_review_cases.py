#!/usr/bin/env python3
"""Create compact deterministic Phase 8 comparison and review records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from furiganalyse.learner_profile import load_json, stable_hash


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _states(report):
    return [
        {
            "source_item_id": value["source_item_id"],
            "item_kind": value["item_kind"],
            "reading_assistance": value["reading_assistance"],
            "meaning_assistance": value["meaning_assistance"],
            "grammar_assistance": value["grammar_assistance"],
            "publisher_ruby_protection": value["publisher_ruby_protection"],
        }
        for value in report["results"]
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--n5", type=Path, required=True)
    parser.add_argument("--n4", type=Path, required=True)
    parser.add_argument("--n3", type=Path, required=True)
    parser.add_argument("--comparison-output", type=Path, required=True)
    parser.add_argument("--review-output", type=Path, required=True)
    args = parser.parse_args()
    baseline = load_json(args.baseline)
    n5, n4, n3 = (load_json(args.n5), load_json(args.n4), load_json(args.n3))
    comparison = {
        "schema_version": 1,
        "fixture_notice": "Synthetic explainable preset comparison; not learner diagnosis or production validation.",
        "profiles": [
            {"level": level, "profile_id": report["profile"]["id"], "states": _states(report)}
            for level, report in (("N5", n5), ("N4", n4), ("N3", n3))
        ],
    }
    comparison["hash"] = stable_hash(comparison)
    _write(args.comparison_output, comparison)

    by_id = {value["source_item_id"]: value for value in baseline["results"]}
    review = {
        "schema_version": 1,
        "fixture_notice": "Synthetic manual-review references only.",
        "cases": [
            {
                "id": "phase8-review-reading-exposure",
                "result_id": by_id["study-item-0001"]["id"],
                "state": by_id["study-item-0001"]["reading_assistance"],
                "source": by_id["study-item-0001"]["effective_sources"]["reading"],
            },
            {
                "id": "phase8-review-meaning-exposure",
                "result_id": by_id["study-item-0002"]["id"],
                "state": by_id["study-item-0002"]["meaning_assistance"],
                "source": by_id["study-item-0002"]["effective_sources"]["meaning"],
            },
            {
                "id": "phase8-review-publisher-ruby",
                "result_id": by_id["study-item-0004"]["id"],
                "protection": by_id["study-item-0004"]["publisher_ruby_protection"],
            },
            {
                "id": "phase8-review-name-separation",
                "result_id": by_id["study-item-0005"]["id"],
                "item_kind": by_id["study-item-0005"]["item_kind"],
            },
            {
                "id": "phase8-review-grammar-override",
                "result_id": by_id["grammar-item-0002"]["id"],
                "state": by_id["grammar-item-0002"]["grammar_assistance"],
                "source": by_id["grammar-item-0002"]["effective_sources"]["grammar"],
            },
        ],
    }
    review["hash"] = stable_hash(review)
    _write(args.review_output, review)


if __name__ == "__main__":
    main()
