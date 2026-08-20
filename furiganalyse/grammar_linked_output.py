"""Deterministic source links and contexts for validated grammar plans."""

from __future__ import annotations

import copy
import posixpath
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from furiganalyse.book_analysis import local_name
from furiganalyse.grammar_analysis import stable_hash
from furiganalyse.grammar_notes import XHTML_NS, render_grammar_notes, validate_grammar_plan_for_notes
from furiganalyse.linked_output import (
    LinkedOutputError, _leaf_blocks, _parent_map, _relative_href, _ruby_snapshot,
    _safe_path, _visible_map,
)

X = f"{{{XHTML_NS}}}"
GRAMMAR_NOTES_FILENAME = "grammar-notes.xhtml"
LINKABLE = {"grammar-link", "separate-nonoverlapping-links"}
STATUS = {
    "grammar-link": "linked",
    "separate-nonoverlapping-links": "linked",
    "grammar-note-reference-only": "reference only",
    "rejected-ambiguous-overlap": "partial overlap rejected",
    "publisher-ruby-preserved": "publisher ruby preserved",
    "vocabulary-link": "reference only",
}
LINK_STYLE = """
.grammar-study-note__occurrence { margin: .75em 0; }
.grammar-study-note__context { margin: .4em 0; }
.grammar-study-note__target { font-weight: bold; }
.grammar-study-note__backlink { font-size: .9em; }
"""


@dataclass(frozen=True)
class GrammarLinkedOutput:
    notes_path: str
    files: dict[str, bytes]


def _load_source(root: Path, relative: str) -> bytes:
    path = root / PurePosixPath(_safe_path(relative))
    if not path.is_file():
        raise LinkedOutputError("Missing linked source")
    return path.read_bytes()


def _snapshot_links(root: ET.Element) -> dict[str, bytes]:
    result = {}
    for link in root.findall(".//" + X + "a"):
        anchor = link.get("id")
        if anchor and "study-link" in link.get("class", "").split():
            value = copy.deepcopy(link)
            value.tail = None
            result[anchor] = ET.tostring(value, encoding="utf-8")
    return result


def _wrap_text(ref_start, ref_end, anchor_id, href, parents):
    if ref_start.owner is not ref_end.owner or ref_start.attribute != ref_end.attribute:
        raise LinkedOutputError("Ambiguous grammar text insertion")
    owner = ref_start.owner
    current = owner
    while current in parents:
        if local_name(current.tag) in {"a", "ruby", "rt", "rp"}:
            raise LinkedOutputError("Grammar selection is inside protected markup")
        current = parents[current]
    if local_name(owner.tag) in {"a", "ruby", "rt", "rp"}:
        raise LinkedOutputError("Grammar selection is inside protected markup")
    raw = getattr(owner, ref_start.attribute) or ""
    start, end = ref_start.raw_index, ref_end.raw_index + 1
    anchor = ET.Element(X + "a", {"id": anchor_id, "class": "grammar-link", "href": href})
    anchor.text = raw[start:end]
    if ref_start.attribute == "text":
        owner.text = raw[:start]
        anchor.tail = raw[end:]
        owner.insert(0, anchor)
    else:
        parent = parents.get(owner)
        if parent is None:
            raise LinkedOutputError("Grammar tail has no parent")
        position = list(parent).index(owner) + 1
        owner.tail = raw[:start]
        anchor.tail = raw[end:]
        parent.insert(position, anchor)


