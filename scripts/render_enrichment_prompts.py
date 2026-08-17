#!/usr/bin/env python3
"""Render deterministic Phase 5 prompt packets without invoking a provider."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.enrichment import serialize  # noqa: E402
from furiganalyse.enrichment_provider import build_prompt_report  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requests_json", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()
    requests = json.loads(args.requests_json.read_text(encoding="utf-8"))
    report = build_prompt_report(requests)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(serialize(report), encoding="utf-8")
    print(f"Wrote {len(report['prompts'])} deterministic prompts")


if __name__ == "__main__":
    main()
