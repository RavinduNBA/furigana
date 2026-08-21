#!/usr/bin/env python3
"""Build deterministic Phase 8 density comparison, review, and failure inputs."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from furiganalyse.assistance_density import stable_hash


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rehash(value):
    value["hash"] = stable_hash({key: item for key, item in value.items() if key != "hash"})
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--assistance", type=Path, required=True)
    parser.add_argument("--n5", type=Path, required=True)
    parser.add_argument("--n4", type=Path, required=True)
    parser.add_argument("--n3", type=Path, required=True)
    parser.add_argument("--annotation-plan", type=Path, required=True)
    parser.add_argument("--grammar-plan", type=Path, required=True)
    parser.add_argument("--policies", type=Path, required=True)
    parser.add_argument("--comparison-output", type=Path, required=True)
    parser.add_argument("--review-output", type=Path, required=True)
    parser.add_argument("--failure-dir", type=Path, required=True)
    args = parser.parse_args()

    baseline = load(args.baseline)
    assistance = load(args.assistance)
    reports = [(level, load(path)) for level, path in (
        ("N5", args.n5), ("N4", args.n4), ("N3", args.n3)
    )]
    comparison = {
        "schema_version": 1,
        "fixture_notice": "Synthetic density comparison; not a pedagogical recommendation.",
        "profiles": [{
            "level": level,
            "policy_id": report["policy"]["policy_id"],
            "report_hash": report["hash"],
            "selected_counts": {
                dimension: sum(
                    chapter["selected_action_counts"][dimension]
                    for chapter in report["chapter_summaries"]
                ) for dimension in ("reading", "meaning", "grammar")
            },
        } for level, report in reports],
    }
    comparison["hash"] = stable_hash(comparison)
    write(args.comparison_output, comparison)

    plans = {value["source_occurrence_id"]: value for value in baseline["occurrence_plans"]}
    review = {
        "schema_version": 1,
        "fixture_notice": "Synthetic manually reviewed density mechanics cases.",
        "character_counts": {
            value["chapter_id"]: value["canonical_character_count"]
            for value in baseline["chapter_summaries"]
        },
        "cases": [{
            "id": f"density-review-case-{number:04d}",
            "source_occurrence_id": occurrence_id,
            "planned_assistance": plans[occurrence_id]["planned_assistance"],
            "density_decisions": plans[occurrence_id]["density_decisions"],
            "rationale_codes": plans[occurrence_id]["rationale_codes"],
        } for number, occurrence_id in enumerate((
            "study-item-0001-occ-0001",
            "study-item-0003-occ-0001",
            "study-item-0004-occ-0001",
            "grammar-plan-occurrence-0002",
            "grammar-plan-occurrence-0003",
            "grammar-plan-occurrence-0004",
            "grammar-plan-occurrence-0006",
        ), 1)],
    }
    review["hash"] = stable_hash(review)
    write(args.review_output, review)

    annotation = load(args.annotation_plan)
    grammar = load(args.grammar_plan)
    policies = load(args.policies)

    stale = copy.deepcopy(assistance)
    stale["source_hashes"]["annotation_plan"] = "0" * 64
    rehash(stale)
    write(args.failure_dir / "stale-assistance.json", stale)

    invalid = copy.deepcopy(policies)
    invalid["policies"][0]["targets_per_1000"]["reading"] = -1
    rehash(invalid["policies"][0])
    rehash(invalid)
    write(args.failure_dir / "invalid-policies.json", invalid)

    unknown = copy.deepcopy(assistance)
    unknown["results"][0]["occurrence_ids"] = ["unknown-occurrence"]
    rehash(unknown["results"][0])
    rehash(unknown)
    write(args.failure_dir / "unknown-assistance.json", unknown)

    publisher_plan = copy.deepcopy(annotation)
    publisher_plan["items"][3]["occurrences"][0]["publisher_ruby_id"] = "unknown-publisher-ruby"
    publisher_assistance = copy.deepcopy(assistance)
    publisher_assistance["source_hashes"]["annotation_plan"] = stable_hash(publisher_plan)
    rehash(publisher_assistance)
    write(args.failure_dir / "publisher-conflict-plan.json", publisher_plan)
    write(args.failure_dir / "publisher-conflict-assistance.json", publisher_assistance)
    (args.failure_dir / "publisher-conflict-book.json").unlink(missing_ok=True)

    grammar_conflict = copy.deepcopy(grammar)
    grammar_conflict["occurrences"][0]["link_disposition"] = "density-promoted-link"
    rehash(grammar_conflict["occurrences"][0])
    conflict_assistance = copy.deepcopy(assistance)
    conflict_assistance["source_hashes"]["grammar_plan"] = stable_hash(grammar_conflict)
    rehash(conflict_assistance)
    write(args.failure_dir / "grammar-conflict-plan.json", grammar_conflict)
    write(args.failure_dir / "grammar-conflict-assistance.json", conflict_assistance)
    (args.failure_dir / "corrupt.json").write_text("{", encoding="utf-8")

    write(args.failure_dir / "annotation-plan.json", annotation)


if __name__ == "__main__":
    main()