def _notes(plan, book, chapter_paths, notes_path):
    root = ET.fromstring(render_grammar_notes(plan, book["_dataset"]))
    style = root.find(X + "head/" + X + "style")
    style.text = (style.text or "") + LINK_STYLE
    sections = {x.get("data-grammar-item-id"): x for x in root.findall(".//" + X + "section")}
    sentences = {
        sentence["id"]: sentence
        for chapter in book["chapters"] for block in chapter["blocks"]
        for sentence in block["sentences"]
    }
    occurrence_map = {x["id"]: x for x in plan["occurrences"]}
    mixed = []
    for item in plan["items"]:
        section = sections[item["id"]]
        old = section.find(X + "div[@class='grammar-study-note__occurrences']")
        section.remove(old)
        details = section.find(X + "dl")
        container = ET.Element(X + "div", {"class": "grammar-study-note__occurrences"})
        for occurrence_id in item["occurrence_ids"]:
            occurrence = occurrence_map[occurrence_id]
            sentence = sentences.get(occurrence["sentence_id"])
            if sentence is None:
                raise LinkedOutputError("Unknown grammar context sentence")
            start, end = occurrence["sentence_start"], occurrence["sentence_end"]
            if sentence["text"][start:end] != occurrence["surface"]:
                raise LinkedOutputError("Grammar context offset mismatch")
            record = ET.Element(X + "div", {
                "class": "grammar-study-note__occurrence",
                "data-occurrence-id": occurrence_id,
                "data-disposition": occurrence["link_disposition"],
            })
            ET.SubElement(record, X + "p", {"class": "grammar-study-note__status"}).text = STATUS[occurrence["link_disposition"]]
            quote = ET.SubElement(record, X + "blockquote", {"class": "grammar-study-note__context"})
            quote.text = sentence["text"][:start]
            mark = ET.SubElement(quote, X + "mark", {"class": "grammar-study-note__target"})
            mark.text = occurrence["surface"]
            mark.tail = sentence["text"][end:]
            mixed.append((quote, mark, sentence["text"], start, end))
            ET.SubElement(record, X + "p", {"class": "grammar-study-note__reference"}).text = (
                f"{occurrence['chapter_id']} — {occurrence['source_grammar_occurrence_id']} — {occurrence['sentence_record_id']}"
            )
            if occurrence["link_disposition"] in LINKABLE:
                paragraph = ET.SubElement(record, X + "p")
                link = ET.SubElement(paragraph, X + "a", {
                    "class": "grammar-study-note__backlink",
                    "href": _relative_href(notes_path, chapter_paths[occurrence["chapter_id"]], occurrence["source_anchor_id"]),
                })
                link.text = "← return to grammar occurrence"
            container.append(record)
        section.insert(list(section).index(details), container)
    ET.indent(root, space="  ")
    for quote, mark, text, start, end in mixed:
        quote.text = text[:start]
        mark.tail = text[end:]
    return ET.tostring(root, encoding="utf-8", xml_declaration=True, short_empty_elements=True) + b"\n"


def _validate_links(files):
    roots = {path: ET.fromstring(data) for path, data in files.items()}
    ids = {}
    for path, root in roots.items():
        values = [x.get("id") for x in root.iter() if x.get("id")]
        if len(values) != len(set(values)):
            raise LinkedOutputError("Duplicate linked XHTML ID")
        ids[path] = set(values)
    generated = []
    for source, root in roots.items():
        for link in root.findall(".//" + X + "a"):
            href = link.get("href", "")
            split = urlsplit(href)
            if split.scheme or split.netloc or ".." in PurePosixPath(split.path).parts:
                raise LinkedOutputError("Unsafe linked XHTML href")
            target = posixpath.normpath(posixpath.join(posixpath.dirname(source), split.path)) if split.path else source
            if target not in roots or not split.fragment or split.fragment not in ids[target]:
                raise LinkedOutputError("Broken linked XHTML href")
            classes = link.get("class", "").split()
            if "grammar-link" in classes or "grammar-study-note__backlink" in classes:
                generated.append((source, target, split.fragment))
            if any(local_name(x.tag) == "a" for x in link.iter() if x is not link):
                raise LinkedOutputError("Nested linked XHTML anchor")
    return generated


