#!/usr/bin/env python3
"""Package validated Phase 8 adaptive XHTML into a deterministic EPUB."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from furiganalyse.adaptive_epub import (
    AdaptiveEpubError,
    load_json,
    safe_package_adaptive_epub,
    serialize_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-epub", required=True, type=Path)
    parser.add_argument("--rendering-report", type=Path)
    parser.add_argument("--adaptive-dir", type=Path)
    parser.add_argument("--package-metadata", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--safe", action="store_true")
    args = parser.parse_args()

    failure_reason = None
    rendering = metadata = None
    try:
        if args.rendering_report is not None:
            rendering = load_json(args.rendering_report)
        if args.package_metadata is not None:
            metadata = load_json(args.package_metadata)
    except (OSError, json.JSONDecodeError, AdaptiveEpubError):
        if not args.safe:
            raise
        failure_reason = "corrupt-input"

    if not args.safe and (
        not args.enabled or rendering is None or metadata is None
        or args.adaptive_dir is None
    ):
        raise AdaptiveEpubError("invalid-configuration")
    report = safe_package_adaptive_epub(
        args.base_epub,
        rendering,
        args.adaptive_dir,
        metadata,
        args.output,
        enabled=args.enabled,
        failure_reason=failure_reason,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(serialize_report(report), encoding="utf-8")


if __name__ == "__main__":
    main()
