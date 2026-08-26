"""Deterministic all-token Guided Reading notes for personal EPUBs."""

from __future__ import annotations

import hashlib
import json
import posixpath
from typing import Any
from xml.etree import ElementTree as ET

from furiganalyse.book_analysis import local_name
from furiganalyse.linked_output import (
    X,
    LinkedOutput,
    LinkedOutputError,
    _all_ids,
    _has_ancestor,
    _index_book,
    _leaf_blocks,
    _parent_map,
    _relative_href,
    _safe_path,
    _validate_links,
    _visible_map,
    _wrap_text,
)
from furiganalyse.vocabulary_analysis import JAPANESE_PATTERN


SCHEMA_VERSION = 1
FUNCTION_CATEGORIES = {"助詞", "助動詞", "接続詞", "連体詞", "感動詞"}
FUNCTION_GLOSSES = {
    "は": "topic or contrast marker; contextual interpretation varies",
    "が": "subject or focus marker; contextual interpretation varies",
    "を": "direct-object or path marker",
    "に": "target, recipient, location, time, result, or agent marker",
    "で": "location, means, material, cause, or circumstance marker",
    "へ": "direction or destination marker",
    "と": "quotation, companion, comparison, or result marker",
    "も": "also, too, even, or inclusive emphasis",
    "の": "possession, modification, explanation, or nominalization marker",
    "から": "from, starting point, source, or reason",
    "まで": "until, as far as, or endpoint",
    "より": "from, than, or comparison baseline",
    "や": "non-exhaustive list marker",
    "か": "question, uncertainty, or alternative marker",
    "ね": "confirmation, agreement, or shared-attention ending",
    "よ": "assertive or new-information ending",
    "な": "modifier or sentence-ending function; interpretation depends on form",
    "て": "connective form linking actions, states, requests, or causes",
    "による": "by, due to, or according to",
    "だ": "plain copula: be; form depends on the surrounding construction",
    "です": "polite copula: be",
    "ます": "polite verbal auxiliary",
    "た": "past or completed-action auxiliary",
    "ない": "negative auxiliary: not; does not",
    "ぬ": "negative auxiliary, often literary or fixed in style",
    "たい": "desire auxiliary: want to",
    "れる": "passive, potential, spontaneous, or honorific auxiliary",
    "られる": "passive, potential, spontaneous, or honorific auxiliary",
    "せる": "causative auxiliary: make or let",
    "させる": "causative auxiliary: make or let",
    "う": "volitional or conjectural auxiliary",
    "よう": "volitional, conjectural, resemblance, or manner-related form",
    "そう": "appearance or hearsay auxiliary; interpretation depends on form",
}

GUIDED_STYLE = """
.guided-notes { font-family: sans-serif; line-height: 1.5; writing-mode: horizontal-tb !important;
  -webkit-writing-mode: horizontal-tb !important; max-width: 42rem; margin: 0 auto; padding: .8rem 1rem 2rem;
  overflow-wrap: anywhere; }
.guided-note { border-top: 1px solid #bbb; margin: 1.1em 0; padding: .8em 0; }
.guided-note__kind { font-size: .8em; font-weight: bold; text-transform: uppercase; }
.guided-note__heading { font-size: 1.2em; margin: .2em 0; }
.guided-note__reading { font-size: .85em; font-weight: normal; margin-left: .35em; }
.guided-note__analysis, .guided-note__meaning { margin: .4em 0; }
.guided-note__context { margin: .5em 0; padding: .5em .75em; overflow-wrap: anywhere; }
.guided-note__target { font-weight: bold; }
.guided-note__backlink { font-size: .9em; }
.guided-components { border-top: 1px dotted #bbb; margin-top: .7em; padding-top: .5em; }
.guided-components__list { margin: .4em 0; padding-left: 1.4em; }
a.guided-link:link, a.guided-note__backlink:link { color: #8a4b08 !important; text-decoration: underline !important; }
a.guided-link:visited, a.guided-note__backlink:visited { color: #6b3fa0 !important; text-decoration: underline !important; }
"""


