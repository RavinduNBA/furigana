#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
ARTIFACTS="$ROOT/artifacts/phase7"
SPEC="$ROOT/tests/fixtures/phase7-passages-v1.json"
DATASET="$ROOT/tests/fixtures/phase7-grammar-rules-v1.json"
GOLDEN="$ROOT/tests/phase7_golden/grammar-candidates-v1.json"
PLAN_GOLDEN="$ROOT/tests/phase7_golden/grammar-plan-v1.json"
COMPAT_BOOK="$ROOT/artifacts/phase2/run-a/book.json"
COMPAT_VOCABULARY="$ROOT/artifacts/phase3/jmnedict/run-a/vocabulary.json"
COMPAT_PLAN="$ROOT/artifacts/phase5/enriched-plan/run-a/annotation-plan.json"

"$ROOT/scripts/phase6-regression.sh"

mkdir -p "$ARTIFACTS/run-a" "$ARTIFACTS/run-b" "$ARTIFACTS/disabled" "$ARTIFACTS/invalid" "$ARTIFACTS/failure" "$ARTIFACTS/compatibility" "$ARTIFACTS/grammar-plan/run-a" "$ARTIFACTS/grammar-plan/run-b" "$ARTIFACTS/grammar-plan/include-synthetic" "$ARTIFACTS/grammar-plan/limit" "$ARTIFACTS/grammar-plan/disabled" "$ARTIFACTS/grammar-plan/stale" "$ARTIFACTS/grammar-plan/invalid" "$ARTIFACTS/grammar-plan/corrupt"

for run in run-a run-b; do
  "$PYTHON" "$ROOT/scripts/build_phase7_fixture.py" --spec "$SPEC" --output-dir "$ARTIFACTS/$run/inputs"
  "$PYTHON" "$ROOT/scripts/analyze_grammar.py" --book "$ARTIFACTS/$run/inputs/book.json" --vocabulary "$ARTIFACTS/$run/inputs/vocabulary.json" --annotation-plan "$ARTIFACTS/$run/inputs/annotation-plan.json" --dataset "$DATASET" --output "$ARTIFACTS/$run/grammar.json"
done

cmp "$ARTIFACTS/run-a/grammar.json" "$ARTIFACTS/run-b/grammar.json"
cmp "$ARTIFACTS/run-a/grammar.json" "$GOLDEN"
cmp "$ARTIFACTS/run-a/inputs/book.json" "$ARTIFACTS/run-b/inputs/book.json"
cmp "$ARTIFACTS/run-a/inputs/vocabulary.json" "$ARTIFACTS/run-b/inputs/vocabulary.json"
cmp "$ARTIFACTS/run-a/inputs/annotation-plan.json" "$ARTIFACTS/run-b/inputs/annotation-plan.json"

cp "$COMPAT_VOCABULARY" "$ARTIFACTS/compatibility/phase3-vocabulary-before.json"
cp "$COMPAT_PLAN" "$ARTIFACTS/compatibility/phase5-plan-before.json"

"$PYTHON" "$ROOT/scripts/analyze_grammar.py" --book "$COMPAT_BOOK" --vocabulary "$COMPAT_VOCABULARY" --annotation-plan "$COMPAT_PLAN" --output "$ARTIFACTS/disabled/report.json" --fallback-plan-output "$ARTIFACTS/disabled/annotation-plan.json" --disabled
"$PYTHON" "$ROOT/scripts/analyze_grammar.py" --book "$COMPAT_BOOK" --vocabulary "$COMPAT_VOCABULARY" --annotation-plan "$COMPAT_PLAN" --dataset "$ROOT/tests/fixtures/phase7-grammar-invalid-v1.json" --output "$ARTIFACTS/invalid/report.json" --fallback-plan-output "$ARTIFACTS/invalid/annotation-plan.json" --safe
"$PYTHON" "$ROOT/scripts/analyze_grammar.py" --book "$COMPAT_BOOK" --vocabulary "$COMPAT_VOCABULARY" --annotation-plan "$COMPAT_PLAN" --dataset "$ROOT/tests/fixtures/phase7-grammar-corrupt-v1.json" --output "$ARTIFACTS/failure/report.json" --fallback-plan-output "$ARTIFACTS/failure/annotation-plan.json" --safe

cmp "$ARTIFACTS/disabled/annotation-plan.json" "$COMPAT_PLAN"
cmp "$ARTIFACTS/invalid/annotation-plan.json" "$COMPAT_PLAN"
cmp "$ARTIFACTS/failure/annotation-plan.json" "$COMPAT_PLAN"
cmp "$ARTIFACTS/compatibility/phase3-vocabulary-before.json" "$COMPAT_VOCABULARY"
cmp "$ARTIFACTS/compatibility/phase5-plan-before.json" "$COMPAT_PLAN"

for run in run-a run-b; do
  "$PYTHON" "$ROOT/scripts/create_grammar_plan.py" --book "$ARTIFACTS/$run/inputs/book.json" --vocabulary "$ARTIFACTS/$run/inputs/vocabulary.json" --annotation-plan "$ARTIFACTS/$run/inputs/annotation-plan.json" --grammar-report "$ARTIFACTS/$run/grammar.json" --dataset "$DATASET" --output "$ARTIFACTS/grammar-plan/$run/plan.json" --enabled
