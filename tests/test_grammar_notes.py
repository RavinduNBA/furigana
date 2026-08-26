import copy
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from furiganalyse.grammar_analysis import detect_grammar, load_json, stable_hash
from furiganalyse.grammar_notes import (
    XHTML_NS,
    GrammarNoteError,
    render_grammar_notes,
    validate_grammar_plan_for_notes,
)
from furiganalyse.grammar_plan import build_grammar_plan
from scripts.build_phase7_fixture import build

ROOT = Path(__file__).resolve().parents[1]
XHTML = f"{{{XHTML_NS}}}"


@pytest.fixture
def values():
    dataset = load_json(ROOT / "tests/fixtures/phase7-grammar-rules-v1.json")
    book, vocabulary, annotation = build(load_json(ROOT / "tests/fixtures/phase7-passages-v1.json"))
    report = detect_grammar(book, vocabulary, annotation, dataset)
    plan = build_grammar_plan(book, vocabulary, annotation, report, dataset, enabled=True)
    return plan, dataset


def parsed(values, **options):
    data = render_grammar_notes(*values, **options)
    return data, ET.fromstring(data)


def test_default_document_is_valid_ordered_grammar_only_xhtml(values):
    data, root = parsed(values)
    assert data.startswith(b"<?xml version='1.0' encoding='utf-8'?>")
    assert root.attrib["lang"] == "ja"
    sections = root.findall(f".//{XHTML}section")
    assert [x.attrib["data-grammar-item-id"] for x in sections] == [
        f"grammar-item-{number:04d}" for number in range(1, 6)
    ]
    assert [x.find(f"{XHTML}h2").text for x in sections] == [
        "〜ている", "〜たことがある", "〜ようにする", "〜てしまう", "〜なければならない"
    ]
    assert [x.attrib["id"] for x in sections] == [f"grammar-note-{number:04d}" for number in range(1, 6)]
    assert not root.findall(f".//{XHTML}a") and not root.findall(f".//{XHTML}ruby")


def test_curated_content_provenance_counts_and_repeated_occurrences(values):
    _, root = parsed(values)
    sections = root.findall(f".//{XHTML}section")
    first = " ".join("".join(sections[0].itertext()).split())
    assert "ongoing or resulting state" in first
    assert "Marks an ongoing action or resulting state." in first
    assert "verb te-form + いる" in first
    assert "Occurrences (3)" in first
    assert first.count("読んでいる") == 3
    assert "furiganalyse-synthetic-grammar 2026-08-18" in first
    obligation = " ".join("".join(sections[-1].itertext()).split())
    assert "neutral" in obligation and "grammar-rule-0003" in obligation


def test_publisher_protection_is_text_status_without_ruby(values):
    _, root = parsed(values)
    text = "".join(root.itertext())
    assert "publisher ruby preserved" in text
    assert "おもてぶたい" not in text
    assert not root.findall(f".//{XHTML}ruby")


def test_serialization_and_escaping_are_deterministic(values):
    plan, dataset = copy.deepcopy(values)
    plan["items"][0]["label"] = "ongoing & resulting"
    dataset["rules"][0]["label"] = "ongoing & resulting"
    dataset["rules"][0]["hash"] = stable_hash({k: v for k, v in dataset["rules"][0].items() if k != "hash"})
    plan["items"][0]["rule_hash"] = dataset["rules"][0]["hash"]
    plan["items"][0]["hash"] = stable_hash({k: v for k, v in plan["items"][0].items() if k != "hash"})
    first = render_grammar_notes(plan, dataset, title="Grammar & Notes")
    assert first == render_grammar_notes(plan, dataset, title="Grammar & Notes")
    assert b"Grammar &amp; Notes" in first and b"ongoing &amp; resulting" in first


def test_synthetic_rule_requires_explicit_test_permission(values):
    plan, dataset = values
    book, vocabulary, annotation = build(load_json(ROOT / "tests/fixtures/phase7-passages-v1.json"))
    report = detect_grammar(book, vocabulary, annotation, dataset)
    synthetic = build_grammar_plan(
        book, vocabulary, annotation, report, dataset, enabled=True,
        include_synthetic_mechanics=True, per_chapter_limit=5,
    )
    with pytest.raises(GrammarNoteError, match="test-only permission"):
        render_grammar_notes(synthetic, dataset)
    data = render_grammar_notes(synthetic, dataset, allow_synthetic_mechanics=True)
    assert "〜て".encode() in data and data.count(b"grammar-study-note\"") == 6


def _set_unknown_occurrence(plan, _dataset):
    plan["items"][0]["occurrence_ids"] = ["missing"]
    plan["items"][0]["hash"] = stable_hash({
        key: value for key, value in plan["items"][0].items() if key != "hash"
    })


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda p, d: p.update(schema_version=2), "Unsupported"),
        (lambda p, d: p["config"].update(enabled=False), "disabled"),
        (lambda p, d: p["items"][0].update(rule_hash="stale"), "Stale"),
        (lambda p, d: p["items"][0].update(label="<script>bad</script>"), "content changed"),
        (_set_unknown_occurrence, "Unknown"),
        (lambda p, d: p["items"].reverse(), "unstable"),
    ],
)
def test_validation_rejects_invalid_or_unsafe_records(values, change, message):
    plan, dataset = copy.deepcopy(values)
    change(plan, dataset)
    with pytest.raises(GrammarNoteError, match=message):
        validate_grammar_plan_for_notes(plan, dataset)


def test_css_and_output_exclude_other_layers_and_provider_metadata(values):
    data, root = parsed(values)
    css = root.find(f"{XHTML}head/{XHTML}style").text.strip().splitlines()
    assert all(line.startswith((".grammar-notes", ".grammar-study-note")) for line in css)
    text = data.decode()
    for forbidden in ("JMdict", "JMnedict", "provider", "model", "cache", "prompt", "context_hash", "<script", "href=", "src="):
        assert forbidden not in text


def test_existing_vocabulary_note_golden_is_unchanged():
    expected = ROOT / "tests/phase4_golden/study-notes-v1.xhtml"
    current = ROOT / "artifacts/phase4/notes/run-a/study-notes.xhtml"
    assert current.read_bytes() == expected.read_bytes()
