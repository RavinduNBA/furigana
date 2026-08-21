import copy
import json
import subprocess
from pathlib import Path

import pytest

from furiganalyse.learner_profile import (
    build_assistance_report,
    load_json,
    safe_build_assistance_report,
    serialize_assistance_report,
    stable_hash,
    validate_assistance_report,
    validate_exposure_history,
    validate_preset_dataset,
    validate_profile,
)
from scripts.build_phase7_fixture import build

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/phase8"


def rehash(value):
    value["hash"] = stable_hash({key: item for key, item in value.items() if key != "hash"})
    return value


@pytest.fixture
def inputs():
    spec = load_json(ROOT / "tests/fixtures/phase7-passages-v1.json")
    _, vocabulary, annotation_plan = build(spec)
    grammar_plan = load_json(ROOT / "tests/phase7_golden/grammar-plan-v1.json")
    presets = load_json(FIXTURES / "phase8-presets-v1.json")
    exposure = load_json(FIXTURES / "phase8-exposure-history-v1.json")
    profile = load_json(FIXTURES / "phase8-profile-baseline-v1.json")
    return vocabulary, annotation_plan, grammar_plan, profile, presets, exposure


def report(inputs, profile=None, exposure=True):
    vocabulary, plan, grammar, baseline, presets, history = inputs
    return build_assistance_report(
        vocabulary,
        plan,
        grammar,
        profile or baseline,
        presets,
        history if exposure else None,
        enabled=True,
    )


def result_by_id(value):
    return {item["source_item_id"]: item for item in value["results"]}


@pytest.mark.parametrize(
    ("fixture", "reading", "meaning"),
    [
        ("show-show", "show-reading", "show-meaning"),
        ("show-hide", "show-reading", "hide-meaning"),
        ("hide-show", "hide-reading", "show-meaning"),
        ("hide-hide", "hide-reading", "hide-meaning"),
    ],
)
def test_all_four_reading_meaning_combinations(inputs, fixture, reading, meaning):
    profile = load_json(FIXTURES / f"phase8-profile-{fixture}-v1.json")
    values = report(inputs, profile, exposure=False)["results"][:5]
    assert {(value["reading_assistance"], value["meaning_assistance"]) for value in values} == {(reading, meaning)}


def test_grammar_assistance_is_independent(inputs):
    profile = load_json(FIXTURES / "phase8-profile-hide-show-v1.json")
    values = report(inputs, profile, exposure=False)["results"]
    assert all(value["grammar_assistance"] is None for value in values[:5])
    assert all(value["reading_assistance"] is None and value["meaning_assistance"] is None for value in values[5:])
    assert all(value["grammar_assistance"] == "hide-grammar" for value in values[5:])


def test_n5_n4_n3_presets_are_explainable_and_monotonic(inputs):
    observed = []
    for level in ("n5", "n4", "n3"):
        profile = load_json(FIXTURES / f"phase8-profile-{level}-v1.json")
        values = report(inputs, profile, exposure=False)["results"]
        observed.append((
            values[0]["reading_assistance"],
            values[0]["meaning_assistance"],
            values[5]["grammar_assistance"],
        ))
        assert all("preset" in {source for source in value["effective_sources"].values() if source} for value in values)
    assert observed == [
        ("show-reading", "show-meaning", "show-grammar"),
        ("hide-reading", "show-meaning", "show-grammar"),
        ("hide-reading", "hide-meaning", "hide-grammar"),
    ]


def test_baseline_overrides_outrank_preset_and_exposure(inputs):
    values = result_by_id(report(inputs))
    assert values["study-item-0003"]["reading_assistance"] == "hide-reading"
    assert values["study-item-0003"]["effective_sources"]["reading"] == "explicit_user_override"
    assert values["study-item-0004"]["meaning_assistance"] == "hide-meaning"
    assert values["study-item-0004"]["effective_sources"]["meaning"] == "explicit_user_override"
    assert values["grammar-item-0002"]["grammar_assistance"] == "show-grammar"
    assert values["grammar-item-0002"]["effective_sources"]["grammar"] == "explicit_user_override"


def test_exposure_changes_only_configured_dimension(inputs):
    without = result_by_id(report(inputs, exposure=False))
    with_history = result_by_id(report(inputs))
    assert with_history["study-item-0001"]["reading_assistance"] == "hide-reading"
    assert without["study-item-0001"]["meaning_assistance"] == with_history["study-item-0001"]["meaning_assistance"]
    assert with_history["study-item-0002"]["meaning_assistance"] == "hide-meaning"
    assert without["study-item-0002"]["reading_assistance"] == with_history["study-item-0002"]["reading_assistance"]
    assert with_history["grammar-item-0001"]["grammar_assistance"] == "hide-grammar"


