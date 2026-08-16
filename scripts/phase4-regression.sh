#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
./scripts/phase3-regression.sh
OUT=artifacts/phase4
SOURCE=artifacts/phase3/jmnedict/run-a/vocabulary.json
GOLDEN=tests/phase4_golden/annotation-plan-v1.json
mkdir -p "$OUT/run-a" "$OUT/run-b"
.venv/bin/python scripts/create_study_plan.py "$SOURCE" "$OUT/run-a/annotation-plan.json"
.venv/bin/python scripts/create_study_plan.py "$SOURCE" "$OUT/run-b/annotation-plan.json"
cmp "$OUT/run-a/annotation-plan.json" "$OUT/run-b/annotation-plan.json"
cmp "$OUT/run-a/annotation-plan.json" "$GOLDEN"
.venv/bin/python -m pytest -q tests/test_study_plan.py
echo "Phase 4 regression passed; artifacts retained under $OUT/"
