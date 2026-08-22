#!/usr/bin/env python3
"""Build deterministic metadata for the Phase 8 adaptive EPUB fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

from furiganalyse.adaptive_epub import build_package_metadata, load_json, serialize_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-epub", required=True, type=Path)
    parser.add_argument("--rendering-report", required=True, type=Path)
    parser.add_argument("--adaptive-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    metadata = build_package_metadata(
        args.base_epub, load_json(args.rendering_report), args.adaptive_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialize_report(metadata), encoding="utf-8")


if __name__ == "__main__":
    main()