def create_grammar_linked_output(source_dir, book, plan, dataset):
    validate_grammar_plan_for_notes(plan, dataset)
    if book.get("schema_version") != 2 or book.get("book_id") != plan.get("book_id"):
        raise LinkedOutputError("Grammar linked source identity mismatch")
    if plan["source_hashes"].get("book") != stable_hash(book):
        raise LinkedOutputError("Stale grammar linked canonical source")
    source_dir = Path(source_dir)
    chapter_paths = {chapter["id"]: _safe_path(chapter["source_path"]) for chapter in book["chapters"]}
    notes_path = posixpath.join(posixpath.dirname(next(iter(chapter_paths.values()))), GRAMMAR_NOTES_FILENAME)
    files = {}
    occurrences_by_chapter = {}
    for occurrence in plan["occurrences"]:
        occurrences_by_chapter.setdefault(occurrence["chapter_id"], []).append(occurrence)
    block_map = {block["id"]: block for chapter in book["chapters"] for block in chapter["blocks"]}
    for chapter in book["chapters"]:
        source_path = chapter_paths[chapter["id"]]
        root = ET.fromstring(_load_source(source_dir, source_path))
        elements = _leaf_blocks(root)
        if len(elements) != len(chapter["blocks"]):
            raise LinkedOutputError("Ambiguous grammar block mapping")
        mapped = dict(zip((x["id"] for x in chapter["blocks"]), elements))
        before_links = _snapshot_links(root)
        before_ruby = {x.get("id"): _ruby_snapshot(x) for x in root.findall(".//" + X + "ruby") if x.get("id")}
        maps = {}
        before_text = {}
        for block in chapter["blocks"]:
            text, refs, rubies = _visible_map(mapped[block["id"]])
            if text != block["text"]:
                raise LinkedOutputError("Canonical grammar block mismatch")
            maps[block["id"]] = refs
            before_text[block["id"]] = text
        parents = _parent_map(root)
        selected = [x for x in occurrences_by_chapter.get(chapter["id"], []) if x["link_disposition"] in LINKABLE]
        selected.sort(key=lambda x: (x["block_id"], -x["block_start"], x["id"]))
        for occurrence in selected:
            block = block_map.get(occurrence["block_id"])
            if block is None:
                raise LinkedOutputError("Unknown grammar block")
            start, end = occurrence["block_start"], occurrence["block_end"]
            if block["text"][start:end] != occurrence["surface"]:
                raise LinkedOutputError("Grammar source offset mismatch")
            refs = maps[block["id"]]
            if end > len(refs):
                raise LinkedOutputError("Grammar XHTML range mismatch")
            first, last = refs[start], refs[end - 1]
            _wrap_text(first, last, occurrence["source_anchor_id"], _relative_href(source_path, notes_path, next(i["note_anchor_id"] for i in plan["items"] if occurrence["id"] in i["occurrence_ids"])), parents)
            parents = _parent_map(root)
        for block in chapter["blocks"]:
            if _visible_map(mapped[block["id"]])[0] != before_text[block["id"]]:
                raise LinkedOutputError("Grammar visible source text changed")
        if _snapshot_links(root) != before_links:
            raise LinkedOutputError("Existing vocabulary link changed")
        after_ruby = {x.get("id"): _ruby_snapshot(x) for x in root.findall(".//" + X + "ruby") if x.get("id")}
        if after_ruby != before_ruby:
            raise LinkedOutputError("Publisher ruby changed")
        files[source_path] = ET.tostring(root, encoding="utf-8", xml_declaration=True, short_empty_elements=True) + b"\n"
    vocabulary_notes_path = posixpath.join(posixpath.dirname(notes_path), "study-notes.xhtml")
    files[vocabulary_notes_path] = _load_source(source_dir, vocabulary_notes_path)
    note_book = dict(book)
    note_book["_dataset"] = dataset
    files[notes_path] = _notes(plan, note_book, chapter_paths, notes_path)
    generated = _validate_links(files)
    expected = sum(x["link_disposition"] in LINKABLE for x in plan["occurrences"])
    if len(generated) != expected * 2:
        raise LinkedOutputError("Missing grammar forward link or backlink")
    return GrammarLinkedOutput(notes_path, files)


def write_grammar_linked_output(output, directory):
    root = Path(directory)
    for relative, data in sorted(output.files.items()):
        target = root / PurePosixPath(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
