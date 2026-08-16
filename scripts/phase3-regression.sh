#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts/phase3"
FIXTURE="${ROOT_DIR}/artifacts/phase2/fixture.epub"
RUN_A="${ARTIFACT_DIR}/run-a/vocabulary.json"
RUN_B="${ARTIFACT_DIR}/run-b/vocabulary.json"
GOLDEN="${ROOT_DIR}/tests/phase3_golden/vocabulary-v1.json"
JMDICT_FIXTURE="${ROOT_DIR}/tests/fixtures/jmdict-mini.xml"
JMDICT_GOLDEN="${ROOT_DIR}/tests/phase3_golden/vocabulary-jmdict-v2.json"
JMDICT_ARTIFACT_DIR="${ARTIFACT_DIR}/jmdict"
JMDICT_INDEX="${JMDICT_ARTIFACT_DIR}/synthetic-jmdict.sqlite3"
JMDICT_RUN_A="${JMDICT_ARTIFACT_DIR}/run-a/vocabulary.json"
JMDICT_RUN_B="${JMDICT_ARTIFACT_DIR}/run-b/vocabulary.json"

mkdir -p \
  "${ARTIFACT_DIR}/run-a" \
  "${ARTIFACT_DIR}/run-b" \
  "${JMDICT_ARTIFACT_DIR}/run-a" \
  "${JMDICT_ARTIFACT_DIR}/run-b"
cd "${ROOT_DIR}"

./scripts/phase2-regression.sh
.venv/bin/python scripts/analyze_vocabulary.py "${FIXTURE}" "${RUN_A}"
.venv/bin/python scripts/analyze_vocabulary.py "${FIXTURE}" "${RUN_B}"
cmp "${RUN_A}" "${RUN_B}"
cmp "${RUN_A}" "${GOLDEN}"

rm -f "${JMDICT_INDEX}"
.venv/bin/python scripts/build_jmdict_index.py \
  "${JMDICT_FIXTURE}" "${JMDICT_INDEX}"
.venv/bin/python scripts/analyze_vocabulary.py \
  "${FIXTURE}" "${JMDICT_RUN_A}" --jmdict-index "${JMDICT_INDEX}"
.venv/bin/python scripts/analyze_vocabulary.py \
  "${FIXTURE}" "${JMDICT_RUN_B}" --jmdict-index "${JMDICT_INDEX}"
cmp "${JMDICT_RUN_A}" "${JMDICT_RUN_B}"
cmp "${JMDICT_RUN_A}" "${JMDICT_GOLDEN}"

.venv/bin/python -m pytest -q \
  tests/test_vocabulary_analysis.py tests/test_jmdict.py

echo "Phase 3 tokenizer and JMdict reports passed. Artifacts: ${ARTIFACT_DIR}"
