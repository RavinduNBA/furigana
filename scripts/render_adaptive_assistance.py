#!/usr/bin/env python3
"""Render a validated Phase 8 assistance plan into copied linked XHTML."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from furiganalyse.adaptive_rendering import (
    AdaptiveRenderingError,
    load_json,
    render_adaptive_output,
    safe_render_adaptive_output,
    serialize_report,
    write_output,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--canonical-book", type=Path, required=True)
    parser.add_argument("--annotation-plan", type=Path, required=True)
    parser.add_argument("--grammar-plan", type=Path)
    parser.add_argument("--assistance-report", type=Path, required=True)
    parser.add_argument("--density-plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--safe", action="store_true")
    args = parser.parse_args()

    failure_reason = None
    try:
        inputs = [load_json(path) for path in (
            args.canonical_book,
            args.annotation_plan,
            args.assistance_report,
            args.density_plan,
        )]
        inputs.insert(2, load_json(args.grammar_plan) if args.grammar_plan else None)
    except (OSError, json.JSONDecodeError, AdaptiveRenderingError):
        if not args.safe:
            raise
        inputs = [{}, {}, {}, {}, {}]
        failure_reason = "corrupt-input"

    if args.safe:
        report, files = safe_render_adaptive_output(
            args.source_dir, *inputs, enabled=args.enabled,
            failure_reason=failure_reason,
        )
    else:
        report, files = render_adaptive_output(
            args.source_dir, *inputs, enabled=args.enabled,
        )
    write_output(files, args.output_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(serialize_report(report), encoding="utf-8")


if __name__ == "__main__":
    main()