def test_exposure_below_and_at_threshold(inputs):
    values = copy.deepcopy(inputs)
    history = values[5]
    history["records"][0]["count"] = 2
    rehash(history["records"][0])
    rehash(history)
    below = report(tuple(values))["results"][0]
    assert below["reading_assistance"] == "show-reading"
    history["records"][0]["count"] = 3
    rehash(history["records"][0])
    rehash(history)
    at = report(tuple(values))["results"][0]
    assert at["reading_assistance"] == "hide-reading"


def test_publisher_ruby_is_preserved_in_every_reading_state(inputs):
    for fixture in ("show-show", "hide-show", "hide-hide", "baseline"):
        profile = load_json(FIXTURES / f"phase8-profile-{fixture}-v1.json")
        selected = result_by_id(report(inputs, profile, exposure=fixture == "baseline"))
        assert selected["study-item-0004"]["publisher_ruby_protection"] == "preserved-authoritative"
        assert selected["grammar-item-0001"]["publisher_ruby_protection"] == "preserved-authoritative"


def test_vocabulary_expression_name_and_grammar_remain_separate(inputs):
    values = report(inputs)["results"]
    assert [value["item_kind"] for value in values] == [
        "vocabulary", "expression", "vocabulary", "vocabulary", "name",
        "grammar", "grammar", "grammar", "grammar", "grammar",
    ]
    assert values[4]["approved_meaning_reference"] is not None
    assert all(value["approved_meaning_reference"] is None for value in values[5:])


def test_stable_ids_hashes_ordering_and_serialization(inputs):
    first = report(inputs)
    second = report(inputs)
    assert serialize_assistance_report(first) == serialize_assistance_report(second)
    assert [value["id"] for value in first["results"]] == [
        f"assistance-result-{number:04d}" for number in range(1, 11)
    ]
    assert all(value["hash"] == stable_hash({key: item for key, item in value.items() if key != "hash"}) for value in first["results"])
    validate_assistance_report(*inputs, first)


def test_preset_profile_and_exposure_hash_validation(inputs):
    vocabulary, plan, grammar, profile, presets, exposure = inputs
    source_hashes = {
        "vocabulary": stable_hash(vocabulary),
        "annotation_plan": stable_hash(plan),
        "grammar_plan": stable_hash(grammar),
    }
    validate_preset_dataset(presets)
    validate_profile(profile, presets, source_hashes)
    validate_exposure_history(exposure, source_hashes)


def test_unknown_duplicate_and_cross_kind_overrides_fail_safely(inputs):
    for mutation, reason in (
        ("unknown", "unknown-override"),
        ("duplicate", "duplicate-override"),
        ("cross-kind", "cross-kind-override"),
    ):
        values = copy.deepcopy(inputs)
        profile = values[3]
        if mutation == "unknown":
            profile["overrides"][0]["target_id"] = "study-item-9999"
            rehash(profile["overrides"][0])
        elif mutation == "duplicate":
            duplicate = copy.deepcopy(profile["overrides"][0])
            duplicate["id"] = "phase8-override-0099"
            rehash(duplicate)
            profile["overrides"].append(duplicate)
        else:
            profile["overrides"][0]["target_kind"] = "grammar"
            rehash(profile["overrides"][0])
        rehash(profile)
        failure = safe_build_assistance_report(*values, enabled=True)
        assert [value["reason"] for value in failure["diagnostics"]] == [reason]
        assert failure["results"] == []


def test_negative_duplicate_and_unknown_exposure_rejected(inputs):
    for mutation, expected in (
        ("negative", "negative-exposure-count"),
        ("duplicate", "duplicate-exposure"),
        ("unknown", "unknown-occurrence-reference"),
    ):
        values = copy.deepcopy(inputs)
        history = values[5]
        if mutation == "negative":
            history["records"][0]["count"] = -1
            rehash(history["records"][0])
        elif mutation == "duplicate":
            duplicate = copy.deepcopy(history["records"][0])
            duplicate["id"] = "phase8-exposure-0099"
            rehash(duplicate)
            history["records"].append(duplicate)
        else:
            history["records"][0]["occurrence_ids"] = ["unknown-occurrence"]
            rehash(history["records"][0])
        rehash(history)
        failure = safe_build_assistance_report(*values, enabled=True)
        assert [value["reason"] for value in failure["diagnostics"]] == [expected]


