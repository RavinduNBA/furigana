#!/usr/bin/env python3
"""Build compact reviewed cases for Phase 8 adaptive EPUB packaging."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from furiganalyse.assistance_density import stable_hash


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    summary = report["structural_summary"]
    value = {
        "schema_version": 1,
        "id": "phase8-adaptive-epub-review-cases-v1",
        "output_epub_sha256": report["output_epub_sha256"],
        "archive_member_order": summary["archive_member_order"],
        "navigation": summary["navigation"],
        "counts": {
            key: summary[key] for key in (
                "rendering_result_count", "generated_reading_count",
                "displayed_meaning_count", "study_forward_links",
                "study_backlinks", "grammar_forward_links", "grammar_backlinks",
                "grammar_notes", "grammar_contexts",
            )
        },
        "publisher_ruby": summary["publisher_ruby"],
        "rendering_diagnostics": summary["rendering_diagnostic_references"],
        "qualifications": [
            "synthetic-adaptive-assistance-fixture",
            "not-pedagogically-validated",
            "suppression-does-not-delete-source-evidence",
        ],
    }
    value["hash"] = stable_hash(value)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
