"""Deterministic adaptive assistance rendering over copied linked XHTML."""

from __future__ import annotations

import copy
import hashlib
import json
import posixpath
import re
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from furiganalyse.assistance_density import stable_hash

XHTML_NS = "http://www.w3.org/1999/xhtml"
XML_NS = "http://www.w3.org/XML/1998/namespace"
X = f"{{{XHTML_NS}}}"
ET.register_namespace("", XHTML_NS)
SCHEMA_VERSION = 1
PRECEDENCE = [
    "publisher",
    "explicit_user_override",
    "input_assistance_state",
    "chapter_density_policy",
    "exposure_evidence",
    "canonical_source_order",
]
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


class AdaptiveRenderingError(ValueError):
    """Raised when adaptive rendering cannot be applied safely."""


def _without_hash(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "hash"}


def _check_hash(value: dict[str, Any], label: str) -> None:
    if value.get("hash") != stable_hash(_without_hash(value)):
        raise AdaptiveRenderingError(f"Invalid {label} hash")


def _add_hash(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result["hash"] = stable_hash(result)
    return result


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdaptiveRenderingError("Expected JSON object")
    return value


def serialize_report(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def read_xhtml_directory(root: str | Path) -> dict[str, bytes]:
    root = Path(root)
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*.xhtml"))
    }


def directory_hash(files: dict[str, bytes]) -> str:
    return stable_hash([
        {"path": path, "sha256": hashlib.sha256(data).hexdigest()}
        for path, data in sorted(files.items())
    ])


def _parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def _replace_link_with_span(root: ET.Element, link: ET.Element) -> None:
    parent = _parent_map(root).get(link)
    if parent is None:
        raise AdaptiveRenderingError("Ambiguous DOM mapping")
    replacement = ET.Element(X + "span", {
        "id": link.get("id", ""),
        "class": "adaptive-grammar-suppressed",
    })
    replacement.text = link.text
    replacement.tail = link.tail
    for child in list(link):
        link.remove(child)
        replacement.append(child)
    index = list(parent).index(link)
    parent.remove(link)
    parent.insert(index, replacement)


def _add_reading(anchor: ET.Element, reading: str, occurrence_id: str) -> str:
    if list(anchor) or not anchor.text:
        raise AdaptiveRenderingError("Nested-anchor risk")
    surface = anchor.text
    anchor.text = None
    ruby_id = f"adaptive-reading-{occurrence_id}"
    ruby = ET.SubElement(anchor, X + "ruby", {
        "id": ruby_id,
        "class": "adaptive-reading-assistance",
    })
    ruby.text = surface
    ET.SubElement(ruby, X + "rt").text = reading
    return ruby_id


def _visible_text(root: ET.Element) -> str:
    parts: list[str] = []

    def walk(node: ET.Element) -> None:
        if node.tag.rsplit("}", 1)[-1] in {"head", "rt", "rp", "script", "style"}:
            return
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(root)
    return "".join(parts)


def _publisher_ruby(root: ET.Element) -> list[bytes]:
    return [
        ET.tostring(node, encoding="utf-8")
        for node in root.findall(f".//{X}ruby")
        if "adaptive-reading-assistance" not in node.get("class", "").split()
    ]


def _validate_links(files: dict[str, bytes], *, strict_source_markup: bool = True) -> None:
    roots = {path: ET.fromstring(data) for path, data in files.items()}
    ids: dict[str, set[str]] = {}
    for path, root in roots.items():
        values = [node.get("id") for node in root.iter() if node.get("id")]
        if len(values) != len(set(values)):
            raise AdaptiveRenderingError("Duplicate XHTML ID")
        ids[path] = set(values)
        if strict_source_markup and root.findall(f".//{X}script"):
            raise AdaptiveRenderingError("Unsafe hidden content")
        for node in root.iter():
            if any(name.lower().startswith("on") for name in node.attrib):
                raise AdaptiveRenderingError("Unsafe hidden content")
            if strict_source_markup and node.get("src"):
                raise AdaptiveRenderingError("Unsafe XHTML link")
        for link in root.findall(f".//{X}a"):
            if link.findall(f".//{X}a"):
                raise AdaptiveRenderingError("Nested-anchor risk")
    for source, root in roots.items():
        for link in root.findall(f".//{X}a"):
            href = link.get("href")
            if not href:
                continue
            generated = bool(
                {
                    "study-link", "study-note__backlink", "grammar-link",
                    "grammar-study-note__backlink",
                }
                & set(link.get("class", "").split())
            )
            if not strict_source_markup and not generated:
                continue
            split = urlsplit(href)
            if split.scheme or split.netloc or ".." in PurePosixPath(split.path).parts:
                raise AdaptiveRenderingError("Unsafe XHTML link")
            target = source if not split.path else posixpath.normpath(
                posixpath.join(posixpath.dirname(source), split.path)
            )
            if target not in roots or not split.fragment or split.fragment not in ids[target]:
                raise AdaptiveRenderingError("Broken fragment")
    if strict_source_markup:
        combined = b"".join(files.values()).lower().replace(b" ", b"")
        if any(value in combined for value in (
            b"display:none", b"visibility:hidden", b"data-meaning", b"<!--", b"url("
        )):
            raise AdaptiveRenderingError("Unsafe hidden content")


def _diagnostic(reason: str, number: int = 1, source_id: str = "adaptive-rendering") -> dict[str, Any]:
    return _add_hash({
        "id": f"adaptive-rendering-diagnostic-{number:04d}",
        "reason": reason,
        "source_id": source_id,
    })


def empty_report(book_id: str | None, reason: str) -> dict[str, Any]:
    configuration = _add_hash({"enabled": False})
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_id": "adaptive-rendering-report-v1",
        "book_id": book_id,
        "source_schema_versions": {
            "canonical_book": 2,
            "annotation_plan": 2,
            "grammar_plan": 1,
            "assistance_report": 1,
            "density_report": 1,
        },
        "source_hashes": {},
        "precedence": PRECEDENCE,
        "configuration": configuration,
        "document_results": [],
        "occurrence_results": [],
        "diagnostics": [_diagnostic(reason)],
    }
    report["hash"] = stable_hash(report)
    return report


