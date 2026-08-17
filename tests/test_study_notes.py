import copy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from furiganalyse.study_notes import (
    XHTML_NS,
    StudyNoteError,
    render_study_notes,
    validate_annotation_plan_for_notes,
)

PLAN_PATH = (
    Path(__file__).resolve().parents[1] / "tests/phase4_golden/annotation-plan-v1.json"
)
XHTML = f"{{{XHTML_NS}}}"


@pytest.fixture
def plan():
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def parsed(plan):
    data = render_study_notes(plan)
    return data, ET.fromstring(data)


def test_renders_valid_namespaced_xhtml_in_plan_order(plan):
    data, root = parsed(plan)
    assert data.startswith(b"<?xml version='1.0' encoding='utf-8'?>")
    assert root.tag == f"{XHTML}html" and root.attrib["lang"] == "en"
    assert root.find(f"{XHTML}head/{XHTML}meta").attrib["charset"] == "utf-8"
    sections = root.findall(f".//{XHTML}section")
    assert [x.attrib["data-item-id"] for x in sections] == [
        x["id"] for x in plan["items"]
    ]
    assert [x.attrib["id"] for x in sections] == [
        x["note_anchor_id"] for x in plan["items"]
    ]
    assert len({x.attrib["id"] for x in sections}) == len(sections) == 5


def test_renders_kinds_forms_meanings_and_provenance(plan):
    _, root = parsed(plan)
    text = [
        " ".join("".join(x.itertext()).split())
        for x in root.findall(f".//{XHTML}section")
    ]
    assert "Expression" in text[0] and "Normalized form: 良い天気" in text[0]
    assert "Vocabulary" in text[1] and "言葉【ことば】" in text[1]
    assert "public stage" in text[2] and "Occurrences 2" in text[2]
    assert "Proper name" in text[3] and "Yukino (person; female given name)" in text[3]
    assert "Translation jmnedict-2001-translation-0001" in text[3]
    assert "Lemma: 振り返る" in text[4] and "to turn around" in text[4]
    assert "furiganalyse-synthetic-jmdict-expressions 2026-08-16" in text[0]
    assert "furiganalyse-synthetic-jmnedict 2026-08-16" in text[3]


def test_publisher_readings_are_plain_text_without_ruby_or_links(plan):
    _, root = parsed(plan)
    text = "".join(root.itertext())
    assert "表舞台【おもてぶたい】" in text and "雪乃【ゆきの】" in text
    assert root.findall(f".//{XHTML}ruby") == [] and root.findall(f".//{XHTML}a") == []


def test_serialization_is_deterministic_and_escapes_text(plan):
    changed = copy.deepcopy(plan)
    changed["items"][0]["surface"] = "良い<&天気"
    changed["items"][0]["display_meaning"] = "fine & <clear>"
    first = render_study_notes(changed, "Notes & <Review>")
    assert first == render_study_notes(changed, "Notes & <Review>")
    assert (
        b"Notes &amp; &lt;Review&gt;" in first and "良い&lt;&amp;天気".encode() in first
    )
    ET.fromstring(first)


def test_styles_are_scoped_to_study_note_classes(plan):
    _, root = parsed(plan)
    lines = root.find(f"{XHTML}head/{XHTML}style").text.strip().splitlines()
    assert all(line.startswith((".study-notes", ".study-note")) for line in lines)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda p: p.update(schema_version=2), "schema v1"),
        (lambda p: p["items"][0].update(kind="grammar"), "Unsupported item kind"),
        (lambda p: p["items"][0].update(display_meaning=""), "Missing display_meaning"),
        (
            lambda p: p["items"][1].update(
                note_anchor_id=p["items"][0]["note_anchor_id"]
            ),
            "Duplicate or invalid note anchor",
        ),
        (
            lambda p: p["items"][0].update(selected_entry_id="missing"),
            "Invalid selected entry",
        ),
        (
            lambda p: p["items"][0].update(selected_sense_id="missing"),
            "Invalid dictionary references",
        ),
        (
            lambda p: p["items"][3].update(selected_translation_id="missing"),
            "Invalid name references",
        ),
        (
            lambda p: p["items"][2].update(reading_source="JMdict"),
            "Publisher-ruby violation",
        ),
        (
            lambda p: p["items"][0].update(surface="unsafe\x00text"),
            "Unsafe XML character",
        ),
        (lambda p: p["items"].reverse(), "Duplicate or unstable item ID"),
    ],
)
def test_validation_rejects_invalid_plans(plan, mutate, message):
    mutate(plan)
    with pytest.raises(StudyNoteError, match=message):
        validate_annotation_plan_for_notes(plan)