def _stable_hash(value: Any) -> str:
    payload = dict(value) if isinstance(value, dict) else value
    if isinstance(payload, dict):
        payload.pop("hash", None)
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _function_gloss(surface: str, lemma: str, category: str) -> str:
    if surface in FUNCTION_GLOSSES:
        return FUNCTION_GLOSSES[surface]
    if lemma in FUNCTION_GLOSSES:
        return FUNCTION_GLOSSES[lemma]
    return {
        "助詞": "particle; its function depends on the surrounding construction",
        "助動詞": "auxiliary; tense, polarity, voice, mood, or politeness depends on form",
        "接続詞": "conjunction connecting this expression to surrounding discourse",
        "連体詞": "adnominal word modifying the following noun",
        "感動詞": "interjection or response expression",
    }.get(category, "function word; contextual interpretation is required")


def build_guided_reading_plan(
    book: dict[str, Any],
    vocabulary: dict[str, Any],
    annotation_plan: dict[str, Any],
) -> dict[str, Any]:
    """Build a separate plan for tokens not covered by dictionary source links."""
    if book.get("schema_version") != 2 or vocabulary.get("schema_version") != 4:
        raise ValueError("Guided Reading requires canonical v2 and vocabulary v4")
    covered_token_ids = {
        token_id
        for item in annotation_plan.get("items", [])
        for occurrence in item.get("occurrences", [])
        for token_id in occurrence.get("token_ids", [])
    }
    groups: dict[tuple, list[dict[str, Any]]] = {}
    diagnostics = []
    for token in vocabulary.get("tokens", []):
        if token["id"] in covered_token_ids:
            continue
        category = (token.get("part_of_speech") or "").split(",", 1)[0]
        if category == "記号" or not JAPANESE_PATTERN.search(token["surface"]):
            continue
        if token.get("publisher_ruby_id"):
            diagnostics.append({
                "token_id": token["id"],
                "reason": "publisher-ruby-preserved",
            })
            continue
        pos_str = token.get("part_of_speech") or ""
        is_function = (
            category in FUNCTION_CATEGORIES
            or ("非自立" in pos_str and token["surface"] in {"の", "こと", "もの", "わけ", "はず", "よう", "ほう"})
        )
        kind = "function" if is_function else "unmatched"
        meaning = (
            _function_gloss(token["surface"], token["lemma"], category)
            if kind == "function"
            else "No compatible local dictionary gloss; inspect the lemma and sentence context."
        )
        key = (
            kind,
            token["surface"],
            token["lemma"],
            token.get("reading"),
            token.get("part_of_speech"),
            meaning,
        )
        groups.setdefault(key, []).append(token)

    ordered_groups = sorted(
        groups.items(),
        key=lambda value: (
            value[1][0]["chapter_id"],
            value[1][0]["block_id"],
            value[1][0]["sentence_id"],
            value[1][0]["sentence_start"],
            value[0],
        ),
    )
    items = []
    for item_number, (key, tokens) in enumerate(ordered_groups, 1):
        kind, surface, lemma, reading, part_of_speech, meaning = key
        item_id = f"guided-item-{item_number:05d}"
        occurrences = []
        # For grammar/particles (function words), only link the first occurrence in the book
        target_tokens = [tokens[0]] if kind == "function" else tokens
        for occurrence_number, token in enumerate(target_tokens, 1):
            occurrence_id = f"{item_id}-occ-{occurrence_number:05d}"
            occurrences.append({
                "id": occurrence_id,
                "token_id": token["id"],
                "chapter_id": token["chapter_id"],
                "block_id": token["block_id"],
                "sentence_id": token["sentence_id"],
                "sentence_start": token["sentence_start"],
                "sentence_end": token["sentence_end"],
                "block_start": token["block_start"],
                "block_end": token["block_end"],
                "source_anchor_id": f"guided-src-{occurrence_id}",
            })
        items.append({
            "id": item_id,
            "kind": kind,
            "surface": surface,
            "lemma": lemma,
            "reading": reading,
            "part_of_speech": part_of_speech,
            "display_assistance": meaning,
            "provenance": "local-curated-function-table" if kind == "function" else "local-tokenizer-no-dictionary-match",
            "occurrences": occurrences,
        })

    expression_components = []
    token_by_id = {token["id"]: token for token in vocabulary["tokens"]}
    for item in annotation_plan.get("items", []):
        if item.get("kind") != "expression":
            continue
        components = []
        for token_id in item.get("token_ids", []):
            token = token_by_id[token_id]
            category = (token.get("part_of_speech") or "").split(",", 1)[0]
            components.append({
                "token_id": token_id,
                "surface": token["surface"],
                "lemma": token["lemma"],
                "reading": token.get("reading"),
                "part_of_speech": token.get("part_of_speech"),
                "assistance": (
                    _function_gloss(token["surface"], token["lemma"], category)
                    if category in FUNCTION_CATEGORIES
                    else "component of the linked dictionary expression"
                ),
            })
        expression_components.append({"study_item_id": item["id"], "components": components})

    plan = {
        "schema_version": SCHEMA_VERSION,
        "id": "guided-reading-plan-v1",
        "book_id": book["book_id"],
        "canonical_hash": _stable_hash(book),
        "vocabulary_hash": _stable_hash(vocabulary),
        "annotation_plan_hash": _stable_hash(annotation_plan),
        "function_dataset_id": "furiganalyse-guided-function-words-v1",
        "function_dataset_version": "2026-08-25",
        "fixture_notice": "Deterministic local reading assistance; not contextual sentence translation.",
        "items": items,
        "expression_components": expression_components,
        "diagnostics": diagnostics,
    }
    plan["hash"] = _stable_hash(plan)
    return plan