def _validate_inputs(
    book: dict[str, Any],
    annotation_plan: dict[str, Any],
    grammar_plan: dict[str, Any] | None,
    assistance: dict[str, Any],
    density: dict[str, Any],
) -> None:
    expected_fields = (
        {"book_id", "chapters", "package_path", "schema_version"},
        {
            "book_id", "config", "diagnostics", "enrichment_diagnostics",
            "enrichments", "items", "schema_version",
            "source_annotation_plan_schema_version", "source_report_schema_version",
        },
        {
            "book_id", "config", "dataset", "diagnostics", "items", "occurrences",
            "overlaps", "schema_version", "source_annotation_plan_schema_version",
            "source_book_schema_version", "source_grammar_report_schema_version",
            "source_hashes", "source_vocabulary_schema_version",
        },
        {
            "book_id", "configuration", "diagnostics", "hash", "precedence",
            "preset_dataset", "profile", "report_id", "results", "schema_version",
            "source_hashes", "source_schema_versions",
        },
        {
            "book_id", "chapter_summaries", "configuration", "diagnostics", "hash",
            "occurrence_plans", "policy", "precedence", "report_id", "schema_version",
            "source_hashes", "source_schema_versions",
        },
    )
    annotation_fields = expected_fields[1]
    production_annotation_fields = annotation_fields | {
        "tokenizer", "dictionary", "name_dictionary",
    }
    invalid_fields = (
        set(book) != expected_fields[0]
        or frozenset(annotation_plan) not in {
            frozenset(annotation_fields), frozenset(production_annotation_fields)
        }
        or (grammar_plan is not None and set(grammar_plan) != expected_fields[2])
        or set(assistance) != expected_fields[3]
        or set(density) != expected_fields[4]
    )
    if invalid_fields:
        raise AdaptiveRenderingError("Unsupported schema or field")
    actual = (
        book.get("schema_version"), annotation_plan.get("schema_version"),
        grammar_plan.get("schema_version") if grammar_plan is not None else None,
        assistance.get("schema_version"), density.get("schema_version"),
    )
    if actual != (2, 2, 1 if grammar_plan is not None else None, 1, 1):
        raise AdaptiveRenderingError("Unsupported schema or field")
    book_id = book.get("book_id")
    sources = [annotation_plan, assistance, density]
    if grammar_plan is not None:
        sources.append(grammar_plan)
    if not book_id or any(value.get("book_id") != book_id for value in sources):
        raise AdaptiveRenderingError("Source identity mismatch")
    _check_hash(assistance, "assistance report")
    _check_hash(density, "density report")
    for result in assistance.get("results", []):
        _check_hash(result, "assistance result")
    for plan in density.get("occurrence_plans", []):
        _check_hash(plan, "occurrence plan")
    expected_hashes = {
        "canonical_book": stable_hash(book),
        "annotation_plan": stable_hash(annotation_plan),
        "grammar_plan": stable_hash(grammar_plan) if grammar_plan is not None else "none",
        "assistance_report": assistance["hash"],
    }
    if any(density.get("source_hashes", {}).get(key) != value for key, value in expected_hashes.items()):
        raise AdaptiveRenderingError("Source-hash mismatch")


