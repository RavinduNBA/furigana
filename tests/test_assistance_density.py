import copy
import json
import subprocess
from pathlib import Path

import pytest

from furiganalyse.assistance_density import (
    build_density_report,
    load_json,
    safe_build_density_report,
    serialize_density_report,
    stable_hash,
    validate_density_policy_dataset,
    validate_density_report,
)
from furiganalyse.learner_profile import build_assistance_report
from scripts.build_phase7_fixture import build

ROOT = Path(__file__).resolve().parents[1]
PHASE8 = ROOT / "tests/fixtures/phase8"
POLICIES = ROOT / "tests/fixtures/phase8-density-policies-v1.json"


def rehash(value):
    value["hash"] = stable_hash({key: item for key, item in value.items() if key != "hash"})
    return value


@pytest.fixture
def inputs():
    spec = load_json(ROOT / "tests/fixtures/phase7-passages-v1.json")
    book, vocabulary, plan = build(spec)
    grammar = load_json(ROOT / "tests/phase7_golden/grammar-plan-v1.json")
    presets = load_json(PHASE8 / "phase8-presets-v1.json")
    profile = load_json(PHASE8 / "phase8-profile-baseline-v1.json")
    exposure = load_json(PHASE8 / "phase8-exposure-history-v1.json")
    assistance = build_assistance_report(
        vocabulary, plan, grammar, profile, presets, exposure, enabled=True
    )
    return book, plan, grammar, assistance, load_json(POLICIES)


def report(inputs, policy_id="phase8-density-n5"):
    return build_density_report(*inputs, policy_id=policy_id, enabled=True)


def by_occurrence(value):
    return {item["source_occurrence_id"]: item for item in value["occurrence_plans"]}


def test_character_counts_integer_budgets_and_order(inputs):
    value = report(inputs)
    assert [chapter["canonical_character_count"] for chapter in value["chapter_summaries"]] == [67, 18]
    first = value["chapter_summaries"][0]
    assert first["normal_budgets"]["reading"]["target_numerator"] == 536
    assert first["normal_budgets"]["reading"]["target_denominator"] == 1000
    assert first["normal_budgets"]["reading"]["final_budget"] == 1
    assert [item["canonical_source_order"] for item in value["occurrence_plans"]] == list(range(1, 13))
    assert all(
        isinstance(item["sentence_start"], int)
        and isinstance(item["sentence_end"], int)
        and item["sentence_start"] < item["sentence_end"]
        for item in value["occurrence_plans"]
    )


def test_all_occurrences_retained_and_kinds_separate(inputs):
    value = report(inputs)
    assert len(value["occurrence_plans"]) == 12
    assert {item["item_kind"] for item in value["occurrence_plans"]} == {
        "vocabulary", "expression", "name", "grammar"
    }
    assert len({item["source_occurrence_id"] for item in value["occurrence_plans"]}) == 12


def test_hidden_states_and_explicit_hide_are_suppressed(inputs):
    values = by_occurrence(report(inputs))
    assert values["study-item-0001-occ-0001"]["density_decisions"]["reading"] == "suppressed-input-state"
    assert values["study-item-0003-occ-0001"]["density_decisions"]["reading"] == "suppressed-explicit-override"
    assert values["study-item-0004-occ-0001"]["density_decisions"]["meaning"] == "suppressed-explicit-override"


def test_explicit_show_can_be_selected_over_budget(inputs):
    value = report(inputs)
    selected = by_occurrence(value)["grammar-plan-occurrence-0002"]
    assert selected["density_decisions"]["grammar"] == "selected-explicit-override-over-budget"
    assert selected["planned_assistance"]["grammar"] == "present-grammar"
    assert value["chapter_summaries"][0]["explicit_override_over_budget_counts"]["grammar"] == 1


def test_publisher_ruby_and_adjacent_grammar_are_protected(inputs):
    values = by_occurrence(report(inputs))
    ruby = values["study-item-0004-occ-0001"]
    adjacent = values["grammar-plan-occurrence-0006"]
    assert ruby["planned_assistance"]["reading"] == "publisher-ruby-preserved"
    assert ruby["density_decisions"]["reading"] == "publisher-ruby-preserved"
    assert adjacent["density_decisions"]["grammar"] == "publisher-adjacent-protected"


def test_grammar_dispositions_cannot_be_promoted(inputs):
    values = by_occurrence(report(inputs))
    assert values["grammar-plan-occurrence-0003"]["density_decisions"]["grammar"] == "grammar-partial-overlap-rejected"
    assert values["grammar-plan-occurrence-0004"]["density_decisions"]["grammar"] == "grammar-reference-only"


