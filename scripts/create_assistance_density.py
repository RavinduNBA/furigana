#!/usr/bin/env python3
"""Create a deterministic Phase 8 per-occurrence assistance-density plan."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from furiganalyse.assistance_density import (
    AssistanceDensityError,
    build_density_report,
    load_json,
    safe_build_density_report,
    serialize_density_report,
)


def _load(path: Path | None, *, optional: bool = False):
    if path is None and optional:
        return None
    if path is None:
        raise AssistanceDensityError("Missing density input")
    return load_json(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-book", type=Path, required=True)
    parser.add_argument("--annotation-plan", type=Path, required=True)
    parser.add_argument("--grammar-plan", type=Path)
    parser.add_argument("--assistance-report", type=Path)
    parser.add_argument("--density-policies", type=Path)
    parser.add_argument("--policy-id")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fallback-plan-output", type=Path)
    parser.add_argument("--fallback-grammar-plan-output", type=Path)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--safe", action="store_true")
    args = parser.parse_args()

    failure_reason = None
    try:
        book = _load(args.canonical_book)
        annotation_plan = _load(args.annotation_plan)
        grammar_plan = _load(args.grammar_plan, optional=True)
        assistance = _load(args.assistance_report, optional=True)
        policies = _load(args.density_policies, optional=True)
    except (OSError, json.JSONDecodeError, AssistanceDensityError):
        if not args.safe:
            raise
        book, annotation_plan = {}, {}
        grammar_plan = assistance = policies = None
        failure_reason = "corrupt-input"

    if args.safe:
        report = safe_build_density_report(
            book, annotation_plan, grammar_plan, assistance, policies,
            policy_id=args.policy_id, enabled=args.enabled,
            failure_reason=failure_reason,
        )
    else:
        report = build_density_report(
            book, annotation_plan, grammar_plan, assistance, policies,
            policy_id=args.policy_id, enabled=args.enabled,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialize_density_report(report), encoding="utf-8")

    if not report["occurrence_plans"]:
        if args.fallback_plan_output:
            args.fallback_plan_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.annotation_plan, args.fallback_plan_output)
        if args.fallback_grammar_plan_output and args.grammar_plan:
            args.fallback_grammar_plan_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.grammar_plan, args.fallback_grammar_plan_output)


if __name__ == "__main__":
    main()
