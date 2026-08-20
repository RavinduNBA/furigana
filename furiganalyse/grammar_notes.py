"""Deterministic standalone XHTML rendering for curated grammar notes."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from furiganalyse.grammar_analysis import stable_hash, validate_dataset
from furiganalyse.grammar_plan import SYNTHETIC_MECHANICS_RULE_ID

XHTML_NS = "http://www.w3.org/1999/xhtml"
XML_NS = "http://www.w3.org/XML/1998/namespace"
ANCHOR = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]*$")
INVALID_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")
UNSAFE = re.compile(r"(?i)<[^>]*>|https?://|javascript:|data:text|on[a-z]+\s*=")
STYLE = """.grammar-notes { font-family: sans-serif; line-height: 1.5; }
.grammar-notes__list { margin: 0; padding: 0; }
.grammar-study-note { border-top: 1px solid #bbb; margin: 1.25em 0; padding: 1em 0; }
.grammar-study-note__heading { font-size: 1.25em; margin: 0 0 .4em; }
.grammar-study-note__label { font-weight: bold; }
.grammar-study-note__explanation { margin: .5em 0; }
.grammar-study-note__formation, .grammar-study-note__usage, .grammar-study-note__occurrences { margin: .5em 0; }
.grammar-study-note__details { font-size: .85em; margin: .5em 0; }
"""

ET.register_namespace("", XHTML_NS)


class GrammarNoteError(ValueError):
    """Raised when a grammar plan cannot produce safe deterministic notes."""


def _plain(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GrammarNoteError(f"Missing {field}")
    if INVALID_XML.search(value) or UNSAFE.search(value):
        raise GrammarNoteError(f"Unsafe {field}")
    return value


def _plain_list(value: Any, field: str, *, empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not empty):
        raise GrammarNoteError(f"Missing {field}")
    result = [_plain(item, field) for item in value]
    if len(result) != len(set(result)):
        raise GrammarNoteError(f"Duplicate {field}")
    return result


def validate_grammar_plan_for_notes(
    plan: dict[str, Any], dataset: dict[str, Any], *, allow_synthetic_mechanics: bool = False
) -> None:
    try:
        validate_dataset(dataset)
    except (KeyError, TypeError, ValueError) as error:
        raise GrammarNoteError("Invalid grammar dataset") from error
    required = {
        "schema_version", "book_id", "source_book_schema_version",
        "source_vocabulary_schema_version", "source_annotation_plan_schema_version",
        "source_grammar_report_schema_version", "source_hashes", "dataset", "config",
        "items", "occurrences", "overlaps", "diagnostics",
    }
    if not isinstance(plan, dict) or set(plan) != required or plan.get("schema_version") != 1:
        raise GrammarNoteError("Unsupported grammar-plan schema")
    if plan.get("config", {}).get("enabled") is not True:
        raise GrammarNoteError("Grammar planning is disabled")
    if plan.get("dataset") != {
        "id": dataset["dataset_id"], "version": dataset["dataset_version"],
        "source_provenance": dataset["source_provenance"],
    }:
        raise GrammarNoteError("Grammar dataset mismatch")
    rules = {rule["id"]: rule for rule in dataset["rules"]}
    items, occurrences = plan.get("items"), plan.get("occurrences")
    if not isinstance(items, list) or not isinstance(occurrences, list):
        raise GrammarNoteError("Missing grammar records")
    occurrence_map: dict[str, dict[str, Any]] = {}
    anchors: set[str] = set()
    previous_source = None
    for number, occurrence in enumerate(occurrences, 1):
        if set(occurrence) != {
            "id", "source_grammar_occurrence_id", "chapter_id", "block_id",
            "sentence_id", "sentence_record_id", "surface", "sentence_start",
            "sentence_end", "block_start", "block_end", "component_token_ids",
            "overlapping_candidate_ids", "publisher_ruby_interaction",
            "source_anchor_id", "link_disposition", "overlap_disposition", "hash",
        }:
            raise GrammarNoteError("Unsupported grammar occurrence fields")
        occurrence_id = occurrence.get("id")
        if occurrence_id != f"grammar-plan-occurrence-{number:04d}":
            raise GrammarNoteError("Duplicate or unstable grammar occurrence")
        if occurrence.get("hash") != stable_hash({k: v for k, v in occurrence.items() if k != "hash"}):
            raise GrammarNoteError("Invalid grammar occurrence hash")
        for field in ("surface", "chapter_id", "sentence_record_id", "source_anchor_id"):
            _plain(occurrence.get(field), field)
        anchor = occurrence["source_anchor_id"]
        if anchor in anchors or not ANCHOR.fullmatch(anchor):
            raise GrammarNoteError("Duplicate or invalid grammar source anchor")
        anchors.add(anchor)
        source = (
            occurrence.get("chapter_id"), occurrence.get("block_id"),
            occurrence.get("sentence_id"), occurrence.get("sentence_start"),
        )
        if not all(isinstance(value, str) for value in source[:3]) or not isinstance(source[3], int):
            raise GrammarNoteError("Invalid grammar occurrence source")
        if previous_source is not None and source < previous_source:
            raise GrammarNoteError("Unordered grammar occurrences")
        previous_source = source
        if occurrence.get("publisher_ruby_interaction") not in {"none", "adjacent-preserved-publisher-ruby"}:
            raise GrammarNoteError("Unsupported publisher-ruby interaction")
        occurrence_map[occurrence_id] = occurrence

    used: set[str] = set()
    previous_first = -1
    for number, item in enumerate(items, 1):
        if set(item) != {
            "id", "grammar_candidate_id", "rule_id", "dataset_id", "dataset_version",
            "dataset_source_provenance", "rule_hash", "canonical_key", "label",
            "explanation", "formation_patterns", "usage_labels", "source_provenance",
            "occurrence_ids", "chapter_counts", "book_count", "selection_status",
            "selection_reason", "note_anchor_id", "hash",
        }:
            raise GrammarNoteError("Unsupported grammar item fields")
        if item.get("id") != f"grammar-item-{number:04d}":
            raise GrammarNoteError("Duplicate or unstable grammar item")
        rule = rules.get(item.get("rule_id"))
        if rule is None:
            raise GrammarNoteError("Unknown grammar rule")
        if rule["id"] == SYNTHETIC_MECHANICS_RULE_ID and not allow_synthetic_mechanics:
            raise GrammarNoteError("Synthetic mechanics rule requires test-only permission")
        for field in ("canonical_key", "label", "explanation", "formation_patterns", "usage_labels", "source_provenance"):
            if item.get(field) != rule.get(field):
                raise GrammarNoteError("Curated grammar rule content changed")
        if item.get("rule_hash") != rule.get("hash"):
            raise GrammarNoteError("Stale grammar rule hash")
        if (item.get("dataset_id"), item.get("dataset_version"), item.get("dataset_source_provenance")) != (
            dataset["dataset_id"], dataset["dataset_version"], dataset["source_provenance"]
        ):
            raise GrammarNoteError("Grammar item dataset mismatch")
        if (item.get("selection_status"), item.get("selection_reason")) != (
            "selected", "exact-curated-rule-within-chapter-limit"
        ):
            raise GrammarNoteError("Unsupported grammar selection")
        for field in ("canonical_key", "label", "explanation", "source_provenance"):
            _plain(item.get(field), field)
        _plain_list(item.get("formation_patterns"), "formation pattern")
        _plain_list(item.get("usage_labels"), "usage label", empty=True)
        if item.get("hash") != stable_hash({k: v for k, v in item.items() if k != "hash"}):
            raise GrammarNoteError("Invalid grammar item hash")
        anchor = _plain(item.get("note_anchor_id"), "grammar note anchor")
        if anchor in anchors or not ANCHOR.fullmatch(anchor):
            raise GrammarNoteError("Duplicate or invalid grammar note anchor")
        anchors.add(anchor)
        refs = item.get("occurrence_ids")
        if not isinstance(refs, list) or not refs or any(ref not in occurrence_map for ref in refs):
            raise GrammarNoteError("Unknown grammar occurrence reference")
        indexes = [occurrences.index(occurrence_map[ref]) for ref in refs]
        if indexes != sorted(indexes) or indexes[0] <= previous_first or used.intersection(refs):
            raise GrammarNoteError("Unordered grammar item occurrences")
        previous_first = indexes[0]
        used.update(refs)
        counts = item.get("chapter_counts")
        if item.get("book_count") != len(refs) or not isinstance(counts, list) or sum(x.get("count", 0) for x in counts) != len(refs):
            raise GrammarNoteError("Invalid grammar occurrence counts")
        chapter_ids = [value.get("chapter_id") for value in counts]
        if chapter_ids != sorted(chapter_ids) or len(chapter_ids) != len(set(chapter_ids)) or any(
            not isinstance(value.get("count"), int) or value["count"] < 1 for value in counts
        ):
            raise GrammarNoteError("Unordered grammar chapter counts")
    if used != set(occurrence_map):
        raise GrammarNoteError("Unreferenced grammar occurrence")


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    node = ET.SubElement(parent, f"{{{XHTML_NS}}}{tag}", attrs)
    if text is not None:
        node.text = text
    return node


def render_grammar_notes(
    plan: dict[str, Any], dataset: dict[str, Any], *,
    title: str = "Grammar Study Notes", allow_synthetic_mechanics: bool = False,
) -> bytes:
    validate_grammar_plan_for_notes(plan, dataset, allow_synthetic_mechanics=allow_synthetic_mechanics)
    title = _plain(title, "document title")
    root = ET.Element(f"{{{XHTML_NS}}}html", {"lang": "ja", f"{{{XML_NS}}}lang": "ja"})
    head = _sub(root, "head")
    _sub(head, "meta", charset="utf-8")
    _sub(head, "title", title)
    _sub(head, "style", STYLE, type="text/css")
    main = _sub(_sub(root, "body"), "main", id="grammar-notes", **{"class": "grammar-notes"})
    _sub(main, "h1", title, **{"class": "grammar-notes__title"})
    notes = _sub(main, "div", **{"class": "grammar-notes__list"})
    occurrences = {value["id"]: value for value in plan["occurrences"]}
    for item in plan["items"]:
        section = _sub(notes, "section", id=item["note_anchor_id"], **{
            "class": "grammar-study-note", "data-grammar-item-id": item["id"],
        })
        _sub(section, "p", "Grammar study note", **{"class": "grammar-study-note__kind"})
        _sub(section, "h2", item["canonical_key"], **{"class": "grammar-study-note__heading"})
        _sub(section, "p", item["label"], **{"class": "grammar-study-note__label"})
        _sub(section, "p", item["explanation"], **{"class": "grammar-study-note__explanation"})
        formation = _sub(section, "div", **{"class": "grammar-study-note__formation"})
        _sub(formation, "h3", "Formation")
        listing = _sub(formation, "ul")
        for value in item["formation_patterns"]:
            _sub(listing, "li", value)
        if item["usage_labels"]:
            usage = _sub(section, "div", **{"class": "grammar-study-note__usage"})
            _sub(usage, "h3", "Usage")
            listing = _sub(usage, "ul")
            for value in item["usage_labels"]:
                _sub(listing, "li", value)
        occurrence_section = _sub(section, "div", **{"class": "grammar-study-note__occurrences"})
        _sub(occurrence_section, "h3", f"Occurrences ({item['book_count']})")
        listing = _sub(occurrence_section, "ol")
        for ref in item["occurrence_ids"]:
            occurrence = occurrences[ref]
            protected = "; publisher ruby preserved" if occurrence["publisher_ruby_interaction"] != "none" else ""
            _sub(listing, "li", (
                f"{occurrence['surface']} — {occurrence['chapter_id']} — "
                f"{occurrence['source_grammar_occurrence_id']} — {occurrence['sentence_record_id']}{protected}"
            ), **{"data-occurrence-id": ref})
        details = _sub(section, "dl", **{"class": "grammar-study-note__details"})
        for label, value in (
            ("Dataset", f"{item['dataset_id']} {item['dataset_version']}"),
            ("Rule", item["rule_id"]), ("Rule hash", item["rule_hash"]),
            ("Selection", item["selection_reason"]),
        ):
            _sub(details, "dt", label)
            _sub(details, "dd", value)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True, short_empty_elements=True) + b"\n"


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GrammarNoteError("Expected a JSON object")
    return value


def write_grammar_notes(plan: dict[str, Any], dataset: dict[str, Any], output: str | Path, **options: Any) -> None:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(render_grammar_notes(plan, dataset, **options))
