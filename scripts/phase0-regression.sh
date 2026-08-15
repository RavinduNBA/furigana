#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"
python_bin="${PYTHON:-$repo_root/.venv/bin/python}"
"$python_bin" -m pytest -q tests/test_phase0_epub.py
"$python_bin" scripts/phase0_regression.py