def _sentence_index(book: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        sentence["id"]: sentence
        for chapter in book["chapters"]
        for block in chapter["blocks"]
        for sentence in block["sentences"]
    }


def _guided_document(title: str) -> tuple[ET.Element, ET.Element]:
    root = ET.Element(X + "html", {
        "lang": "ja",
        "{http://www.w3.org/XML/1998/namespace}lang": "ja",
    })
    head = ET.SubElement(root, X + "head")
    ET.SubElement(head, X + "meta", {"charset": "utf-8"})
    ET.SubElement(head, X + "title").text = title
    ET.SubElement(head, X + "style", {"type": "text/css"}).text = GUIDED_STYLE
    body = ET.SubElement(root, X + "body")
    main = ET.SubElement(body, X + "main", {"class": "guided-notes"})
    ET.SubElement(main, X + "h1").text = title
    return root, main


def _serialize(root: ET.Element) -> bytes:
    return ET.tostring(
        root, encoding="utf-8", xml_declaration=True, short_empty_elements=True
    ) + b"\n"


def _add_expression_components(
    files: dict[str, bytes],
    notes_path: str,
    plan: dict[str, Any],
) -> None:
    if not plan["expression_components"]:
        return
    root = ET.fromstring(files[notes_path])
    sections = {
        section.get("data-item-id"): section
        for section in root.findall(".//" + X + "section")
    }
    for record in plan["expression_components"]:
        section = sections.get(record["study_item_id"])
        if section is None:
            raise LinkedOutputError("Missing expression study note")
        container = ET.Element(X + "div", {"class": "guided-components"})
        ET.SubElement(container, X + "strong").text = "Phrase components"
        listing = ET.SubElement(container, X + "ul", {"class": "guided-components__list"})
        for component in record["components"]:
            item = ET.SubElement(listing, X + "li")
            reading = f"【{component['reading']}】" if component.get("reading") else ""
            item.text = (
                f"{component['surface']}{reading} — lemma {component['lemma']} — "
                f"{component.get('part_of_speech') or 'unclassified'} — {component['assistance']}"
            )
        details = section.find(X + "dl[@class='study-note__details']")
        section.insert(list(section).index(details) if details is not None else len(section), container)
    files[notes_path] = _serialize(root)


