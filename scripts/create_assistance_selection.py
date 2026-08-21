#!/usr/bin/env python3
"""Create a deterministic Phase 8 assistance-selection report."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from furiganalyse.learner_profile import (
    LearnerProfileError,
    build_assistance_report,
    load_json,
    safe_build_assistance_report,
    serialize_assistance_report,
)


def _load(path: Path | None, *, optional: bool = False):
    if path is None and optional:
        return None
    if path is None:
        raise LearnerProfileError("Missing input")
    return load_json(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vocabulary", type=Path, required=True)
    parser.add_argument("--annotation-plan", type=Path, required=True)
    parser.add_argument("--grammar-plan", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--presets", type=Path)
    parser.add_argument("--exposure-history", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fallback-plan-output", type=Path)
    parser.add_argument("--fallback-grammar-plan-output", type=Path)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--safe", action="store_true")
    args = parser.parse_args()

    failure_reason = None
    try:
        vocabulary = _load(args.vocabulary)
        annotation_plan = _load(args.annotation_plan)
        grammar_plan = _load(args.grammar_plan, optional=True)
        profile = _load(args.profile, optional=True)
        presets = _load(args.presets, optional=True)
        exposure = _load(args.exposure_history, optional=True)
    except (OSError, json.JSONDecodeError, LearnerProfileError):
        if not args.safe:
            raise
        vocabulary, annotation_plan = {}, {}
        grammar_plan = profile = presets = exposure = None
        failure_reason = "corrupt-input"

    if args.safe:
        report = safe_build_assistance_report(
            vocabulary,
            annotation_plan,
            grammar_plan,
            profile,
            presets,
            exposure,
            enabled=args.enabled,
            failure_reason=failure_reason,
        )
    else:
        report = build_assistance_report(
            vocabulary,
            annotation_plan,
            grammar_plan,
            profile,
            presets,
            exposure,
            enabled=args.enabled,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialize_assistance_report(report), encoding="utf-8")

    if not report["results"]:
        if args.fallback_plan_output:
            args.fallback_plan_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.annotation_plan, args.fallback_plan_output)
        if args.fallback_grammar_plan_output and args.grammar_plan:
            args.fallback_grammar_plan_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.grammar_plan, args.fallback_grammar_plan_output)


if __name__ == "__main__":
    main()