def test_exposure_last_location_and_order_are_exact(inputs):
    values = copy.deepcopy(inputs)
    history = values[5]
    history["records"][0]["last_observed"]["sentence_id"] = "unknown-sentence"
    rehash(history["records"][0])
    rehash(history)
    assert safe_build_assistance_report(*values, enabled=True)["diagnostics"][0]["reason"] == "unknown-occurrence-reference"

    values = copy.deepcopy(inputs)
    history = values[5]
    history["records"] = list(reversed(history["records"]))
    rehash(history)
    assert safe_build_assistance_report(*values, enabled=True)["diagnostics"][0]["reason"] == "invalid-input"


def test_invalid_states_unsafe_notes_and_source_mismatch_are_rejected(inputs):
    values = copy.deepcopy(inputs)
    values[3]["reading_assistance_policy"]["state"] = "sometimes"
    rehash(values[3])
    assert safe_build_assistance_report(*values, enabled=True)["diagnostics"][0]["reason"] == "invalid-input"

    values = copy.deepcopy(inputs)
    values[3]["overrides"][0]["reviewer_note"] = "<script>bad</script>"
    rehash(values[3]["overrides"][0])
    rehash(values[3])
    assert safe_build_assistance_report(*values, enabled=True)["diagnostics"][0]["reason"] == "invalid-input"

    values = copy.deepcopy(inputs)
    values[3]["source_references"]["vocabulary_hash"] = "0" * 64
    rehash(values[3])
    assert safe_build_assistance_report(*values, enabled=True)["diagnostics"][0]["reason"] == "source-hash-mismatch"


def test_disabled_and_corrupt_cli_are_safe_and_preserve_plan(inputs, tmp_path):
    vocabulary, plan, grammar, profile, presets, exposure = inputs
    paths = {}
    for name, value in {
        "vocabulary": vocabulary,
        "plan": plan,
        "grammar": grammar,
        "profile": profile,
        "presets": presets,
        "exposure": exposure,
    }.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        paths[name] = path
    fallback = tmp_path / "fallback.json"
    subprocess.run([
        str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/create_assistance_selection.py"),
        "--vocabulary", str(paths["vocabulary"]), "--annotation-plan", str(paths["plan"]),
        "--grammar-plan", str(paths["grammar"]), "--output", str(tmp_path / "disabled.json"),
        "--fallback-plan-output", str(fallback), "--safe",
    ], check=True)
    assert load_json(tmp_path / "disabled.json")["diagnostics"][0]["reason"] == "disabled"
    assert fallback.read_bytes() == paths["plan"].read_bytes()

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{", encoding="utf-8")
    subprocess.run([
        str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/create_assistance_selection.py"),
        "--vocabulary", str(paths["vocabulary"]), "--annotation-plan", str(paths["plan"]),
        "--grammar-plan", str(paths["grammar"]), "--profile", str(corrupt),
        "--presets", str(paths["presets"]), "--output", str(tmp_path / "corrupt-report.json"),
        "--fallback-plan-output", str(tmp_path / "corrupt-fallback.json"), "--enabled", "--safe",
    ], check=True)
    assert load_json(tmp_path / "corrupt-report.json")["diagnostics"][0]["reason"] == "corrupt-input"
    assert (tmp_path / "corrupt-fallback.json").read_bytes() == paths["plan"].read_bytes()


def test_sources_are_not_mutated(inputs):
    before = [json.dumps(value, ensure_ascii=False, sort_keys=True) for value in inputs]
    report(inputs)
    after = [json.dumps(value, ensure_ascii=False, sort_keys=True) for value in inputs]
    assert before == after


def test_approved_phase3_phase5_sources_work_without_grammar():
    vocabulary = load_json(ROOT / "tests/phase3_golden/vocabulary-jmnedict-v4.json")
    plan = load_json(ROOT / "tests/phase5_golden/enriched-plan-v2.json")
    presets = load_json(FIXTURES / "phase8-presets-v1.json")
    profile = load_json(FIXTURES / "phase8-profile-n5-v1.json")
    profile["source_references"] = {
        "vocabulary_hash": stable_hash(vocabulary),
        "annotation_plan_hash": stable_hash(plan),
        "grammar_plan_hash": "none",
        "preset_dataset_hash": presets["hash"],
    }
    rehash(profile)
    selected = build_assistance_report(
        vocabulary, plan, None, profile, presets, enabled=True
    )
    assert [value["item_kind"] for value in selected["results"]] == [
        "expression", "vocabulary", "vocabulary", "name", "vocabulary"
    ]
    values = result_by_id(selected)
    assert values["study-item-0003"]["authoritative_reading"] == "おもてぶたい"
    assert values["study-item-0003"]["reading_source"] == "publisher"
    assert values["study-item-0004"]["item_kind"] == "name"
    assert values["study-item-0004"]["approved_meaning_reference"]["selected_translation_id"] == "jmnedict-2001-translation-0001"
