#!/usr/bin/env python3
"""Build small deterministic synthetic Phase 8 profile fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from furiganalyse.learner_profile import add_hash, load_json, stable_hash


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _preset(identifier, level, reading, meaning, grammar, rank, threshold):
    return add_hash({
        "id": identifier,
        "schema_version": 1,
        "level": level,
        "reading_default": reading,
        "meaning_default": meaning,
        "grammar_default": grammar,
        "frequency_thresholds": {
            "reading_rank": rank,
            "meaning_rank": rank,
            "grammar_rank": rank,
        },
        "exposure_thresholds": {
            "reading": threshold,
            "meaning": threshold,
            "grammar": threshold,
        },
        "rationale_codes": [
            f"synthetic-{level.lower()}-assistance-defaults",
            f"synthetic-{level.lower()}-exposure-threshold-{threshold}",
        ],
        "source_provenance": "locally curated synthetic Phase 8 preset",
    })


def _override(identifier, target, kind, dimension, state, note):
    return add_hash({
        "id": identifier,
        "target_id": target,
        "target_kind": kind,
        "dimension": dimension,
        "state": state,
        "reviewer_note": note,
        "reviewer": "Synthetic Fixture Reviewer",
        "review_date": "2026-08-21",
        "provenance": "user",
    })


def _profile(identifier, label, source_refs, *, preset_id=None, reading="preset", meaning="preset", grammar="preset", overrides=None, exposure=False):
    return add_hash({
        "schema_version": 1,
        "id": identifier,
        "label": label,
        "preset_id": preset_id,
        "reading_assistance_policy": {"state": reading},
        "meaning_assistance_policy": {"state": meaning},
        "grammar_assistance_policy": {"state": grammar},
        "overrides": overrides or [],
        "exposure_policy": {
            "enabled": exposure,
            "dimensions": ["reading", "meaning", "grammar"] if exposure else [],
        },
        "source_references": source_refs,
        "provenance": "local-synthetic-fixture",
    })


def _exposure(identifier, target, kind, dimension, count, occurrence, chapter, sentence):
    return add_hash({
        "id": identifier,
        "target_id": target,
        "target_kind": kind,
        "dimension": dimension,
        "count": count,
        "occurrence_ids": [occurrence],
        "last_observed": {
            "chapter_id": chapter,
            "sentence_id": sentence,
            "occurrence_id": occurrence,
        },
        "provenance": "explicit-local-history",
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vocabulary", type=Path, required=True)
    parser.add_argument("--annotation-plan", type=Path, required=True)
    parser.add_argument("--grammar-plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    vocabulary = load_json(args.vocabulary)
    plan = load_json(args.annotation_plan)
    grammar = load_json(args.grammar_plan)

    presets = {
        "schema_version": 1,
        "dataset_id": "furiganalyse-synthetic-learner-presets",
        "dataset_version": "2026-08-21",
        "fixture_notice": "Synthetic explainable defaults; not a learner diagnosis or pedagogical validation.",
        "source_provenance": "locally curated copyright-free Phase 8 fixture",
        "presets": [
            _preset("phase8-preset-n5", "N5", "show-reading", "show-meaning", "show-grammar", 100, 3),
            _preset("phase8-preset-n4", "N4", "hide-reading", "show-meaning", "show-grammar", 60, 2),
            _preset("phase8-preset-n3", "N3", "hide-reading", "hide-meaning", "hide-grammar", 30, 1),
        ],
    }
    presets = add_hash(presets)
    source_refs = {
        "vocabulary_hash": stable_hash(vocabulary),
        "annotation_plan_hash": stable_hash(plan),
        "grammar_plan_hash": stable_hash(grammar),
        "preset_dataset_hash": presets["hash"],
    }
    profiles = {
        "show-show": _profile("phase8-profile-show-show", "Show readings and meanings", source_refs, reading="show-reading", meaning="show-meaning", grammar="show-grammar"),
        "show-hide": _profile("phase8-profile-show-hide", "Show readings and hide meanings", source_refs, reading="show-reading", meaning="hide-meaning", grammar="show-grammar"),
        "hide-show": _profile("phase8-profile-hide-show", "Hide readings and show meanings", source_refs, reading="hide-reading", meaning="show-meaning", grammar="hide-grammar"),
        "hide-hide": _profile("phase8-profile-hide-hide", "Hide readings and meanings", source_refs, reading="hide-reading", meaning="hide-meaning", grammar="hide-grammar"),
        "n5": _profile("phase8-profile-n5", "Synthetic N5 defaults", source_refs, preset_id="phase8-preset-n5"),
        "n4": _profile("phase8-profile-n4", "Synthetic N4 defaults", source_refs, preset_id="phase8-preset-n4"),
        "n3": _profile("phase8-profile-n3", "Synthetic N3 defaults", source_refs, preset_id="phase8-preset-n3"),
    }
    overrides = [
        _override("phase8-override-0001", "study-item-0003", "vocabulary", "reading", "hide-reading", "Synthetic reading override."),
        _override("phase8-override-0002", "study-item-0004", "vocabulary", "meaning", "hide-meaning", "Synthetic meaning override."),
        _override("phase8-override-0003", "grammar-item-0002", "grammar", "grammar", "show-grammar", "Synthetic grammar override."),
    ]
    profiles["baseline"] = _profile(
        "phase8-profile-baseline",
        "Synthetic N5 exposure and override baseline",
        source_refs,
        preset_id="phase8-preset-n5",
        overrides=overrides,
        exposure=True,
    )

    records = [
        _exposure("phase8-exposure-0001", "study-item-0001", "vocabulary", "reading", 3, "study-item-0001-occ-0001", "ch-0001", "ch-0001-b-0001-s-0001"),
        _exposure("phase8-exposure-0002", "study-item-0002", "expression", "meaning", 3, "study-item-0002-occ-0001", "ch-0001", "ch-0001-b-0004-s-0001"),
        _exposure("phase8-exposure-0003", "grammar-item-0001", "grammar", "grammar", 3, "grammar-plan-occurrence-0001", "ch-0001", "ch-0001-b-0001-s-0001"),
        _exposure("phase8-exposure-0004", "grammar-item-0002", "grammar", "grammar", 3, "grammar-plan-occurrence-0002", "ch-0001", "ch-0001-b-0002-s-0001"),
    ]
    exposure = add_hash({
        "schema_version": 1,
        "id": "phase8-exposure-history-v1",
        "book_id": plan["book_id"],
        "source_references": {
            "annotation_plan_hash": stable_hash(plan),
            "grammar_plan_hash": stable_hash(grammar),
        },
        "provenance": "explicit-local-history",
        "records": records,
    })

    _write(args.output_dir / "phase8-presets-v1.json", presets)
    for name, profile in profiles.items():
        _write(args.output_dir / f"phase8-profile-{name}-v1.json", profile)
    _write(args.output_dir / "phase8-exposure-history-v1.json", exposure)


if __name__ == "__main__":
    main()
