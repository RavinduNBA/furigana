#!/usr/bin/env python3
"""Explicitly opt in to OpenAI-compatible enrichment for existing requests."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.enrichment import enrich_requests, serialize  # noqa: E402
from furiganalyse.enrichment_provider import (  # noqa: E402
    OpenAICompatibleProvider,
    OpenAISDKTransport,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requests_json", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--enable-openai-compatible", action="store_true")
    parser.add_argument("--model", required=True)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--max-output-tokens", type=int, default=300)
    args = parser.parse_args()
    if not args.enable_openai_compatible:
        parser.error("provider use requires --enable-openai-compatible")
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        parser.error(f"provider credential is absent from {args.api_key_env}")
    requests = json.loads(args.requests_json.read_text(encoding="utf-8"))
    provider = OpenAICompatibleProvider(
        model_id=args.model,
        api_key=api_key,
        transport=OpenAISDKTransport(),
        timeout_seconds=args.timeout_seconds,
        max_output_tokens=args.max_output_tokens,
    )
    report = enrich_requests(requests, provider, args.cache_dir)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(serialize(report), encoding="utf-8")
    print(f"Wrote {len(report['results'])} validated enrichment results")


if __name__ == "__main__":
    main()
