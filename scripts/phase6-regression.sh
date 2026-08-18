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

"$PYTEST" -q tests/test_book_context.py tests/test_context_evidence.py tests/test_terminology.py
echo "Phase 6 regression passed; artifacts retained under $OUT"
