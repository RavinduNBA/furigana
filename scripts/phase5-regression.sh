#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
./scripts/phase4-regression.sh
OUT=artifacts/phase5
rm -rf "$OUT/run-a" "$OUT/run-b" "$OUT/cache-a" "$OUT/cache-b" "$OUT/cache-failure" "$OUT/provider" "$OUT/enriched-plan" "$OUT/rendered"
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
mkdir -p "$OUT/enriched-plan/run-a" "$OUT/enriched-plan/run-b"
.venv/bin/python scripts/apply_enrichment_plan.py artifacts/phase4/run-a/annotation-plan.json "$OUT/run-a/requests.json" "$OUT/provider/run-a/report.json" "$OUT/enriched-plan/run-a/annotation-plan.json" "$OUT/enriched-plan/run-a/fallback-plan.json"
.venv/bin/python scripts/apply_enrichment_plan.py artifacts/phase4/run-a/annotation-plan.json "$OUT/run-b/requests.json" "$OUT/provider/run-b/report.json" "$OUT/enriched-plan/run-b/annotation-plan.json" "$OUT/enriched-plan/run-b/fallback-plan.json"
cmp "$OUT/enriched-plan/run-a/annotation-plan.json" "$OUT/enriched-plan/run-b/annotation-plan.json"
cmp "$OUT/enriched-plan/run-a/annotation-plan.json" tests/phase5_golden/enriched-plan-v2.json
.venv/bin/python scripts/apply_enrichment_plan.py artifacts/phase4/run-a/annotation-plan.json "$OUT/run-a/requests.json" "$OUT/run-a/disabled.json" "$OUT/enriched-plan/disabled.json" "$OUT/enriched-plan/disabled-fallback.json"
.venv/bin/python scripts/apply_enrichment_plan.py artifacts/phase4/run-a/annotation-plan.json "$OUT/run-a/requests.json" "$OUT/provider/run-a/failure.json" "$OUT/enriched-plan/failure.json" "$OUT/enriched-plan/failure-fallback.json"
cmp "$OUT/enriched-plan/disabled.json" artifacts/phase4/run-a/annotation-plan.json
cmp "$OUT/enriched-plan/disabled-fallback.json" artifacts/phase4/run-a/annotation-plan.json
cmp "$OUT/enriched-plan/failure.json" artifacts/phase4/run-a/annotation-plan.json
cmp "$OUT/enriched-plan/failure-fallback.json" artifacts/phase4/run-a/annotation-plan.json
.venv/bin/python scripts/build_mixed_enrichment_report.py "$OUT/provider/run-a/report.json" "$OUT/provider/run-a/failure.json" "$OUT/enriched-plan/mixed-report-a.json"
.venv/bin/python scripts/build_mixed_enrichment_report.py "$OUT/provider/run-b/report.json" "$OUT/provider/run-a/failure.json" "$OUT/enriched-plan/mixed-report-b.json"
.venv/bin/python scripts/apply_enrichment_plan.py artifacts/phase4/run-a/annotation-plan.json "$OUT/run-a/requests.json" "$OUT/enriched-plan/mixed-report-a.json" "$OUT/enriched-plan/mixed-a.json" "$OUT/enriched-plan/mixed-fallback-a.json"
.venv/bin/python scripts/apply_enrichment_plan.py artifacts/phase4/run-a/annotation-plan.json "$OUT/run-b/requests.json" "$OUT/enriched-plan/mixed-report-b.json" "$OUT/enriched-plan/mixed-b.json" "$OUT/enriched-plan/mixed-fallback-b.json"
cmp "$OUT/enriched-plan/mixed-a.json" "$OUT/enriched-plan/mixed-b.json"
mkdir -p "$OUT/rendered/run-a/notes" "$OUT/rendered/run-b/notes"
.venv/bin/python scripts/render_study_notes.py "$OUT/enriched-plan/run-a/annotation-plan.json" "$OUT/rendered/run-a/notes/study-notes.xhtml"
.venv/bin/python scripts/render_study_notes.py "$OUT/enriched-plan/run-b/annotation-plan.json" "$OUT/rendered/run-b/notes/study-notes.xhtml"
cmp "$OUT/rendered/run-a/notes/study-notes.xhtml" "$OUT/rendered/run-b/notes/study-notes.xhtml"
cmp "$OUT/rendered/run-a/notes/study-notes.xhtml" tests/phase5_golden/rendered-v2/study-notes.xhtml
.venv/bin/python scripts/render_linked_study_notes.py artifacts/phase2/fixture.epub artifacts/phase2/run-a/book.json "$OUT/enriched-plan/run-a/annotation-plan.json" "$OUT/rendered/run-a/linked"
.venv/bin/python scripts/render_linked_study_notes.py artifacts/phase2/fixture.epub artifacts/phase2/run-a/book.json "$OUT/enriched-plan/run-b/annotation-plan.json" "$OUT/rendered/run-b/linked"
diff -ru "$OUT/rendered/run-a/linked" "$OUT/rendered/run-b/linked"
diff -ru "$OUT/rendered/run-a/linked" tests/phase5_golden/linked-v2
.venv/bin/python scripts/package_study_epub.py artifacts/phase2/fixture.epub artifacts/phase2/run-a/book.json "$OUT/enriched-plan/run-a/annotation-plan.json" "$OUT/rendered/run-a.epub"
.venv/bin/python scripts/package_study_epub.py artifacts/phase2/fixture.epub artifacts/phase2/run-a/book.json "$OUT/enriched-plan/run-b/annotation-plan.json" "$OUT/rendered/run-b.epub"
cmp "$OUT/rendered/run-a.epub" "$OUT/rendered/run-b.epub"
mkdir -p "$OUT/rendered/fallback"
.venv/bin/python scripts/render_study_notes.py "$OUT/enriched-plan/disabled.json" "$OUT/rendered/fallback/study-notes.xhtml"
cmp "$OUT/rendered/fallback/study-notes.xhtml" artifacts/phase4/notes/run-a/study-notes.xhtml
.venv/bin/python scripts/render_linked_study_notes.py artifacts/phase2/fixture.epub artifacts/phase2/run-a/book.json "$OUT/enriched-plan/failure.json" "$OUT/rendered/fallback/linked"
diff -ru "$OUT/rendered/fallback/linked" artifacts/phase4/linked/run-a
.venv/bin/python scripts/package_study_epub.py artifacts/phase2/fixture.epub artifacts/phase2/run-a/book.json "$OUT/enriched-plan/disabled.json" "$OUT/rendered/fallback.epub"
cmp "$OUT/rendered/fallback.epub" artifacts/phase4/epub/run-a.epub
.venv/bin/python -m pytest -q tests/test_enrichment.py tests/test_enrichment_provider.py tests/test_enriched_plan.py tests/test_enriched_rendering.py
echo "Phase 5 enrichment and enriched-rendering regression passed. Artifacts: $OUT"
