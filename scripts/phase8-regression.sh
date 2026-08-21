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

DENSITY="$ROOT/artifacts/phase8/density"
DENSITY_FIXTURE="$ROOT/tests/fixtures/phase8-density-policies-v1.json"
DENSITY_GOLDEN="$ROOT/tests/phase8_golden/per-occurrence-assistance-plan-v1.json"
DENSITY_COMPARISON_GOLDEN="$ROOT/tests/phase8_golden/density-comparison-v1.json"
DENSITY_REVIEW_GOLDEN="$ROOT/tests/phase8_golden/density-review-cases-v1.json"
SOURCE_BOOK="$ROOT/artifacts/phase7/run-a/inputs/book.json"

mkdir -p "$DENSITY/policies" "$DENSITY/run-a" "$DENSITY/run-b" \
  "$DENSITY/profiles" "$DENSITY/cases/inputs" "$DENSITY/compatibility"

for run in run-a run-b; do
  "$PYTHON" "$ROOT/scripts/build_phase8_density_policy.py" \
    --output "$DENSITY/policies/$run.json"
done
cmp "$DENSITY/policies/run-a.json" "$DENSITY/policies/run-b.json"
cmp "$DENSITY/policies/run-a.json" "$DENSITY_FIXTURE"

for run in run-a run-b; do
  "$PYTHON" "$ROOT/scripts/create_assistance_density.py" \
    --canonical-book "$SOURCE_BOOK" \
    --annotation-plan "$SOURCE_PLAN" \
    --grammar-plan "$SOURCE_GRAMMAR" \
    --assistance-report "$ARTIFACTS/run-a/assistance.json" \
    --density-policies "$DENSITY_FIXTURE" \
    --policy-id phase8-density-n5 \
    --output "$DENSITY/$run/density.json" --enabled
done
cmp "$DENSITY/run-a/density.json" "$DENSITY/run-b/density.json"
cmp "$DENSITY/run-a/density.json" "$DENSITY_GOLDEN"

for level in n5 n4 n3; do
  "$PYTHON" "$ROOT/scripts/create_assistance_density.py" \
    --canonical-book "$SOURCE_BOOK" \
    --annotation-plan "$SOURCE_PLAN" \
    --grammar-plan "$SOURCE_GRAMMAR" \
    --assistance-report "$ARTIFACTS/profiles/$level.json" \
    --density-policies "$DENSITY_FIXTURE" \
    --policy-id "phase8-density-$level" \
    --output "$DENSITY/profiles/$level.json" --enabled
done

"$PYTHON" "$ROOT/scripts/build_phase8_density_cases.py" \
  --baseline "$DENSITY/run-a/density.json" \
  --assistance "$ARTIFACTS/run-a/assistance.json" \
  --n5 "$DENSITY/profiles/n5.json" \
  --n4 "$DENSITY/profiles/n4.json" \
  --n3 "$DENSITY/profiles/n3.json" \
  --annotation-plan "$SOURCE_PLAN" \
  --grammar-plan "$SOURCE_GRAMMAR" \
  --policies "$DENSITY_FIXTURE" \
  --comparison-output "$DENSITY/density-comparison.json" \
  --review-output "$DENSITY/review-cases.json" \
  --failure-dir "$DENSITY/cases/inputs"
cmp "$DENSITY/density-comparison.json" "$DENSITY_COMPARISON_GOLDEN"
cmp "$DENSITY/review-cases.json" "$DENSITY_REVIEW_GOLDEN"

jq -e '
  (.occurrence_plans | length) == 12 and
  [.chapter_summaries[].canonical_character_count] == [67,18] and
  (.occurrence_plans | map(.source_occurrence_id) | unique | length) == 12 and
  any(.diagnostics[]; .reason == "budget-exclusion") and
  any(.diagnostics[]; .reason == "explicit-override-over-budget") and
  (.occurrence_plans[] | select(.source_occurrence_id == "study-item-0004-occ-0001") | .density_decisions.reading) == "publisher-ruby-preserved" and
  (.occurrence_plans[] | select(.source_occurrence_id == "grammar-plan-occurrence-0003") | .density_decisions.grammar) == "grammar-partial-overlap-rejected" and
  (.occurrence_plans[] | select(.source_occurrence_id == "grammar-plan-occurrence-0004") | .density_decisions.grammar) == "grammar-reference-only"
' "$DENSITY/run-a/density.json" >/dev/null

jq -e '
  .profiles[0].selected_counts.reading >= .profiles[1].selected_counts.reading and
  .profiles[1].selected_counts.reading >= .profiles[2].selected_counts.reading and
  .profiles[0].selected_counts.meaning >= .profiles[1].selected_counts.meaning and
  .profiles[1].selected_counts.meaning >= .profiles[2].selected_counts.meaning and
  .profiles[0].selected_counts.grammar >= .profiles[1].selected_counts.grammar and
  .profiles[1].selected_counts.grammar >= .profiles[2].selected_counts.grammar
' "$DENSITY/density-comparison.json" >/dev/null

run_density_failure() {
  local name="$1"
  local expected="$2"
  local book="$3"
  local annotation="$4"
  local grammar="$5"
  local assistance="$6"
  local policies="$7"
  mkdir -p "$DENSITY/cases/$name"
  "$PYTHON" "$ROOT/scripts/create_assistance_density.py" \
    --canonical-book "$book" --annotation-plan "$annotation" \
    --grammar-plan "$grammar" --assistance-report "$assistance" \
    --density-policies "$policies" --policy-id phase8-density-n5 \
    --output "$DENSITY/cases/$name/report.json" \
    --fallback-plan-output "$DENSITY/cases/$name/annotation-plan.json" \
    --fallback-grammar-plan-output "$DENSITY/cases/$name/grammar-plan.json" \
    --enabled --safe
  jq -e --arg reason "$expected" '.occurrence_plans == [] and .chapter_summaries == [] and [.diagnostics[].reason] == [$reason]' "$DENSITY/cases/$name/report.json" >/dev/null
  cmp "$DENSITY/cases/$name/annotation-plan.json" "$annotation"
  cmp "$DENSITY/cases/$name/grammar-plan.json" "$grammar"
}

