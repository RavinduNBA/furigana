#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
ARTIFACTS="$ROOT/artifacts/phase8/selection"
SOURCE_VOCABULARY="$ROOT/artifacts/phase7/run-a/inputs/vocabulary.json"
SOURCE_PLAN="$ROOT/artifacts/phase7/run-a/inputs/annotation-plan.json"
SOURCE_GRAMMAR="$ROOT/artifacts/phase7/grammar-plan/run-a/plan.json"
FIXTURES="$ROOT/tests/fixtures/phase8"
GOLDEN="$ROOT/tests/phase8_golden/assistance-selection-v1.json"
COMPARISON_GOLDEN="$ROOT/tests/phase8_golden/preset-comparison-v1.json"
REVIEW_GOLDEN="$ROOT/tests/phase8_golden/assistance-review-cases-v1.json"
COMPAT_VOCABULARY="$ROOT/artifacts/phase3/jmnedict/run-a/vocabulary.json"
COMPAT_PLAN="$ROOT/artifacts/phase5/enriched-plan/run-a/annotation-plan.json"

"$ROOT/scripts/phase7-regression.sh"

mkdir -p "$ARTIFACTS/fixtures/run-a" "$ARTIFACTS/fixtures/run-b" \
  "$ARTIFACTS/run-a" "$ARTIFACTS/run-b" "$ARTIFACTS/profiles" \
  "$ARTIFACTS/cases/inputs" "$ARTIFACTS/compatibility"

for run in run-a run-b; do
  "$PYTHON" "$ROOT/scripts/build_phase8_fixtures.py" \
    --vocabulary "$SOURCE_VOCABULARY" \
    --annotation-plan "$SOURCE_PLAN" \
    --grammar-plan "$SOURCE_GRAMMAR" \
    --output-dir "$ARTIFACTS/fixtures/$run"
done
diff -r "$ARTIFACTS/fixtures/run-a" "$ARTIFACTS/fixtures/run-b"
diff -r "$ARTIFACTS/fixtures/run-a" "$FIXTURES"

for run in run-a run-b; do
  "$PYTHON" "$ROOT/scripts/create_assistance_selection.py" \
    --vocabulary "$SOURCE_VOCABULARY" \
    --annotation-plan "$SOURCE_PLAN" \
    --grammar-plan "$SOURCE_GRAMMAR" \
    --profile "$ARTIFACTS/fixtures/$run/phase8-profile-baseline-v1.json" \
    --presets "$ARTIFACTS/fixtures/$run/phase8-presets-v1.json" \
    --exposure-history "$ARTIFACTS/fixtures/$run/phase8-exposure-history-v1.json" \
    --output "$ARTIFACTS/$run/assistance.json" --enabled
done
cmp "$ARTIFACTS/run-a/assistance.json" "$ARTIFACTS/run-b/assistance.json"
cmp "$ARTIFACTS/run-a/assistance.json" "$GOLDEN"

for profile in show-show show-hide hide-show hide-hide n5 n4 n3; do
  "$PYTHON" "$ROOT/scripts/create_assistance_selection.py" \
    --vocabulary "$SOURCE_VOCABULARY" \
    --annotation-plan "$SOURCE_PLAN" \
    --grammar-plan "$SOURCE_GRAMMAR" \
    --profile "$FIXTURES/phase8-profile-$profile-v1.json" \
    --presets "$FIXTURES/phase8-presets-v1.json" \
    --output "$ARTIFACTS/profiles/$profile.json" --enabled
done

