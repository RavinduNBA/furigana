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
EXPRESSION_FIXTURE="${ROOT_DIR}/tests/fixtures/jmdict-expressions-mini.xml"
EXPRESSION_GOLDEN="${ROOT_DIR}/tests/phase3_golden/vocabulary-jmdict-expressions-v3.json"
EXPRESSION_ARTIFACT_DIR="${JMDICT_ARTIFACT_DIR}/expressions"
EXPRESSION_INDEX="${EXPRESSION_ARTIFACT_DIR}/synthetic-jmdict.sqlite3"
EXPRESSION_RUN_A="${EXPRESSION_ARTIFACT_DIR}/run-a/vocabulary.json"
EXPRESSION_RUN_B="${EXPRESSION_ARTIFACT_DIR}/run-b/vocabulary.json"
JMNEDICT_FIXTURE="${ROOT_DIR}/tests/fixtures/jmnedict-mini.xml"
JMNEDICT_GOLDEN="${ROOT_DIR}/tests/phase3_golden/vocabulary-jmnedict-v4.json"
JMNEDICT_ARTIFACT_DIR="${ARTIFACT_DIR}/jmnedict"
JMNEDICT_INDEX="${JMNEDICT_ARTIFACT_DIR}/synthetic-jmnedict.sqlite3"
JMNEDICT_RUN_A="${JMNEDICT_ARTIFACT_DIR}/run-a/vocabulary.json"
JMNEDICT_RUN_B="${JMNEDICT_ARTIFACT_DIR}/run-b/vocabulary.json"

mkdir -p \
  "${ARTIFACT_DIR}/run-a" \
  "${ARTIFACT_DIR}/run-b" \
  "${JMDICT_ARTIFACT_DIR}/run-a" \
  "${JMDICT_ARTIFACT_DIR}/run-b" \
  "${EXPRESSION_ARTIFACT_DIR}/run-a" \
  "${EXPRESSION_ARTIFACT_DIR}/run-b" \
  "${JMNEDICT_ARTIFACT_DIR}/run-a" \
  "${JMNEDICT_ARTIFACT_DIR}/run-b"
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

rm -f "${EXPRESSION_INDEX}"
.venv/bin/python scripts/build_jmdict_index.py \
  "${EXPRESSION_FIXTURE}" "${EXPRESSION_INDEX}"
.venv/bin/python scripts/analyze_vocabulary.py \
  "${FIXTURE}" "${EXPRESSION_RUN_A}" \
  --jmdict-index "${EXPRESSION_INDEX}" --expressions
.venv/bin/python scripts/analyze_vocabulary.py \
  "${FIXTURE}" "${EXPRESSION_RUN_B}" \
  --jmdict-index "${EXPRESSION_INDEX}" --expressions
cmp "${EXPRESSION_RUN_A}" "${EXPRESSION_RUN_B}"
cmp "${EXPRESSION_RUN_A}" "${EXPRESSION_GOLDEN}"

rm -f "${JMNEDICT_INDEX}"
.venv/bin/python scripts/build_jmnedict_index.py \
  "${JMNEDICT_FIXTURE}" "${JMNEDICT_INDEX}"
.venv/bin/python scripts/analyze_vocabulary.py \
  "${FIXTURE}" "${JMNEDICT_RUN_A}" \
  --jmdict-index "${EXPRESSION_INDEX}" --expressions \
  --jmnedict-index "${JMNEDICT_INDEX}"
.venv/bin/python scripts/analyze_vocabulary.py \
  "${FIXTURE}" "${JMNEDICT_RUN_B}" \
  --jmdict-index "${EXPRESSION_INDEX}" --expressions \
  --jmnedict-index "${JMNEDICT_INDEX}"
cmp "${JMNEDICT_RUN_A}" "${JMNEDICT_RUN_B}"
cmp "${JMNEDICT_RUN_A}" "${JMNEDICT_GOLDEN}"

.venv/bin/python -m pytest -q \
  tests/test_vocabulary_analysis.py tests/test_jmdict.py tests/test_jmnedict.py

echo "Phase 3 tokenizer, dictionary, expression, and name reports passed. Artifacts: ${ARTIFACT_DIR}"