mkdir -p "$DENSITY/cases/disabled"
"$PYTHON" "$ROOT/scripts/create_assistance_density.py" \
  --canonical-book "$SOURCE_BOOK" --annotation-plan "$SOURCE_PLAN" \
  --grammar-plan "$SOURCE_GRAMMAR" \
  --output "$DENSITY/cases/disabled/report.json" \
  --fallback-plan-output "$DENSITY/cases/disabled/annotation-plan.json" \
  --fallback-grammar-plan-output "$DENSITY/cases/disabled/grammar-plan.json" --safe
jq -e '.occurrence_plans == [] and [.diagnostics[].reason] == ["disabled"]' "$DENSITY/cases/disabled/report.json" >/dev/null
cmp "$DENSITY/cases/disabled/annotation-plan.json" "$SOURCE_PLAN"
cmp "$DENSITY/cases/disabled/grammar-plan.json" "$SOURCE_GRAMMAR"

run_density_failure stale source-hash-mismatch "$SOURCE_BOOK" "$SOURCE_PLAN" "$SOURCE_GRAMMAR" "$DENSITY/cases/inputs/stale-assistance.json" "$DENSITY_FIXTURE"
run_density_failure invalid invalid-density-target "$SOURCE_BOOK" "$SOURCE_PLAN" "$SOURCE_GRAMMAR" "$ARTIFACTS/run-a/assistance.json" "$DENSITY/cases/inputs/invalid-policies.json"
run_density_failure unknown-occurrence unknown-occurrence "$SOURCE_BOOK" "$SOURCE_PLAN" "$SOURCE_GRAMMAR" "$DENSITY/cases/inputs/unknown-assistance.json" "$DENSITY_FIXTURE"
run_density_failure publisher-conflict publisher-ruby-suppression-attempt "$SOURCE_BOOK" "$DENSITY/cases/inputs/publisher-conflict-plan.json" "$SOURCE_GRAMMAR" "$DENSITY/cases/inputs/publisher-conflict-assistance.json" "$DENSITY_FIXTURE"
run_density_failure grammar-conflict grammar-disposition-conflict "$SOURCE_BOOK" "$SOURCE_PLAN" "$DENSITY/cases/inputs/grammar-conflict-plan.json" "$DENSITY/cases/inputs/grammar-conflict-assistance.json" "$DENSITY_FIXTURE"

mkdir -p "$DENSITY/cases/corrupt"
"$PYTHON" "$ROOT/scripts/create_assistance_density.py" \
  --canonical-book "$SOURCE_BOOK" --annotation-plan "$SOURCE_PLAN" \
  --grammar-plan "$SOURCE_GRAMMAR" \
  --assistance-report "$DENSITY/cases/inputs/corrupt.json" \
  --density-policies "$DENSITY_FIXTURE" \
  --output "$DENSITY/cases/corrupt/report.json" \
  --fallback-plan-output "$DENSITY/cases/corrupt/annotation-plan.json" \
  --fallback-grammar-plan-output "$DENSITY/cases/corrupt/grammar-plan.json" \
  --enabled --safe
jq -e '.occurrence_plans == [] and [.diagnostics[].reason] == ["corrupt-input"]' "$DENSITY/cases/corrupt/report.json" >/dev/null
cmp "$DENSITY/cases/corrupt/annotation-plan.json" "$SOURCE_PLAN"
cmp "$DENSITY/cases/corrupt/grammar-plan.json" "$SOURCE_GRAMMAR"

cp "$SOURCE_PLAN" "$DENSITY/compatibility/phase5-plan.json"
cp "$COMPAT_PLAN" "$DENSITY/compatibility/phase5-approved-plan.json"
cp "$SOURCE_GRAMMAR" "$DENSITY/compatibility/phase7-grammar-plan.json"
cp "$ARTIFACTS/run-a/assistance.json" "$DENSITY/compatibility/phase8-assistance.json"
cp "$COMPAT_VOCABULARY" "$DENSITY/compatibility/phase3-vocabulary.json"
cmp "$DENSITY/compatibility/phase5-plan.json" "$SOURCE_PLAN"
cmp "$DENSITY/compatibility/phase5-approved-plan.json" "$COMPAT_PLAN"
cmp "$DENSITY/compatibility/phase7-grammar-plan.json" "$SOURCE_GRAMMAR"
cmp "$DENSITY/compatibility/phase8-assistance.json" "$ARTIFACTS/run-a/assistance.json"
cmp "$DENSITY/compatibility/phase3-vocabulary.json" "$COMPAT_VOCABULARY"
test "$(sha256sum "$ROOT/artifacts/phase7/epub/run-a.epub" | cut -d' ' -f1)" = "df4c4bf0f072c01ac0a8d8aff316ee92613760c1822274cecd7ec9ce409a9619"

"$PYTHON" -m pytest -q "$ROOT/tests/test_learner_profile.py" "$ROOT/tests/test_assistance_density.py"
echo "Phase 8 adaptive-density regression passed; artifacts retained under artifacts/phase8/density/."
