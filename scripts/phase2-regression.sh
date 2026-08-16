#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts/phase2"
FIXTURE="${ARTIFACT_DIR}/fixture.epub"
RUN_A="${ARTIFACT_DIR}/run-a/book.json"
RUN_B="${ARTIFACT_DIR}/run-b/book.json"
GOLDEN="${ROOT_DIR}/tests/golden/phase2-book-v2.json"

mkdir -p "${ARTIFACT_DIR}/run-a" "${ARTIFACT_DIR}/run-b"
cd "${ROOT_DIR}"
.venv/bin/python -c \
  "from pathlib import Path; from tests.phase0_epub import build_fixture; build_fixture(Path('${FIXTURE}'))"
.venv/bin/python scripts/extract_book.py "${FIXTURE}" "${RUN_A}"
.venv/bin/python scripts/extract_book.py "${FIXTURE}" "${RUN_B}"
cmp "${RUN_A}" "${RUN_B}"
cmp "${RUN_A}" "${GOLDEN}"
.venv/bin/python -m pytest -q tests/test_book_analysis.py
echo "Phase 2 canonical extraction passed. Artifacts: ${ARTIFACT_DIR}"