def _validate_occurrence_plans(
    book: dict[str, Any],
    annotation_plan: dict[str, Any],
    grammar_plan: dict[str, Any] | None,
    assistance: dict[str, Any],
    density: dict[str, Any],
) -> None:
    sentences = {
        sentence["id"]: sentence["text"]
        for chapter in book["chapters"]
        for block in chapter["blocks"]
        for sentence in block["sentences"]
    }
    source: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for item in annotation_plan["items"]:
        for occurrence in item["occurrences"]:
            source[occurrence["id"]] = (item["id"], item["surface"], occurrence)
    grammar_items = {
        occurrence_id: item["id"]
        for item in (grammar_plan or {"items": []})["items"]
        for occurrence_id in item["occurrence_ids"]
    }
    for occurrence in (grammar_plan or {"occurrences": []})["occurrences"]:
        source[occurrence["id"]] = (
            grammar_items[occurrence["id"]], occurrence["surface"], occurrence
        )
    results = {result["id"]: result for result in assistance["results"]}
    seen: set[str] = set()
    plans = density["occurrence_plans"]
    if len(plans) != len(source):
        raise AdaptiveRenderingError("Unknown occurrence")
    for number, plan in enumerate(plans, 1):
        occurrence_id = plan["source_occurrence_id"]
        if occurrence_id in seen or plan["canonical_source_order"] != number:
            raise AdaptiveRenderingError("Duplicate or unordered occurrence")
        seen.add(occurrence_id)
        expected = source.get(occurrence_id)
        result = results.get(plan["source_result_id"])
        if expected is None or result is None:
            raise AdaptiveRenderingError("Unknown occurrence")
        item_id, surface, occurrence = expected
        if item_id != plan["source_item_id"] or result["source_item_id"] != item_id:
            raise AdaptiveRenderingError("Unknown occurrence")
        keys = ("chapter_id", "block_id", "sentence_id", "sentence_start", "sentence_end")
        if any(plan.get(key) != occurrence.get(key) for key in keys):
            raise AdaptiveRenderingError("Invalid source offset")
        text = sentences.get(plan["sentence_id"])
        start, end = plan["sentence_start"], plan["sentence_end"]
        if not isinstance(text, str) or text[start:end] != surface:
            raise AdaptiveRenderingError("Invalid source offset")
        if plan.get("publisher_ruby_id") and (
            plan["planned_assistance"]["reading"] != "publisher-ruby-preserved"
            or plan["density_decisions"]["reading"] != "publisher-ruby-preserved"
        ):
            raise AdaptiveRenderingError("Publisher-ruby suppression attempt")
        disposition = plan.get("grammar_link_disposition")
        if disposition == "rejected-ambiguous-overlap" and plan["planned_assistance"]["grammar"] != "suppress-grammar":
            raise AdaptiveRenderingError("Grammar-disposition conflict")
        if disposition == "publisher-ruby-preserved" and plan["density_decisions"]["grammar"] != "publisher-adjacent-protected":
            raise AdaptiveRenderingError("Grammar-disposition conflict")


