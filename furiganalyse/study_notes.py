"""Deterministic standalone XHTML rendering for Phase 4 study notes."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

XHTML_NS = "http://www.w3.org/1999/xhtml"
XML_NS = "http://www.w3.org/XML/1998/namespace"
DOCUMENT_VERSION = 1
SUPPORTED_KINDS = {"vocabulary", "expression", "name"}
ANCHOR_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]*$")
INVALID_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")
KIND_LABELS = {
    "vocabulary": "Vocabulary",
    "expression": "Expression",
    "name": "Proper name",
}
STYLE = """.study-notes { font-family: sans-serif; line-height: 1.5; }
.study-notes__list { margin: 0; padding: 0; }
.study-note { border-top: 1px solid #bbb; margin: 1.25em 0; padding: 1em 0; }
.study-note__heading { font-size: 1.25em; margin: 0 0 .4em; }
.study-note__reading { font-size: .85em; font-weight: normal; margin-left: .35em; }
.study-note__kind { font-size: .8em; font-weight: bold; text-transform: uppercase; }
.study-note__meaning { margin: .5em 0; }
.study-note__details { font-size: .85em; margin: .5em 0; }
.study-note__details dt { font-weight: bold; }
.study-note__details dd { margin-left: 1.5em; }
"""

ET.register_namespace("", XHTML_NS)


class StudyNoteError(ValueError):
    """Raised when an annotation plan cannot produce safe deterministic notes."""


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StudyNoteError(f"Missing {field}")
    if INVALID_XML.search(value):
        raise StudyNoteError(f"Unsafe XML character in {field}")
    return value


def _strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise StudyNoteError(f"Missing {field}")
    result = [_text(item, field) for item in value]
    if len(result) != len(set(result)):
        raise StudyNoteError(f"Duplicate {field}")
    return result


def validate_annotation_plan_for_notes(plan: dict[str, Any]) -> None:
    if not isinstance(plan, dict) or plan.get("schema_version") != 1:
        raise StudyNoteError("Study notes require annotation-plan schema v1")
    _text(plan.get("book_id"), "book ID")
    items = plan.get("items")
    if not isinstance(items, list):
        raise StudyNoteError("Missing study items")
    item_ids: set[str] = set()
    anchors: set[str] = set()
    previous_source = None
    for number, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise StudyNoteError("Invalid study item")
        item_id = _text(item.get("id"), "item ID")
        if item_id != f"study-item-{number:04d}" or item_id in item_ids:
            raise StudyNoteError(f"Duplicate or unstable item ID: {item_id}")
        item_ids.add(item_id)
        kind = item.get("kind")
        if kind not in SUPPORTED_KINDS:
            raise StudyNoteError(f"Unsupported item kind: {kind}")
        for field in ("surface", "reading", "display_meaning"):
            _text(item.get(field), field)
        anchor = _text(item.get("note_anchor_id"), "note anchor")
        if not ANCHOR_PATTERN.fullmatch(anchor) or anchor in anchors:
            raise StudyNoteError(f"Duplicate or invalid note anchor: {anchor}")
        if anchor != f"note-{item_id}":
            raise StudyNoteError(f"Unstable note anchor: {anchor}")
        anchors.add(anchor)
        entries = _strings(item.get("source_entry_ids"), "entry references")
        if item.get("selected_entry_id") not in entries:
            raise StudyNoteError(f"Invalid selected entry: {item_id}")
        senses = item.get("source_sense_ids")
        translations = item.get("source_translation_ids")
        if kind == "name":
            translations = _strings(translations, "translation references")
            if senses or item.get("selected_translation_id") not in translations:
                raise StudyNoteError(f"Invalid name references: {item_id}")
            if item.get("selected_sense_id") is not None:
                raise StudyNoteError(f"Name has JMdict sense: {item_id}")
        else:
            senses = _strings(senses, "sense references")
            if translations or item.get("selected_sense_id") not in senses:
                raise StudyNoteError(f"Invalid dictionary references: {item_id}")
            if item.get("selected_translation_id") is not None:
                raise StudyNoteError(f"Dictionary item has name translation: {item_id}")
        _text(item.get("dictionary_dataset_id"), "dictionary dataset ID")
        _text(item.get("dictionary_dataset_version"), "dictionary dataset version")
        occurrences = item.get("occurrences")
        if not isinstance(occurrences, list) or not occurrences:
            raise StudyNoteError(f"Missing occurrences: {item_id}")
        previous_occurrence = None
        for occurrence_number, occurrence in enumerate(occurrences, 1):
            occurrence_id = _text(occurrence.get("id"), "occurrence ID")
            if (
                occurrence_id != f"{item_id}-occ-{occurrence_number:04d}"
                or occurrence.get("occurrence_number") != occurrence_number
            ):
                raise StudyNoteError(f"Unordered occurrence: {occurrence_id}")
            source_key = (
                _text(occurrence.get("chapter_id"), "chapter ID"),
                _text(occurrence.get("block_id"), "block ID"),
                _text(occurrence.get("sentence_id"), "sentence ID"),
                occurrence.get("sentence_start"),
                occurrence.get("sentence_end"),
            )
            if not all(isinstance(offset, int) for offset in source_key[-2:]):
                raise StudyNoteError(f"Invalid occurrence offsets: {occurrence_id}")
            if source_key[-2] < 0 or source_key[-2] >= source_key[-1]:
                raise StudyNoteError(f"Invalid occurrence offsets: {occurrence_id}")
            if previous_occurrence is not None and source_key <= previous_occurrence:
                raise StudyNoteError(f"Unordered occurrences: {item_id}")
            previous_occurrence = source_key
            for field in ("token_ids", "candidate_ids"):
                _strings(occurrence.get(field), field)
            if occurrence.get("publisher_ruby_id"):
                _text(occurrence["publisher_ruby_id"], "publisher ruby ID")
                if (
                    occurrence.get("annotation_target") != "preserved_publisher_ruby"
                    or item.get("reading_source") != "publisher"
                ):
                    raise StudyNoteError(f"Publisher-ruby violation: {occurrence_id}")
        primary = occurrences[0]
        item_source = (
            item.get("chapter_id"),
            item.get("block_id"),
            item.get("sentence_id"),
            primary.get("sentence_start"),
        )
        if previous_source is not None and item_source <= previous_source:
            raise StudyNoteError("Study items are not in source order")
        previous_source = item_source


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs) -> ET.Element:
    node = ET.SubElement(parent, f"{{{XHTML_NS}}}{tag}", attrs)
    if text is not None:
        node.text = text
    return node


def render_study_notes(plan: dict[str, Any], title: str = "Study Notes") -> bytes:
    """Validate an annotation plan and serialize one deterministic XHTML document."""
    validate_annotation_plan_for_notes(plan)
    title = _text(title, "document title")
    root = ET.Element(
        f"{{{XHTML_NS}}}html",
        {"lang": "en", f"{{{XML_NS}}}lang": "en"},
    )
    head = _sub(root, "head")
    _sub(head, "meta", charset="utf-8")
    _sub(head, "title", title)
    _sub(head, "style", STYLE, type="text/css")
    body = _sub(root, "body")
    main = _sub(body, "main", **{"class": "study-notes", "id": "study-notes"})
    _sub(main, "h1", title, **{"class": "study-notes__title"})
    notes = _sub(main, "div", **{"class": "study-notes__list"})
    for item in plan["items"]:
        section = _sub(
            notes,
            "section",
            id=item["note_anchor_id"],
            **{
                "class": f"study-note study-note--{item['kind']}",
                "data-item-id": item["id"],
            },
        )
        _sub(section, "p", KIND_LABELS[item["kind"]], **{"class": "study-note__kind"})
        heading = _sub(
            section, "h2", item["surface"], **{"class": "study-note__heading"}
        )
        reading = _sub(heading, "span", **{"class": "study-note__reading"})
        reading.text = f"【{item['reading']}】"
        if item.get("lemma"):
            _sub(
                section, "p", f"Lemma: {item['lemma']}", **{"class": "study-note__form"}
            )
        if item.get("normalized_form"):
            _sub(
                section,
                "p",
                f"Normalized form: {item['normalized_form']}",
                **{"class": "study-note__form"},
            )
        _sub(section, "p", item["display_meaning"], **{"class": "study-note__meaning"})
        details = _sub(section, "dl", **{"class": "study-note__details"})
        rows = [
            ("Occurrences", str(len(item["occurrences"]))),
            (
                "Dictionary",
                f"{item['dictionary_dataset_id']} {item['dictionary_dataset_version']}",
            ),
            ("Entry", item["selected_entry_id"]),
        ]
        if item["kind"] == "name":
            rows.append(("Translation", item["selected_translation_id"]))
        else:
            rows.append(("Sense", item["selected_sense_id"]))
        for label, value in rows:
            _sub(details, "dt", label)
            _sub(details, "dd", value)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    return (
        ET.tostring(
            root,
            encoding="utf-8",
            xml_declaration=True,
            short_empty_elements=True,
        )
        + b"\n"
    )


def load_annotation_plan(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StudyNoteError("Annotation plan must be a JSON object")
    return value


def write_study_notes(
    plan: dict[str, Any], output_path: str | Path, title: str = "Study Notes"
) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(render_study_notes(plan, title))
