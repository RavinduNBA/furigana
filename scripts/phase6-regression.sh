#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

./scripts/phase5-regression.sh

PYTHON="${PYTHON:-.venv/bin/python}"
PYTEST="${PYTEST:-.venv/bin/pytest}"
OUT="artifacts/phase6"
BOOK="artifacts/phase2/run-a/book.json"
VOCABULARY="artifacts/phase3/jmnedict/run-a/vocabulary.json"
PLAN="artifacts/phase5/enriched-plan/run-a/annotation-plan.json"
QUERIES="tests/phase6_golden/retrieval-queries-v1.json"

mkdir -p "$OUT/run-a" "$OUT/run-b" "$OUT/disabled" "$OUT/failure"
mkdir -p "$OUT/evidence/run-a" "$OUT/evidence/run-b" "$OUT/evidence/minimum-one"
mkdir -p "$OUT/evidence/disabled" "$OUT/evidence/failure"
mkdir -p "$OUT/terminology/run-a" "$OUT/terminology/run-b"
mkdir -p "$OUT/terminology/rejected" "$OUT/terminology/disabled"
mkdir -p "$OUT/terminology/stale" "$OUT/terminology/invalid"
mkdir -p "$OUT/terminology/failure"
mkdir -p "$OUT/summaries/run-a" "$OUT/summaries/run-b"
mkdir -p "$OUT/summaries/rejected" "$OUT/summaries/missing"
mkdir -p "$OUT/summaries/disabled" "$OUT/summaries/stale"
mkdir -p "$OUT/summaries/invalid" "$OUT/summaries/failure"
mkdir -p "$OUT/manifest/run-a" "$OUT/manifest/run-b" "$OUT/manifest/export-a" "$OUT/manifest/export-b"
mkdir -p "$OUT/manifest/rebuilt-a" "$OUT/manifest/rebuilt-b"
mkdir -p "$OUT/manifest/disabled" "$OUT/manifest/stale" "$OUT/manifest/invalid" "$OUT/manifest/failure"

"$PYTHON" scripts/build_book_context.py build "$BOOK" "$VOCABULARY" "$PLAN" "$OUT/run-a/context-index.json"
"$PYTHON" scripts/build_book_context.py build "$BOOK" "$VOCABULARY" "$PLAN" "$OUT/run-b/context-index.json"
cmp "$OUT/run-a/context-index.json" "$OUT/run-b/context-index.json"
cmp "$OUT/run-a/context-index.json" tests/phase6_golden/context-index-v1.json

"$PYTHON" scripts/build_book_context.py retrieve "$OUT/run-a/context-index.json" "$QUERIES" "$OUT/run-a/retrieval.json"
"$PYTHON" scripts/build_book_context.py retrieve "$OUT/run-b/context-index.json" "$QUERIES" "$OUT/run-b/retrieval.json"
cmp "$OUT/run-a/retrieval.json" "$OUT/run-b/retrieval.json"
cmp "$OUT/run-a/retrieval.json" tests/phase6_golden/retrieval-v1.json

"$PYTHON" scripts/build_book_context.py fallback "$PLAN" "$OUT/disabled/report.json" "$OUT/disabled/annotation-plan.json"
"$PYTHON" scripts/build_book_context.py fallback "$PLAN" "$OUT/failure/report.json" "$OUT/failure/annotation-plan.json" --reason corrupt-input
cmp "$PLAN" "$OUT/disabled/annotation-plan.json"
cmp "$PLAN" "$OUT/failure/annotation-plan.json"

"$PYTHON" scripts/build_context_evidence.py build "$OUT/run-a/context-index.json" "$VOCABULARY" "$PLAN" "$OUT/evidence/run-a/evidence.json"
"$PYTHON" scripts/build_context_evidence.py build "$OUT/run-b/context-index.json" "$VOCABULARY" "$PLAN" "$OUT/evidence/run-b/evidence.json"
cmp "$OUT/evidence/run-a/evidence.json" "$OUT/evidence/run-b/evidence.json"
cmp "$OUT/evidence/run-a/evidence.json" tests/phase6_golden/evidence-v1.json