def render_adaptive_output(
    source_dir: str | Path,
    book: dict[str, Any],
    annotation_plan: dict[str, Any],
    grammar_plan: dict[str, Any] | None,
    assistance: dict[str, Any],
    density: dict[str, Any],
    *,
    enabled: bool = False,
    strict_source_markup: bool = True,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    source_files = read_xhtml_directory(source_dir)
    if not enabled:
        return empty_report(book.get("book_id"), "disabled"), source_files
    _validate_inputs(book, annotation_plan, grammar_plan, assistance, density)
    _validate_occurrence_plans(book, annotation_plan, grammar_plan, assistance, density)
    chapter_paths = {chapter["id"]: chapter["source_path"] for chapter in book["chapters"]}
    notes_directory = posixpath.dirname(next(iter(chapter_paths.values())))
    study_notes_path = posixpath.join(notes_directory, "study-notes.xhtml")
    grammar_notes_path = posixpath.join(notes_directory, "grammar-notes.xhtml")
    required = set(chapter_paths.values()) | {study_notes_path}
    if grammar_plan is not None:
        required.add(grammar_notes_path)
    if set(source_files) != required:
        raise AdaptiveRenderingError("Ambiguous DOM mapping")
    roots = {path: ET.fromstring(data) for path, data in source_files.items()}
    chapter_set = set(chapter_paths.values())
    before_visible = {path: _visible_text(roots[path]) for path in chapter_set}
    before_publisher = {path: _publisher_ruby(roots[path]) for path in chapter_set}
    items = {item["id"]: item for item in annotation_plan["items"]}
    assistance_results = {result["source_item_id"]: result for result in assistance["results"]}
    study_notes = roots[study_notes_path]
    grammar_notes = roots.get(grammar_notes_path)
    occurrence_results: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    grammar_keep: dict[str, bool] = {}

    for number, plan in enumerate(density["occurrence_plans"], 1):
        item_id = plan["source_item_id"]
        occurrence_id = plan["source_occurrence_id"]
        path = chapter_paths.get(plan["chapter_id"])
        if path is None:
            raise AdaptiveRenderingError("Unknown occurrence")
        root = roots[path]
        actions = {"reading": "not-applicable", "meaning": "not-applicable", "grammar": "not-applicable"}
        generated_anchor_ids: list[str] = []
        reasons: list[str] = []

        if plan["item_kind"] != "grammar":
            item = items.get(item_id)
            result = assistance_results.get(item_id)
            anchor = root.find(f".//{X}a[@id='{plan['source_anchor_id']}']")
            section = study_notes.find(f".//{X}section[@data-item-id='{item_id}']")
            if item is None or result is None or anchor is None or section is None:
                raise AdaptiveRenderingError("Unknown occurrence")
            section.set("class", f"adaptive-study-note adaptive-{plan['item_kind']}-note")
            # Phase 4 notes show dictionary reading/meaning by default. Adaptive
            # rendering starts from those approved records but must genuinely omit
            # any assistance the occurrence plan suppresses.
            section_parents = _parent_map(section)
            for node in list(section.iter()):
                classes = node.get("class", "").split()
                if "study-note__reading" in classes or "study-note__meaning" in classes:
                    parent = section_parents.get(node)
                    if parent is not None:
                        parent.remove(node)
            reading_state = plan["planned_assistance"]["reading"]
            if reading_state == "publisher-ruby-preserved":
                actions["reading"] = "publisher-ruby-preserved"
                reasons.append("publisher-ruby-preserved")
            elif reading_state == "suppress-reading":
                actions["reading"] = "reading-suppressed"
                reasons.append("planned-reading-suppression")
            elif reading_state == "present-reading":
                approved = result.get("authoritative_reading")
                if not approved or result.get("reading_source") == "publisher":
                    actions["reading"] = "reading-unavailable"
                    reasons.append("missing-approved-reading")
                    diagnostics.append(_diagnostic(
                        "missing-approved-reading", len(diagnostics) + 1, occurrence_id
                    ))
                else:
                    generated_anchor_ids.append(_add_reading(anchor, approved, occurrence_id))
                    actions["reading"] = "reading-presented"
                    reasons.append("approved-reading-presented")
            meaning_state = plan["planned_assistance"]["meaning"]
            if meaning_state == "present-meaning":
                approved = item.get("display_meaning")
                reference = result.get("approved_meaning_reference") or {}
                if not approved or not any(reference.get(key) for key in (
                    "selected_entry_id", "selected_sense_id", "selected_translation_id"
                )):
                    raise AdaptiveRenderingError("Missing approved meaning")
                meaning = ET.Element(X + "p", {"class": "adaptive-meaning-assistance"})
                meaning.text = approved
                section.insert(1, meaning)
                actions["meaning"] = "meaning-presented"
                reasons.append("approved-meaning-presented")
            else:
                actions["meaning"] = "meaning-suppressed"
                reasons.append("planned-meaning-suppression")
        else:
            decision = plan["density_decisions"]["grammar"]
            actions["grammar"] = {
                "selected-within-budget": "grammar-presented",
                "selected-explicit-override": "grammar-presented",
                "selected-explicit-override-over-budget": "grammar-presented",
                "grammar-reference-only": "grammar-reference-only",
                "grammar-partial-overlap-rejected": "grammar-partial-overlap-rejected",
                "publisher-adjacent-protected": "publisher-adjacent-protected",
            }.get(decision, "grammar-suppressed")
            grammar_keep[occurrence_id] = actions["grammar"] in {
                "grammar-presented", "grammar-reference-only"
            }
            if actions["grammar"] == "grammar-suppressed":
                link = root.find(f".//{X}a[@id='{plan['source_anchor_id']}']")
                if link is not None:
                    _replace_link_with_span(root, link)
            reasons.append(actions["grammar"])

        occurrence_results.append(_add_hash({
            "id": f"adaptive-rendering-result-{number:04d}",
            "source_occurrence_plan_id": plan["id"],
            "source_assistance_result_id": plan["source_result_id"],
            "source_item_id": item_id,
            "source_occurrence_id": occurrence_id,
            "chapter_id": plan["chapter_id"],
            "document_path": path,
            "block_id": plan["block_id"],
            "sentence_id": plan["sentence_id"],
            "sentence_record_id": plan["sentence_record_id"],
            "input_assistance": plan["input_assistance"],
            "planned_assistance": plan["planned_assistance"],
            "density_decisions": plan["density_decisions"],
            "effective_sources": plan["effective_sources"],
            "reading_action": actions["reading"],
            "meaning_action": actions["meaning"],
            "grammar_action": actions["grammar"],
            "generated_anchor_ids": generated_anchor_ids,
            "preserved_source_anchor_id": plan["source_anchor_id"],
            "publisher_ruby_status": (
                "publisher-ruby-preserved" if plan.get("publisher_ruby_id")
                else plan["publisher_ruby_interaction"]
            ),
            "grammar_disposition": plan["grammar_link_disposition"],
            "reason_codes": reasons,
        }))

    if grammar_notes is not None:
        for context in list(grammar_notes.findall(f".//{X}div[@data-occurrence-id]")):
            if not grammar_keep.get(context.get("data-occurrence-id", ""), False):
                _parent_map(grammar_notes)[context].remove(context)
        for section in list(grammar_notes.findall(f".//{X}section[@data-grammar-item-id]")):
            if section.findall(f".//{X}div[@data-occurrence-id]"):
                section.set("class", "grammar-study-note adaptive-grammar-note")
            else:
                _parent_map(grammar_notes)[section].remove(section)

    for root in roots.values():
        root.set("lang", "ja")
        root.set(f"{{{XML_NS}}}lang", "ja")
    output_files = {
        path: ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"
        for path, root in sorted(roots.items())
    }
    for path in chapter_set:
        if _visible_text(roots[path]) != before_visible[path]:
            raise AdaptiveRenderingError("Visible source text changed")
        if _publisher_ruby(roots[path]) != before_publisher[path]:
            raise AdaptiveRenderingError("Publisher-ruby suppression attempt")
    _validate_links(output_files, strict_source_markup=strict_source_markup)

    document_results = [
        _add_hash({
            "id": f"adaptive-document-{number:04d}",
            "path": path,
            "source_sha256": hashlib.sha256(source_files[path]).hexdigest(),
            "output_sha256": hashlib.sha256(output_files[path]).hexdigest(),
        })
        for number, path in enumerate(sorted(output_files), 1)
    ]
    for result in occurrence_results:
        path = result["document_path"]
        result["source_document_hash"] = hashlib.sha256(source_files[path]).hexdigest()
        result["output_document_hash"] = hashlib.sha256(output_files[path]).hexdigest()
        result["hash"] = stable_hash(_without_hash(result))
    configuration = _add_hash({"enabled": True})
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_id": "adaptive-rendering-report-v1",
        "book_id": book["book_id"],
        "source_schema_versions": {
            "canonical_book": 2,
            "annotation_plan": 2,
            "grammar_plan": 1 if grammar_plan is not None else None,
            "assistance_report": 1,
            "density_report": 1,
        },
        "source_hashes": {
            "canonical_book": stable_hash(book),
            "annotation_plan": stable_hash(annotation_plan),
            "grammar_plan": stable_hash(grammar_plan) if grammar_plan is not None else "none",
            "assistance_report": assistance["hash"],
            "density_report": density["hash"],
            "source_directory": directory_hash(source_files),
        },
        "precedence": PRECEDENCE,
        "configuration": configuration,
        "document_results": document_results,
        "occurrence_results": occurrence_results,
        "diagnostics": diagnostics,
    }
    report["hash"] = stable_hash(report)
    return report, output_files