def render_guided_reading(
    output: LinkedOutput,
    book: dict[str, Any],
    plan: dict[str, Any],
    *,
    items_per_page: int = 25,
) -> tuple[LinkedOutput, dict[str, Any]]:
    """Add non-overlapping function/unmatched links and compact local notes."""
    if plan.get("schema_version") != 1 or plan.get("book_id") != book.get("book_id"):
        raise LinkedOutputError("Guided Reading plan mismatch")
    if items_per_page < 1:
        raise LinkedOutputError("Guided Reading page size must be positive")
    files = dict(output.files)
    _add_expression_components(files, output.notes_path, plan)
    chapters, _, sentences = _index_book(book)
    occurrences_by_chapter: dict[str, list[tuple[dict, dict]]] = {}
    for item in plan["items"]:
        for occurrence in item["occurrences"]:
            occurrences_by_chapter.setdefault(occurrence["chapter_id"], []).append(
                (item, occurrence)
            )
    note_directory = posixpath.dirname(output.notes_path)
    guided_index_path = posixpath.join(note_directory, "guided-notes.xhtml")
    page_records = []
    rendered_occurrences = 0
    skipped = []

    for chapter in chapters.values():
        source_path = _safe_path(chapter["source_path"])
        if source_path not in files:
            continue
        root = ET.fromstring(files[source_path])
        elements = _leaf_blocks(root)
        if len(elements) != len(chapter["blocks"]):
            raise LinkedOutputError("Guided Reading ambiguous block mapping")
        mapped = dict(zip((block["id"] for block in chapter["blocks"]), elements))
        parents = _parent_map(root)
        block_maps = {
            block_id: _visible_map(element)[1]
            for block_id, element in mapped.items()
        }
        renderable = []
        for item, occurrence in occurrences_by_chapter.get(chapter["id"], []):
            refs = block_maps[occurrence["block_id"]]
            start, end = occurrence["block_start"], occurrence["block_end"]
            if not 0 <= start < end <= len(refs):
                raise LinkedOutputError("Guided Reading source offset mismatch")
            first, last = refs[start], refs[end - 1]
            owner = first.owner
            raw = getattr(owner, first.attribute) or ""
            safe = (
                owner is last.owner
                and first.attribute == last.attribute
                and raw[first.raw_index:last.raw_index + 1] == item["surface"]
                and local_name(owner.tag) not in {"a", "ruby", "rb", "rt", "rp"}
                and not _has_ancestor(owner, "a", parents)
                and not _has_ancestor(owner, "ruby", parents)
            )
            # Text in the tail of a ruby or a element is positioned *after*
            # the closing tag and is safe to wrap in a guided-link.
            if local_name(owner.tag) in {"a", "ruby"} and first.attribute == "tail":
                safe = (
                    owner is last.owner
                    and first.attribute == last.attribute
                    and raw[first.raw_index:last.raw_index + 1] == item["surface"]
                    and not _has_ancestor(owner, "a", parents)
                    and not _has_ancestor(owner, "ruby", parents)
                )
            if safe:
                renderable.append((item, occurrence, first, last))
            else:
                skipped.append({"occurrence_id": occurrence["id"], "reason": "protected-existing-markup"})
        renderable_in_source_order = sorted(
            renderable,
            key=lambda value: (
                value[1]["block_id"],
                value[1]["block_start"],
                value[1]["id"],
            ),
        )
        page_for_occurrence = {}
        for start in range(0, len(renderable_in_source_order), items_per_page):
            chunk = renderable_in_source_order[start:start + items_per_page]
            page_number = len(page_records) + 1
            page_path = posixpath.join(
                note_directory, f"guided-notes-page-{page_number:04d}.xhtml"
            )
            for _, occurrence, _, _ in chunk:
                page_for_occurrence[occurrence["id"]] = page_path
            page_records.append((page_number, page_path, source_path, chunk))
        for item, occurrence, first, last in sorted(
            renderable,
            key=lambda value: (value[1]["block_id"], -value[1]["block_start"], value[1]["id"]),
        ):
            page_path = page_for_occurrence[occurrence["id"]]
            _wrap_text(
                first,
                last,
                occurrence["source_anchor_id"],
                _relative_href(
                    source_path,
                    page_path,
                    f"guided-note-{occurrence['id']}",
                ),
                parents,
                "guided-link",
            )
            parents = _parent_map(root)
            rendered_occurrences += 1
        files[source_path] = _serialize(root)

    for page_number, page_path, source_path, page_occurrences in page_records:
        root, main = _guided_document(f"Guided Reading Notes — Page {page_number}")
        for item, occurrence, _, _ in page_occurrences:
            section = ET.SubElement(main, X + "section", {
                "id": f"guided-note-{occurrence['id']}",
                "class": f"guided-note guided-note--{item['kind']}",
            })
            ET.SubElement(section, X + "p", {"class": "guided-note__kind"}).text = (
                "Function word" if item["kind"] == "function" else "Unmatched local token"
            )
            heading = ET.SubElement(section, X + "h2", {"class": "guided-note__heading"})
            heading.text = item["surface"]
            if item.get("reading"):
                ET.SubElement(heading, X + "span", {"class": "guided-note__reading"}).text = f"【{item['reading']}】"
            ET.SubElement(section, X + "p", {"class": "guided-note__analysis"}).text = (
                f"Lemma: {item['lemma']} · {item.get('part_of_speech') or 'unclassified'}"
            )
            ET.SubElement(section, X + "p", {"class": "guided-note__meaning"}).text = item["display_assistance"]
            sentence = sentences[occurrence["sentence_id"]]
            quote = ET.SubElement(section, X + "blockquote", {"class": "guided-note__context"})
            quote.text = sentence["text"][:occurrence["sentence_start"]]
            mark = ET.SubElement(quote, X + "mark", {"class": "guided-note__target"})
            mark.text = sentence["text"][occurrence["sentence_start"]:occurrence["sentence_end"]]
            mark.tail = sentence["text"][occurrence["sentence_end"]:]
            paragraph = ET.SubElement(section, X + "p")
            backlink = ET.SubElement(paragraph, X + "a", {
                "class": "guided-note__backlink",
                "href": _relative_href(page_path, source_path, occurrence["source_anchor_id"]),
            })
            backlink.text = "← return to this occurrence"
        files[page_path] = _serialize(root)

    index_root, index_main = _guided_document("Guided Reading Notes")
    ET.SubElement(index_main, X + "p").text = (
        "Local dictionary, phrase-component, function-word, and tokenizer assistance; not contextual sentence translation."
    )
    ordered = ET.SubElement(index_main, X + "ol")
    for page_number, page_path, _, _ in page_records:
        item = ET.SubElement(ordered, X + "li")
        ET.SubElement(item, X + "a", {
            "href": posixpath.relpath(page_path, note_directory)
        }).text = f"Guided notes page {page_number}"
    files[guided_index_path] = _serialize(index_root)
    _validate_links(files)
    for path, payload in files.items():
        root = ET.fromstring(payload)
        _all_ids(root)
    report = {
        "schema_version": 1,
        "id": "guided-reading-rendering-report-v1",
        "book_id": book["book_id"],
        "plan_hash": plan["hash"],
        "guided_note_pages": len(page_records),
        "rendered_occurrences": rendered_occurrences,
        "skipped_occurrences": skipped,
    }
    report["hash"] = _stable_hash(report)
    return LinkedOutput(notes_path=output.notes_path, files=files), report