"$PYTHON" scripts/build_context_evidence.py build "$OUT/run-a/context-index.json" "$VOCABULARY" "$PLAN" "$OUT/evidence/minimum-one/evidence.json" --minimum-occurrences 1
"$PYTHON" scripts/build_context_evidence.py fallback "$PLAN" "$OUT/evidence/disabled/report.json" "$OUT/evidence/disabled/annotation-plan.json"
"$PYTHON" scripts/build_context_evidence.py fallback "$PLAN" "$OUT/evidence/failure/report.json" "$OUT/evidence/failure/annotation-plan.json" --reason corrupt-input
cmp "$PLAN" "$OUT/evidence/disabled/annotation-plan.json"
cmp "$PLAN" "$OUT/evidence/failure/annotation-plan.json"

"$PYTHON" scripts/build_terminology_consistency.py build "$OUT/evidence/run-a/evidence.json" "$OUT/run-a/context-index.json" "$PLAN" tests/fixtures/phase6-terminology-registry-v1.json "$OUT/terminology/run-a/consistency.json"
"$PYTHON" scripts/build_terminology_consistency.py build "$OUT/evidence/run-b/evidence.json" "$OUT/run-b/context-index.json" "$PLAN" tests/fixtures/phase6-terminology-registry-v1.json "$OUT/terminology/run-b/consistency.json"
cmp "$OUT/terminology/run-a/consistency.json" "$OUT/terminology/run-b/consistency.json"
cmp "$OUT/terminology/run-a/consistency.json" tests/phase6_golden/terminology-consistency-v1.json

"$PYTHON" scripts/build_terminology_consistency.py build "$OUT/evidence/run-a/evidence.json" "$OUT/run-a/context-index.json" "$PLAN" tests/fixtures/phase6-terminology-rejected-v1.json "$OUT/terminology/rejected/consistency.json"
"$PYTHON" scripts/build_terminology_consistency.py fallback "$PLAN" "$OUT/terminology/disabled/report.json" "$OUT/terminology/disabled/annotation-plan.json"
"$PYTHON" scripts/build_terminology_consistency.py fallback "$PLAN" "$OUT/terminology/stale/report.json" "$OUT/terminology/stale/annotation-plan.json" --reason stale-evidence-hash
"$PYTHON" scripts/build_terminology_consistency.py fallback "$PLAN" "$OUT/terminology/invalid/report.json" "$OUT/terminology/invalid/annotation-plan.json" --reason invalid-registry
"$PYTHON" scripts/build_terminology_consistency.py fallback "$PLAN" "$OUT/terminology/failure/report.json" "$OUT/terminology/failure/annotation-plan.json" --reason corrupt-registry
cmp "$PLAN" "$OUT/terminology/disabled/annotation-plan.json"
cmp "$PLAN" "$OUT/terminology/stale/annotation-plan.json"
cmp "$PLAN" "$OUT/terminology/invalid/annotation-plan.json"
cmp "$PLAN" "$OUT/terminology/failure/annotation-plan.json"

"$PYTHON" scripts/build_chapter_summaries.py packets "$OUT/run-a/context-index.json" "$OUT/evidence/run-a/evidence.json" "$OUT/terminology/run-a/consistency.json" "$OUT/summaries/run-a/packets.json"
"$PYTHON" scripts/build_chapter_summaries.py packets "$OUT/run-b/context-index.json" "$OUT/evidence/run-b/evidence.json" "$OUT/terminology/run-b/consistency.json" "$OUT/summaries/run-b/packets.json"
cmp "$OUT/summaries/run-a/packets.json" "$OUT/summaries/run-b/packets.json"
cmp "$OUT/summaries/run-a/packets.json" tests/phase6_golden/chapter-context-packets-v1.json