def safe_render_adaptive_output(
    source_dir: str | Path,
    book: dict[str, Any],
    annotation_plan: dict[str, Any],
    grammar_plan: dict[str, Any] | None,
    assistance: dict[str, Any],
    density: dict[str, Any],
    *,
    enabled: bool = False,
    failure_reason: str | None = None,
    strict_source_markup: bool = True,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    source_files = read_xhtml_directory(source_dir)
    if not enabled:
        return empty_report(book.get("book_id"), "disabled"), source_files
    if failure_reason:
        return empty_report(book.get("book_id"), failure_reason), source_files
    try:
        return render_adaptive_output(
            source_dir, book, annotation_plan, grammar_plan, assistance, density,
            enabled=True, strict_source_markup=strict_source_markup,
        )
    except AdaptiveRenderingError as error:
        message = str(error).lower()
        mapping = (
            ("source-hash", "source-hash-mismatch"),
            ("identity", "density-report-mismatch"),
            ("unknown occurrence", "unknown-occurrence"),
            ("offset", "invalid-source-offset"),
            ("ambiguous", "ambiguous-dom-mapping"),
            ("missing approved reading", "missing-approved-reading"),
            ("missing approved meaning", "missing-approved-meaning"),
            ("publisher", "publisher-ruby-suppression-attempt"),
            ("grammar", "grammar-disposition-conflict"),
            ("nested", "nested-anchor-risk"),
            ("fragment", "broken-fragment"),
            ("unsafe hidden", "unsafe-hidden-content"),
            ("unsupported", "unsupported-schema-or-field"),
        )
        reason = next((code for key, code in mapping if key in message), "invalid-configuration")
        return empty_report(book.get("book_id"), reason), source_files


def write_output(files: dict[str, bytes], directory: str | Path) -> None:
    root = Path(directory)
    for relative, data in files.items():
        target = root / PurePosixPath(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