done
cmp "$ARTIFACTS/grammar-plan/run-a/plan.json" "$ARTIFACTS/grammar-plan/run-b/plan.json"
cmp "$ARTIFACTS/grammar-plan/run-a/plan.json" "$PLAN_GOLDEN"

"$PYTHON" "$ROOT/scripts/create_grammar_plan.py" --book "$ARTIFACTS/run-a/inputs/book.json" --vocabulary "$ARTIFACTS/run-a/inputs/vocabulary.json" --annotation-plan "$ARTIFACTS/run-a/inputs/annotation-plan.json" --grammar-report "$ARTIFACTS/run-a/grammar.json" --dataset "$DATASET" --output "$ARTIFACTS/grammar-plan/include-synthetic/plan.json" --enabled --include-synthetic-mechanics --per-chapter-limit 5
"$PYTHON" "$ROOT/scripts/create_grammar_plan.py" --book "$ARTIFACTS/run-a/inputs/book.json" --vocabulary "$ARTIFACTS/run-a/inputs/vocabulary.json" --annotation-plan "$ARTIFACTS/run-a/inputs/annotation-plan.json" --grammar-report "$ARTIFACTS/run-a/grammar.json" --dataset "$DATASET" --output "$ARTIFACTS/grammar-plan/limit/plan.json" --enabled --per-chapter-limit 2

"$PYTHON" "$ROOT/scripts/analyze_grammar.py" --book "$COMPAT_BOOK" --vocabulary "$COMPAT_VOCABULARY" --annotation-plan "$COMPAT_PLAN" --dataset "$DATASET" --output "$ARTIFACTS/compatibility/legal-grammar.json"
"$PYTHON" "$ROOT/scripts/build_phase7_plan_cases.py" --grammar-report "$ARTIFACTS/compatibility/legal-grammar.json" --stale-output "$ARTIFACTS/grammar-plan/stale/grammar.json"

"$PYTHON" "$ROOT/scripts/create_grammar_plan.py" --book "$COMPAT_BOOK" --vocabulary "$COMPAT_VOCABULARY" --annotation-plan "$COMPAT_PLAN" --grammar-report "$ARTIFACTS/compatibility/legal-grammar.json" --dataset "$DATASET" --output "$ARTIFACTS/grammar-plan/disabled/report.json" --fallback-plan-output "$ARTIFACTS/grammar-plan/disabled/annotation-plan.json"
"$PYTHON" "$ROOT/scripts/create_grammar_plan.py" --book "$COMPAT_BOOK" --vocabulary "$COMPAT_VOCABULARY" --annotation-plan "$COMPAT_PLAN" --grammar-report "$ARTIFACTS/grammar-plan/stale/grammar.json" --dataset "$DATASET" --output "$ARTIFACTS/grammar-plan/stale/report.json" --fallback-plan-output "$ARTIFACTS/grammar-plan/stale/annotation-plan.json" --enabled --safe
"$PYTHON" "$ROOT/scripts/create_grammar_plan.py" --book "$COMPAT_BOOK" --vocabulary "$COMPAT_VOCABULARY" --annotation-plan "$COMPAT_PLAN" --grammar-report "$ARTIFACTS/compatibility/legal-grammar.json" --dataset "$ROOT/tests/fixtures/phase7-grammar-invalid-v1.json" --output "$ARTIFACTS/grammar-plan/invalid/report.json" --fallback-plan-output "$ARTIFACTS/grammar-plan/invalid/annotation-plan.json" --enabled --safe
"$PYTHON" "$ROOT/scripts/create_grammar_plan.py" --book "$COMPAT_BOOK" --vocabulary "$COMPAT_VOCABULARY" --annotation-plan "$COMPAT_PLAN" --grammar-report "$ROOT/tests/fixtures/phase7-grammar-corrupt-v1.json" --dataset "$DATASET" --output "$ARTIFACTS/grammar-plan/corrupt/report.json" --fallback-plan-output "$ARTIFACTS/grammar-plan/corrupt/annotation-plan.json" --enabled --safe

cmp "$ARTIFACTS/grammar-plan/disabled/annotation-plan.json" "$COMPAT_PLAN"
cmp "$ARTIFACTS/grammar-plan/stale/annotation-plan.json" "$COMPAT_PLAN"
cmp "$ARTIFACTS/grammar-plan/invalid/annotation-plan.json" "$COMPAT_PLAN"
cmp "$ARTIFACTS/grammar-plan/corrupt/annotation-plan.json" "$COMPAT_PLAN"
cmp "$ARTIFACTS/compatibility/phase3-vocabulary-before.json" "$COMPAT_VOCABULARY"
cmp "$ARTIFACTS/compatibility/phase5-plan-before.json" "$COMPAT_PLAN"

"$PYTHON" -m pytest -q "$ROOT/tests/test_grammar_analysis.py" "$ROOT/tests/test_grammar_plan.py"
echo "Phase 7 regression passed; artifacts retained under artifacts/phase7/."