"$PYTHON" scripts/build_chapter_summaries.py report "$OUT/summaries/run-a/packets.json" tests/fixtures/phase6-chapter-summary-registry-v1.json "$OUT/summaries/run-a/summary.json"
"$PYTHON" scripts/build_chapter_summaries.py report "$OUT/summaries/run-b/packets.json" tests/fixtures/phase6-chapter-summary-registry-v1.json "$OUT/summaries/run-b/summary.json"
cmp "$OUT/summaries/run-a/summary.json" "$OUT/summaries/run-b/summary.json"
cmp "$OUT/summaries/run-a/summary.json" tests/phase6_golden/chapter-summary-report-v1.json

"$PYTHON" scripts/build_chapter_summaries.py retrieve "$OUT/summaries/run-a/packets.json" "$OUT/summaries/run-a/summary.json" tests/phase6_golden/chapter-summary-queries-v1.json "$OUT/summaries/run-a/retrieval.json"
"$PYTHON" scripts/build_chapter_summaries.py retrieve "$OUT/summaries/run-b/packets.json" "$OUT/summaries/run-b/summary.json" tests/phase6_golden/chapter-summary-queries-v1.json "$OUT/summaries/run-b/retrieval.json"
cmp "$OUT/summaries/run-a/retrieval.json" "$OUT/summaries/run-b/retrieval.json"
cmp "$OUT/summaries/run-a/retrieval.json" tests/phase6_golden/chapter-summary-retrieval-v1.json

"$PYTHON" scripts/build_chapter_summaries.py report "$OUT/summaries/run-a/packets.json" tests/fixtures/phase6-chapter-summary-rejected-v1.json "$OUT/summaries/rejected/summary.json"
"$PYTHON" scripts/build_chapter_summaries.py report "$OUT/summaries/run-a/packets.json" tests/fixtures/phase6-chapter-summary-missing-v1.json "$OUT/summaries/missing/summary.json"
"$PYTHON" scripts/build_chapter_summaries.py fallback "$PLAN" "$OUT/summaries/disabled/report.json" "$OUT/summaries/disabled/annotation-plan.json"
"$PYTHON" scripts/build_chapter_summaries.py fallback "$PLAN" "$OUT/summaries/stale/report.json" "$OUT/summaries/stale/annotation-plan.json" --reason stale-packet-hash
"$PYTHON" scripts/build_chapter_summaries.py fallback "$PLAN" "$OUT/summaries/invalid/report.json" "$OUT/summaries/invalid/annotation-plan.json" --reason invalid-registry
"$PYTHON" scripts/build_chapter_summaries.py fallback "$PLAN" "$OUT/summaries/failure/report.json" "$OUT/summaries/failure/annotation-plan.json" --reason corrupt-registry
cmp "$PLAN" "$OUT/summaries/disabled/annotation-plan.json"
cmp "$PLAN" "$OUT/summaries/stale/annotation-plan.json"
cmp "$PLAN" "$OUT/summaries/invalid/annotation-plan.json"
cmp "$PLAN" "$OUT/summaries/failure/annotation-plan.json"

"$PYTHON" scripts/build_context_manifest.py build "$OUT/run-a/context-index.json" "$OUT/evidence/run-a/evidence.json" "$OUT/terminology/run-a/consistency.json" "$OUT/summaries/run-a/packets.json" "$OUT/summaries/run-a/summary.json" "$OUT/manifest/run-a/manifest.json"
"$PYTHON" scripts/build_context_manifest.py build "$OUT/run-b/context-index.json" "$OUT/evidence/run-b/evidence.json" "$OUT/terminology/run-b/consistency.json" "$OUT/summaries/run-b/packets.json" "$OUT/summaries/run-b/summary.json" "$OUT/manifest/run-b/manifest.json"
cmp "$OUT/manifest/run-a/manifest.json" "$OUT/manifest/run-b/manifest.json"
cmp "$OUT/manifest/run-a/manifest.json" tests/phase6_golden/book-context-manifest-v1.json

