#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
./scripts/phase4-regression.sh
OUT=artifacts/phase5
rm -rf "$OUT/run-a" "$OUT/run-b" "$OUT/cache-a" "$OUT/cache-b" "$OUT/cache-failure" "$OUT/provider"
mkdir -p "$OUT/run-a" "$OUT/run-b" "$OUT/cache-a" "$OUT/cache-b"
ARGS="artifacts/phase2/run-a/book.json artifacts/phase3/jmnedict/run-a/vocabulary.json artifacts/phase4/run-a/annotation-plan.json"
.venv/bin/python scripts/enrich_study_plan.py $ARGS "$OUT/run-a/requests.json" "$OUT/run-a/disabled.json" --fallback-plan-output "$OUT/run-a/fallback-plan.json"
.venv/bin/python scripts/enrich_study_plan.py $ARGS "$OUT/run-b/requests.json" "$OUT/run-b/disabled.json" --fallback-plan-output "$OUT/run-b/fallback-plan.json"
cmp "$OUT/run-a/requests.json" "$OUT/run-b/requests.json"
cmp "$OUT/run-a/requests.json" tests/phase5_golden/requests-v1.json
cmp "$OUT/run-a/disabled.json" "$OUT/run-b/disabled.json"
cmp "$OUT/run-a/fallback-plan.json" artifacts/phase4/run-a/annotation-plan.json
.venv/bin/python scripts/enrich_study_plan.py $ARGS "$OUT/run-a/scripted-requests.json" "$OUT/run-a/scripted.json" --scripted-responses tests/fixtures/phase5-scripted-responses-v1.json --cache-dir "$OUT/cache-a"
.venv/bin/python scripts/enrich_study_plan.py $ARGS "$OUT/run-b/scripted-requests.json" "$OUT/run-b/scripted.json" --scripted-responses tests/fixtures/phase5-scripted-responses-v1.json --cache-dir "$OUT/cache-b"
cmp "$OUT/run-a/scripted.json" "$OUT/run-b/scripted.json"
.venv/bin/python scripts/enrich_study_plan.py $ARGS "$OUT/run-a/cache-hit-requests.json" "$OUT/run-a/cache-hit.json" --cache-only --cache-dir "$OUT/cache-a"
.venv/bin/python scripts/enrich_study_plan.py $ARGS "$OUT/run-a/failure-requests.json" "$OUT/run-a/failure.json" --scripted-responses tests/fixtures/phase5-failing-responses-v1.json --cache-dir "$OUT/cache-failure"
mkdir -p "$OUT/provider/run-a" "$OUT/provider/run-b"
.venv/bin/python scripts/render_enrichment_prompts.py "$OUT/run-a/requests.json" "$OUT/provider/run-a/prompts.json"
.venv/bin/python scripts/render_enrichment_prompts.py "$OUT/run-b/requests.json" "$OUT/provider/run-b/prompts.json"
cmp "$OUT/provider/run-a/prompts.json" "$OUT/provider/run-b/prompts.json"
cmp "$OUT/provider/run-a/prompts.json" tests/phase5_golden/prompts-v1.json
.venv/bin/python scripts/run_fake_openai_provider.py "$OUT/run-a/requests.json" tests/fixtures/phase5-openai-responses-v1.json "$OUT/provider/run-a/provider-prompts.json" "$OUT/provider/run-a/report.json" --cache-dir "$OUT/provider/cache-a"
.venv/bin/python scripts/run_fake_openai_provider.py "$OUT/run-b/requests.json" tests/fixtures/phase5-openai-responses-v1.json "$OUT/provider/run-b/provider-prompts.json" "$OUT/provider/run-b/report.json" --cache-dir "$OUT/provider/cache-b"
cmp "$OUT/provider/run-a/report.json" "$OUT/provider/run-b/report.json"
.venv/bin/python scripts/run_fake_openai_provider.py "$OUT/run-a/requests.json" tests/fixtures/phase5-failing-responses-v1.json "$OUT/provider/run-a/cache-hit-prompts.json" "$OUT/provider/run-a/cache-hit.json" --cache-dir "$OUT/provider/cache-a"
.venv/bin/python scripts/run_fake_openai_provider.py "$OUT/run-a/requests.json" tests/fixtures/phase5-failing-responses-v1.json "$OUT/provider/run-a/failure-prompts.json" "$OUT/provider/run-a/failure.json" --cache-dir "$OUT/provider/cache-failure"
.venv/bin/python -m pytest -q tests/test_enrichment.py tests/test_enrichment_provider.py
echo "Phase 5 request, prompt, fake-provider cache, and fallback regression passed. Artifacts: $OUT"
