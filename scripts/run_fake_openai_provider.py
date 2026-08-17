#!/usr/bin/env python3
"""Exercise the OpenAI-compatible adapter with a local fixture transport."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.enrichment import enrich_requests, serialize  # noqa: E402
from furiganalyse.enrichment_provider import (  # noqa: E402
    OpenAICompatibleProvider,
    build_prompt_report,
)


class FixtureTransport:
    def __init__(self, responses):
        self.responses = responses

    def create(self, payload, api_key, timeout):
        del api_key, timeout
        request_id = json.loads(payload["input"])["study_item"]["request_id"]
        value = self.responses.get(request_id)
        if not isinstance(value, dict):
            raise RuntimeError("fixture transport unavailable")
        return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requests_json", type=Path)
    parser.add_argument("responses_json", type=Path)
    parser.add_argument("prompts_output", type=Path)
    parser.add_argument("report_output", type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--model", default="fake-enrichment-v1")
    args = parser.parse_args()
    requests = json.loads(args.requests_json.read_text(encoding="utf-8"))
    responses = json.loads(args.responses_json.read_text(encoding="utf-8"))
    provider = OpenAICompatibleProvider(
        model_id=args.model,
        api_key="local-fixture-credential",
        transport=FixtureTransport(responses),
    )
    prompts = build_prompt_report(requests)
    report = enrich_requests(requests, provider, args.cache_dir)
    for path, value in (
        (args.prompts_output, prompts),
        (args.report_output, report),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialize(value), encoding="utf-8")
    print(f"Wrote {len(prompts['prompts'])} prompts and {len(report['results'])} results")


if __name__ == "__main__":
    main()