"$PYTHON" scripts/build_context_manifest.py validate "$OUT/manifest/run-a/manifest.json" tests/fixtures/phase6-edited-context-manifest-v1.json
"$PYTHON" scripts/build_context_manifest.py validate "$OUT/manifest/run-b/manifest.json" tests/fixtures/phase6-edited-context-manifest-v1.json
"$PYTHON" scripts/build_context_manifest.py export "$OUT/manifest/run-a/manifest.json" tests/fixtures/phase6-edited-context-manifest-v1.json "$OUT/evidence/run-a/evidence.json" "$OUT/summaries/run-a/packets.json" "$OUT/manifest/export-a/terminology.json" "$OUT/manifest/export-a/summaries.json"
"$PYTHON" scripts/build_context_manifest.py export "$OUT/manifest/run-b/manifest.json" tests/fixtures/phase6-edited-context-manifest-v1.json "$OUT/evidence/run-b/evidence.json" "$OUT/summaries/run-b/packets.json" "$OUT/manifest/export-b/terminology.json" "$OUT/manifest/export-b/summaries.json"
cmp "$OUT/manifest/export-a/terminology.json" "$OUT/manifest/export-b/terminology.json"
cmp "$OUT/manifest/export-a/terminology.json" tests/phase6_golden/exported-terminology-registry-v1.json
cmp "$OUT/manifest/export-a/summaries.json" "$OUT/manifest/export-b/summaries.json"
cmp "$OUT/manifest/export-a/summaries.json" tests/phase6_golden/exported-summary-registry-v1.json

"$PYTHON" scripts/build_terminology_consistency.py build "$OUT/evidence/run-a/evidence.json" "$OUT/run-a/context-index.json" "$PLAN" "$OUT/manifest/export-a/terminology.json" "$OUT/manifest/rebuilt-a/terminology.json"
"$PYTHON" scripts/build_terminology_consistency.py build "$OUT/evidence/run-b/evidence.json" "$OUT/run-b/context-index.json" "$PLAN" "$OUT/manifest/export-b/terminology.json" "$OUT/manifest/rebuilt-b/terminology.json"
cmp "$OUT/manifest/rebuilt-a/terminology.json" "$OUT/manifest/rebuilt-b/terminology.json"
"$PYTHON" scripts/build_chapter_summaries.py report "$OUT/summaries/run-a/packets.json" "$OUT/manifest/export-a/summaries.json" "$OUT/manifest/rebuilt-a/summaries.json"
"$PYTHON" scripts/build_chapter_summaries.py report "$OUT/summaries/run-b/packets.json" "$OUT/manifest/export-b/summaries.json" "$OUT/manifest/rebuilt-b/summaries.json"
cmp "$OUT/manifest/rebuilt-a/summaries.json" "$OUT/manifest/rebuilt-b/summaries.json"

"$PYTHON" scripts/build_context_manifest.py augment artifacts/phase5/run-a/requests.json tests/fixtures/phase6-edited-context-manifest-v1.json "$OUT/manifest/run-a/augmentation.json" --include-previous
"$PYTHON" scripts/build_context_manifest.py augment artifacts/phase5/run-a/requests.json tests/fixtures/phase6-edited-context-manifest-v1.json "$OUT/manifest/run-b/augmentation.json" --include-previous
cmp "$OUT/manifest/run-a/augmentation.json" "$OUT/manifest/run-b/augmentation.json"
cmp "$OUT/manifest/run-a/augmentation.json" tests/phase6_golden/context-augmentation-v1.json

for mode in disabled stale invalid failure; do
  reason=""
  if [ "$mode" != disabled ]; then reason="--reason $mode-manifest"; fi
  "$PYTHON" scripts/build_context_manifest.py fallback artifacts/phase5/run-a/requests.json "$PLAN" "$OUT/manifest/$mode/report.json" "$OUT/manifest/$mode/requests.json" "$OUT/manifest/$mode/annotation-plan.json" $reason
  cmp artifacts/phase5/run-a/requests.json "$OUT/manifest/$mode/requests.json"
  cmp "$PLAN" "$OUT/manifest/$mode/annotation-plan.json"
done

"$PYTEST" -q tests/test_book_context.py tests/test_context_evidence.py tests/test_terminology.py tests/test_chapter_summaries.py tests/test_context_manifest.py
echo "Phase 6 regression passed; artifacts retained under $OUT"