def test_repeated_occurrences_are_distinct_and_first_preferred(inputs):
    values = [
        item for item in report(inputs)["occurrence_plans"]
        if item["source_item_id"] == "grammar-item-0001"
    ]
    assert [item["source_occurrence_id"] for item in values] == [
        "grammar-plan-occurrence-0001", "grammar-plan-occurrence-0005",
        "grammar-plan-occurrence-0006",
    ]
    assert len({item["hash"] for item in values}) == 3

    spec = load_json(ROOT / "tests/fixtures/phase7-passages-v1.json")
    book, vocabulary, plan = build(spec)
    grammar = load_json(ROOT / "tests/phase7_golden/grammar-plan-v1.json")
    presets = load_json(PHASE8 / "phase8-presets-v1.json")
    profile = load_json(PHASE8 / "phase8-profile-n5-v1.json")
    assistance = build_assistance_report(
        vocabulary, plan, grammar, profile, presets, enabled=True
    )
    n5 = build_density_report(
        book, plan, grammar, assistance, load_json(POLICIES),
        policy_id="phase8-density-n5", enabled=True,
    )
    repeated = [
        item for item in n5["occurrence_plans"]
        if item["source_item_id"] == "grammar-item-0001"
    ]
    assert [item["density_decisions"]["grammar"] for item in repeated] == [
        "grammar-reference-only", "suppressed-density-budget",
        "publisher-adjacent-protected",
    ]


def test_density_policy_is_monotonic_and_valid(inputs):
    policies = inputs[-1]
    validate_density_policy_dataset(policies)
    targets = [sum(value["targets_per_1000"].values()) for value in policies["policies"]]
    assert targets == [21, 10, 5]


def test_n5_n4_n3_plans_are_monotonic():
    spec = load_json(ROOT / "tests/fixtures/phase7-passages-v1.json")
    book, vocabulary, plan = build(spec)
    grammar = load_json(ROOT / "tests/phase7_golden/grammar-plan-v1.json")
    presets = load_json(PHASE8 / "phase8-presets-v1.json")
    policies = load_json(POLICIES)
    totals = []
    source_references = []
    for level in ("n5", "n4", "n3"):
        profile = load_json(PHASE8 / f"phase8-profile-{level}-v1.json")
        assistance = build_assistance_report(
            vocabulary, plan, grammar, profile, presets, enabled=True
        )
        density = build_density_report(
            book, plan, grammar, assistance, policies,
            policy_id=f"phase8-density-{level}", enabled=True,
        )
        totals.append(sum(
            sum(chapter["selected_action_counts"].values())
            for chapter in density["chapter_summaries"]
        ))
        source_references.append([
            (
                value["source_item_id"], value["source_occurrence_id"],
                value["chapter_id"], value["block_id"], value["sentence_id"],
                value["sentence_start"], value["sentence_end"], value["token_ids"],
            ) for value in density["occurrence_plans"]
        ])
    assert totals[0] >= totals[1] >= totals[2]
    assert source_references[0] == source_references[1] == source_references[2]


@pytest.mark.parametrize(
    ("profile_name", "reading", "meaning"),
    [
        ("show-show", "present-reading", "present-meaning"),
        ("show-hide", "present-reading", "suppress-meaning"),
        ("hide-show", "suppress-reading", "present-meaning"),
        ("hide-hide", "suppress-reading", "suppress-meaning"),
    ],
)
def test_all_four_input_combinations(profile_name, reading, meaning):
    spec = load_json(ROOT / "tests/fixtures/phase7-passages-v1.json")
    book, vocabulary, plan = build(spec)
    grammar = load_json(ROOT / "tests/phase7_golden/grammar-plan-v1.json")
    presets = load_json(PHASE8 / "phase8-presets-v1.json")
    profile = load_json(PHASE8 / f"phase8-profile-{profile_name}-v1.json")
    assistance = build_assistance_report(
        vocabulary, plan, grammar, profile, presets, enabled=True
    )
    density = build_density_report(
        book, plan, grammar, assistance, load_json(POLICIES),
        policy_id="phase8-density-n5", enabled=True,
    )
    study = next(item for item in density["occurrence_plans"] if item["source_item_id"] == "study-item-0001")
    assert study["planned_assistance"]["reading"] == reading
    assert study["planned_assistance"]["meaning"] == meaning


