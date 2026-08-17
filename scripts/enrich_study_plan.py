#!/usr/bin/env python3
"""Generate Phase 5 requests and optional local scripted enrichment."""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from furiganalyse.enrichment import (  # noqa: E402
    ScriptedProvider,
    build_enrichment_requests,
    enrich_requests,
    serialize,
)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("canonical_json", type=Path)
    p.add_argument("vocabulary_json", type=Path)
    p.add_argument("annotation_plan_json", type=Path)
    p.add_argument("request_output", type=Path)
    p.add_argument("report_output", type=Path)
    p.add_argument("--scripted-responses", type=Path)
    p.add_argument("--cache-dir", type=Path)
    p.add_argument("--cache-only", action="store_true")
    p.add_argument("--fallback-plan-output", type=Path)
    a = p.parse_args()
    requests = build_enrichment_requests(
        load(a.canonical_json), load(a.vocabulary_json), load(a.annotation_plan_json)
    )
    a.request_output.parent.mkdir(parents=True, exist_ok=True)
    a.request_output.write_text(serialize(requests), encoding="utf-8")
    if a.cache_only and not a.cache_dir:
        p.error("--cache-only requires --cache-dir")
    if a.cache_only and a.scripted_responses:
        p.error("--cache-only cannot be combined with --scripted-responses")
    provider = (
        ScriptedProvider({})
        if a.cache_only
        else ScriptedProvider(load(a.scripted_responses))
        if a.scripted_responses
        else None
    )
    report = enrich_requests(requests, provider, a.cache_dir)
    a.report_output.parent.mkdir(parents=True, exist_ok=True)
    a.report_output.write_text(serialize(report), encoding="utf-8")
    if a.fallback_plan_output:
        a.fallback_plan_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(a.annotation_plan_json, a.fallback_plan_output)
    print(
        f"Wrote {len(requests['requests'])} requests and {len(report['results'])} results"
    )


if __name__ == "__main__":
    main()