jq -e '[.results[:5][] | [.reading_assistance,.meaning_assistance]] | unique == [["show-reading","show-meaning"]]' "$ARTIFACTS/profiles/show-show.json" >/dev/null
jq -e '[.results[:5][] | [.reading_assistance,.meaning_assistance]] | unique == [["show-reading","hide-meaning"]]' "$ARTIFACTS/profiles/show-hide.json" >/dev/null
jq -e '[.results[:5][] | [.reading_assistance,.meaning_assistance]] | unique == [["hide-reading","show-meaning"]]' "$ARTIFACTS/profiles/hide-show.json" >/dev/null
jq -e '[.results[:5][] | [.reading_assistance,.meaning_assistance]] | unique == [["hide-reading","hide-meaning"]]' "$ARTIFACTS/profiles/hide-hide.json" >/dev/null
jq -e '.results[0].reading_assistance == "show-reading" and .results[0].meaning_assistance == "show-meaning" and .results[5].grammar_assistance == "show-grammar"' "$ARTIFACTS/profiles/n5.json" >/dev/null
jq -e '.results[0].reading_assistance == "hide-reading" and .results[0].meaning_assistance == "show-meaning" and .results[5].grammar_assistance == "show-grammar"' "$ARTIFACTS/profiles/n4.json" >/dev/null
jq -e '.results[0].reading_assistance == "hide-reading" and .results[0].meaning_assistance == "hide-meaning" and .results[5].grammar_assistance == "hide-grammar"' "$ARTIFACTS/profiles/n3.json" >/dev/null

"$PYTHON" "$ROOT/scripts/build_phase8_review_cases.py" \
  --baseline "$ARTIFACTS/run-a/assistance.json" \
  --n5 "$ARTIFACTS/profiles/n5.json" \
  --n4 "$ARTIFACTS/profiles/n4.json" \
  --n3 "$ARTIFACTS/profiles/n3.json" \
  --comparison-output "$ARTIFACTS/preset-comparison.json" \
  --review-output "$ARTIFACTS/review-cases.json"
cmp "$ARTIFACTS/preset-comparison.json" "$COMPARISON_GOLDEN"
cmp "$ARTIFACTS/review-cases.json" "$REVIEW_GOLDEN"

jq -e '
  (.results | length) == 10 and
  .diagnostics == [] and
  (.results[] | select(.source_item_id == "study-item-0001") | .effective_sources.reading) == "exposure_policy" and
  (.results[] | select(.source_item_id == "study-item-0002") | .effective_sources.meaning) == "exposure_policy" and
  (.results[] | select(.source_item_id == "study-item-0003") | .effective_sources.reading) == "explicit_user_override" and
  (.results[] | select(.source_item_id == "study-item-0004") | .publisher_ruby_protection) == "preserved-authoritative" and
  (.results[] | select(.source_item_id == "study-item-0005") | .item_kind) == "name" and
  (.results[] | select(.source_item_id == "grammar-item-0002") | .effective_sources.grammar) == "explicit_user_override"
' "$ARTIFACTS/run-a/assistance.json" >/dev/null

"$PYTHON" "$ROOT/scripts/build_phase8_cases.py" \
  --profile "$FIXTURES/phase8-profile-baseline-v1.json" \
  --exposure-history "$FIXTURES/phase8-exposure-history-v1.json" \
  --output-dir "$ARTIFACTS/cases/inputs"

run_failure() {
  local name="$1"
  local expected="$2"
  local profile="$3"
  local exposure="$4"
  mkdir -p "$ARTIFACTS/cases/$name"
  local args=(
    --vocabulary "$SOURCE_VOCABULARY"
    --annotation-plan "$SOURCE_PLAN"
    --grammar-plan "$SOURCE_GRAMMAR"
    --profile "$profile"
    --presets "$FIXTURES/phase8-presets-v1.json"
    --output "$ARTIFACTS/cases/$name/report.json"
    --fallback-plan-output "$ARTIFACTS/cases/$name/annotation-plan.json"
    --fallback-grammar-plan-output "$ARTIFACTS/cases/$name/grammar-plan.json"
    --enabled --safe
  )
  if [[ -n "$exposure" ]]; then
    args+=(--exposure-history "$exposure")
  fi
  "$PYTHON" "$ROOT/scripts/create_assistance_selection.py" "${args[@]}"
  jq -e --arg reason "$expected" '.results == [] and [.diagnostics[].reason] == [$reason]' "$ARTIFACTS/cases/$name/report.json" >/dev/null
  cmp "$ARTIFACTS/cases/$name/annotation-plan.json" "$SOURCE_PLAN"
  cmp "$ARTIFACTS/cases/$name/grammar-plan.json" "$SOURCE_GRAMMAR"
}

