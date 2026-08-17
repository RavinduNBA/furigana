#!/usr/bin/env python3
"""Apply validated Phase 5 results to a Phase 4 annotation plan."""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.enriched_plan import apply_enrichment  # noqa: E402
from furiganalyse.enrichment import serialize  # noqa: E402


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotation_plan", type=Path)
    parser.add_argument("request_report", type=Path)
    parser.add_argument("enrichment_report", type=Path)
    parser.add_argument("enriched_output", type=Path)
    parser.add_argument("fallback_output", type=Path)
    args = parser.parse_args()
    enriched, diagnostics = apply_enrichment(
        load(args.annotation_plan),
        load(args.request_report),
        load(args.enrichment_report),
    )
    for path in (args.enriched_output, args.fallback_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.annotation_plan, args.fallback_output)
    if enriched is None:
        shutil.copyfile(args.annotation_plan, args.enriched_output)
        accepted = 0
    else:
        args.enriched_output.write_text(serialize(enriched), encoding="utf-8")
        accepted = len(enriched["enrichments"])
    print(f"Applied {accepted} enrichments with {len(diagnostics)} fallbacks")


if __name__ == "__main__":
    main()
