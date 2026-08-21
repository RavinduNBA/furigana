#!/usr/bin/env python3
"""Build deterministic invalid Phase 8 inputs for safe-path regression."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from furiganalyse.learner_profile import load_json, stable_hash


def _rehash(value):
    value["hash"] = stable_hash({key: item for key, item in value.items() if key != "hash"})
    return value


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--exposure-history", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    profile = load_json(args.profile)
    exposure = load_json(args.exposure_history)

    stale = copy.deepcopy(profile)
    stale["source_references"]["vocabulary_hash"] = "0" * 64
    _write(args.output_dir / "stale-profile.json", _rehash(stale))

    invalid = copy.deepcopy(profile)
    invalid["reading_assistance_policy"]["state"] = "invalid-reading-state"
    _write(args.output_dir / "invalid-profile.json", _rehash(invalid))

    unknown = copy.deepcopy(profile)
    unknown["overrides"][0]["target_id"] = "study-item-9999"
    _rehash(unknown["overrides"][0])
    _write(args.output_dir / "unknown-override-profile.json", _rehash(unknown))

    duplicate = copy.deepcopy(profile)
    extra = copy.deepcopy(duplicate["overrides"][0])
    extra["id"] = "phase8-override-0099"
    duplicate["overrides"].append(_rehash(extra))
    _write(args.output_dir / "duplicate-override-profile.json", _rehash(duplicate))

    publisher = copy.deepcopy(profile)
    publisher["reading_assistance_policy"]["state"] = "suppress-publisher-ruby"
    _write(args.output_dir / "publisher-suppression-profile.json", _rehash(publisher))

    negative = copy.deepcopy(exposure)
    negative["records"][0]["count"] = -1
    _rehash(negative["records"][0])
    _write(args.output_dir / "negative-exposure.json", _rehash(negative))

    duplicate_exposure = copy.deepcopy(exposure)
    extra_exposure = copy.deepcopy(duplicate_exposure["records"][0])
    extra_exposure["id"] = "phase8-exposure-0099"
    duplicate_exposure["records"].append(_rehash(extra_exposure))
    _write(args.output_dir / "duplicate-exposure.json", _rehash(duplicate_exposure))

    dimension = copy.deepcopy(exposure)
    dimension["records"][0]["dimension"] = "grammar"
    _rehash(dimension["records"][0])
    _write(args.output_dir / "dimension-mismatch-exposure.json", _rehash(dimension))

    (args.output_dir / "corrupt-profile.json").write_text("{", encoding="utf-8")


if __name__ == "__main__":
    main()
