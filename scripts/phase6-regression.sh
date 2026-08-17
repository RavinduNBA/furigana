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

"$PYTEST" -q tests/test_book_context.py
echo "Phase 6 regression passed; artifacts retained under $OUT"