mkdir -p "$ARTIFACTS/cases/disabled"
"$PYTHON" "$ROOT/scripts/create_assistance_selection.py" \
  --vocabulary "$SOURCE_VOCABULARY" --annotation-plan "$SOURCE_PLAN" \
  --grammar-plan "$SOURCE_GRAMMAR" \
  --output "$ARTIFACTS/cases/disabled/report.json" \
  --fallback-plan-output "$ARTIFACTS/cases/disabled/annotation-plan.json" \
  --fallback-grammar-plan-output "$ARTIFACTS/cases/disabled/grammar-plan.json" --safe
jq -e '.results == [] and [.diagnostics[].reason] == ["disabled"]' "$ARTIFACTS/cases/disabled/report.json" >/dev/null
cmp "$ARTIFACTS/cases/disabled/annotation-plan.json" "$SOURCE_PLAN"
cmp "$ARTIFACTS/cases/disabled/grammar-plan.json" "$SOURCE_GRAMMAR"

run_failure stale source-hash-mismatch "$ARTIFACTS/cases/inputs/stale-profile.json" "$FIXTURES/phase8-exposure-history-v1.json"
run_failure invalid invalid-input "$ARTIFACTS/cases/inputs/invalid-profile.json" "$FIXTURES/phase8-exposure-history-v1.json"
run_failure corrupt corrupt-input "$ARTIFACTS/cases/inputs/corrupt-profile.json" "$FIXTURES/phase8-exposure-history-v1.json"
run_failure unknown unknown-override "$ARTIFACTS/cases/inputs/unknown-override-profile.json" "$FIXTURES/phase8-exposure-history-v1.json"
run_failure duplicate duplicate-override "$ARTIFACTS/cases/inputs/duplicate-override-profile.json" "$FIXTURES/phase8-exposure-history-v1.json"
run_failure publisher publisher-ruby-suppression-attempt "$ARTIFACTS/cases/inputs/publisher-suppression-profile.json" "$FIXTURES/phase8-exposure-history-v1.json"
run_failure negative-exposure negative-exposure-count "$FIXTURES/phase8-profile-baseline-v1.json" "$ARTIFACTS/cases/inputs/negative-exposure.json"
run_failure duplicate-exposure duplicate-exposure "$FIXTURES/phase8-profile-baseline-v1.json" "$ARTIFACTS/cases/inputs/duplicate-exposure.json"
run_failure dimension-mismatch dimension-mismatch "$FIXTURES/phase8-profile-baseline-v1.json" "$ARTIFACTS/cases/inputs/dimension-mismatch-exposure.json"

cp "$COMPAT_VOCABULARY" "$ARTIFACTS/compatibility/phase3-vocabulary.json"
cp "$COMPAT_PLAN" "$ARTIFACTS/compatibility/phase5-plan.json"
cmp "$ARTIFACTS/compatibility/phase3-vocabulary.json" "$COMPAT_VOCABULARY"
cmp "$ARTIFACTS/compatibility/phase5-plan.json" "$COMPAT_PLAN"
test "$(sha256sum "$ROOT/artifacts/phase7/epub/run-a.epub" | cut -d' ' -f1)" = "df4c4bf0f072c01ac0a8d8aff316ee92613760c1822274cecd7ec9ce409a9619"

"$PYTHON" -m pytest -q "$ROOT/tests/test_learner_profile.py"
echo "Phase 8 assistance-selection regression passed; artifacts retained under artifacts/phase8/selection/."
