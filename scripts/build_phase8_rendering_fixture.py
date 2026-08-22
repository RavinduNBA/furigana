#!/usr/bin/env python3
"""Build the legal synthetic Phase 8 adaptive-rendering input fixture."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

from furiganalyse.assistance_density import build_density_report, stable_hash
from furiganalyse.learner_profile import build_assistance_report

ROOT = Path(__file__).resolve().parents[1]


def _load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rehash(value: dict) -> dict:
    value.pop("hash", None)
    value["hash"] = stable_hash(value)
    return value


def build(output: Path) -> None:
    if output.exists():
        shutil.rmtree(output)
    book = _load("artifacts/phase7/run-a/inputs/book.json")
    vocabulary = _load("artifacts/phase7/run-a/inputs/vocabulary.json")
    annotation = _load("artifacts/phase7/run-a/inputs/annotation-plan.json")
    grammar = _load("tests/phase7_golden/grammar-plan-v1.json")
    presets = _load("tests/fixtures/phase8/phase8-presets-v1.json")
    profile = _load("tests/fixtures/phase8/phase8-profile-baseline-v1.json")
    exposure = _load("tests/fixtures/phase8/phase8-exposure-history-v1.json")
    policies = _load("tests/fixtures/phase8-density-policies-v1.json")

    synthetic = {
        "study-item-0001": ("よん", "local-synthetic-approved-reading", "to read", "entry-0001", "sense-0001", None),
        "study-item-0002": (None, None, "to forget completely", "entry-0002", "sense-0002", None),
        "study-item-0003": ("まいにちよむ", "local-synthetic-approved-reading", "to read every day", "entry-0003", "sense-0003", None),
        "study-item-0004": ("おもてぶたい", "publisher", "public stage", "entry-0004", "sense-0004", None),
        "study-item-0005": ("まえ", "local-synthetic-approved-name-reading", "Mae (synthetic name)", None, None, "translation-0005"),
    }
    for item in annotation["items"]:
        reading, source, meaning, entry, sense, translation = synthetic[item["id"]]
        item.update({
            "reading": reading,
            "reading_source": source,
            "display_meaning": meaning,
            "selected_entry_id": entry,
            "selected_sense_id": sense,
            "selected_translation_id": translation,
            "adaptive_fixture_provenance": "local-synthetic-rendering-fixture",
        })

    source_hashes = {
        "vocabulary_hash": stable_hash(vocabulary),
        "annotation_plan_hash": stable_hash(annotation),
        "grammar_plan_hash": stable_hash(grammar),
        "preset_dataset_hash": presets["hash"],
    }
    profile["id"] = "phase8-profile-adaptive-rendering"
    profile["label"] = "Synthetic adaptive rendering baseline"
    profile["source_references"] = source_hashes
    _rehash(profile)

    exposure["id"] = "phase8-rendering-exposure-history-v1"
    exposure["source_references"] = {
        "annotation_plan_hash": stable_hash(annotation),
        "grammar_plan_hash": stable_hash(grammar),
    }
    exposure["records"][2]["count"] = 2
    _rehash(exposure["records"][2])
    _rehash(exposure)

    policies = copy.deepcopy(policies)
    policies["dataset_id"] = "furiganalyse-synthetic-rendering-density-policy"
    policies["dataset_version"] = "2026-08-22"
    policies["source_provenance"] = "local-synthetic-rendering-fixture"
    policies["fixture_notice"] = "Synthetic rendering mechanics only; not a pedagogical recommendation."
    n5 = policies["policies"][0]
    n5["id"] = "phase8-rendering-density-n5"
    n5["minimum_per_chapter"]["reading"] = 2
    n5["rationale_codes"] = [
        "synthetic-rendering-coverage-target",
        "independent-dimension-budgets",
        "canonical-source-order",
    ]
    _rehash(n5)
    _rehash(policies)

    assistance = build_assistance_report(
        vocabulary, annotation, grammar, profile, presets, exposure, enabled=True
    )
    density = build_density_report(
        book, annotation, grammar, assistance, policies,
        policy_id=n5["id"], enabled=True,
    )

    values = {
        "book.json": book,
        "annotation-plan.json": annotation,
        "grammar-plan.json": grammar,
        "assistance.json": assistance,
        "density.json": density,
    }
    for name, value in values.items():
        _write(output / name, value)
    source = ROOT / "tests/phase7_golden/grammar-linked-v1"
    shutil.copytree(source, output / "source", dirs_exist_ok=True)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output)


if __name__ == "__main__":
    main()
