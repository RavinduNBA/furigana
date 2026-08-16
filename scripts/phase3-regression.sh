#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts/phase3"
FIXTURE="${ROOT_DIR}/artifacts/phase2/fixture.epub"
RUN_A="${ARTIFACT_DIR}/run-a/vocabulary.json"
RUN_B="${ARTIFACT_DIR}/run-b/vocabulary.json"
GOLDEN="${ROOT_DIR}/tests/phase3_golden/vocabulary-v1.json"

mkdir -p "${ARTIFACT_DIR}/run-a" "${ARTIFACT_DIR}/run-b"
cd "${ROOT_DIR}"

./scripts/phase2-regression.sh
.venv/bin/python scripts/analyze_vocabulary.py "${FIXTURE}" "${RUN_A}"
.venv/bin/python scripts/analyze_vocabulary.py "${FIXTURE}" "${RUN_B}"
cmp "${RUN_A}" "${RUN_B}"
cmp "${RUN_A}" "${GOLDEN}"
.venv/bin/python -m pytest -q tests/test_vocabulary_analysis.py

echo "Phase 3 vocabulary report passed. Artifacts: ${ARTIFACT_DIR}"