def test_stable_hashes_serialization_and_validation(inputs):
    first = report(inputs)
    second = report(inputs)
    assert serialize_density_report(first) == serialize_density_report(second)
    assert all(item["hash"] == stable_hash({k: v for k, v in item.items() if k != "hash"}) for item in first["occurrence_plans"])
    validate_density_report(*inputs, first, policy_id="phase8-density-n5")


def test_unknown_duplicate_cross_chapter_and_stale_inputs_fail_safely(inputs):
    values = copy.deepcopy(inputs)
    values[3]["results"][0]["occurrence_ids"] = ["unknown-occurrence"]
    rehash(values[3]["results"][0])
    rehash(values[3])
    assert safe_build_density_report(*values, policy_id="phase8-density-n5", enabled=True)["diagnostics"][0]["reason"] == "unknown-occurrence"

    values = copy.deepcopy(inputs)
    values[3]["results"][1]["occurrence_ids"] = values[3]["results"][0]["occurrence_ids"]
    rehash(values[3]["results"][1])
    rehash(values[3])
    assert safe_build_density_report(*values, policy_id="phase8-density-n5", enabled=True)["diagnostics"][0]["reason"] == "duplicate-occurrence"

    values = copy.deepcopy(inputs)
    values[1]["items"][0]["occurrences"][0]["chapter_id"] = "ch-0002"
    assert safe_build_density_report(*values, policy_id="phase8-density-n5", enabled=True)["diagnostics"][0]["reason"] == "source-hash-mismatch"

    values = copy.deepcopy(inputs)
    values[3]["source_hashes"]["annotation_plan"] = "0" * 64
    rehash(values[3])
    assert safe_build_density_report(*values, policy_id="phase8-density-n5", enabled=True)["diagnostics"][0]["reason"] == "source-hash-mismatch"

    values = copy.deepcopy(inputs)
    values[0]["chapters"][0]["blocks"][0]["sentences"][0]["text"] = "本を違っている。"
    assert safe_build_density_report(*values, policy_id="phase8-density-n5", enabled=True)["diagnostics"][0]["reason"] == "invalid-occurrence-offset"


def test_invalid_policy_and_mismatch_fail_safely(inputs):
    values = copy.deepcopy(inputs)
    values[-1]["policies"][0]["targets_per_1000"]["reading"] = -1
    rehash(values[-1]["policies"][0])
    rehash(values[-1])
    assert safe_build_density_report(*values, policy_id="phase8-density-n5", enabled=True)["diagnostics"][0]["reason"] == "invalid-density-target"
    assert safe_build_density_report(*inputs, policy_id="phase8-density-n4", enabled=True)["diagnostics"][0]["reason"] == "preset-policy-mismatch"


def test_disabled_and_corrupt_cli_preserve_fallbacks(inputs, tmp_path):
    names = ("book", "plan", "grammar", "assistance", "policies")
    paths = {}
    for name, value in zip(names, inputs):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        paths[name] = path
    subprocess.run([
        str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/create_assistance_density.py"),
        "--canonical-book", str(paths["book"]), "--annotation-plan", str(paths["plan"]),
        "--grammar-plan", str(paths["grammar"]), "--output", str(tmp_path / "disabled.json"),
        "--fallback-plan-output", str(tmp_path / "fallback-plan.json"),
        "--fallback-grammar-plan-output", str(tmp_path / "fallback-grammar.json"), "--safe",
    ], check=True)
    assert load_json(tmp_path / "disabled.json")["diagnostics"][0]["reason"] == "disabled"
    assert (tmp_path / "fallback-plan.json").read_bytes() == paths["plan"].read_bytes()
    assert (tmp_path / "fallback-grammar.json").read_bytes() == paths["grammar"].read_bytes()

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{", encoding="utf-8")
    subprocess.run([
        str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/create_assistance_density.py"),
        "--canonical-book", str(paths["book"]), "--annotation-plan", str(paths["plan"]),
        "--grammar-plan", str(paths["grammar"]), "--assistance-report", str(corrupt),
        "--density-policies", str(paths["policies"]), "--output", str(tmp_path / "corrupt-report.json"),
        "--enabled", "--safe",
    ], check=True)
    assert load_json(tmp_path / "corrupt-report.json")["diagnostics"][0]["reason"] == "corrupt-input"


def test_sources_are_not_mutated(inputs):
    before = json.dumps(inputs, ensure_ascii=False, sort_keys=True)
    report(inputs)
    assert json.dumps(inputs, ensure_ascii=False, sort_keys=True) == before
