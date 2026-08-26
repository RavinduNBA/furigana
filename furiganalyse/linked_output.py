"""Deterministic linked chapter and study-note XHTML output."""

from __future__ import annotations

import copy
import json
import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from furiganalyse.book_analysis import BLOCK_TAGS, HIDDEN_TAGS, local_name
from furiganalyse.study_notes import (
    XHTML_NS,
    render_study_notes,
    validate_annotation_plan_for_notes,
)

X = f"{{{XHTML_NS}}}"
NOTES_FILENAME = "study-notes.xhtml"
LINK_STYLE = """
.study-note__occurrence { margin: .75em 0; }
.study-note__context { margin: .4em 0; }
.study-note__target { font-weight: bold; }
.study-note__backlink { font-size: .9em; }
"""
ET.register_namespace("", XHTML_NS)


class LinkedOutputError(ValueError):
    """Raised when safe deterministic source linking is impossible."""


@dataclass(frozen=True)
class LinkedOutput:
    notes_path: str
    files: dict[str, bytes]


@dataclass(frozen=True)
class _CharRef:
    owner: ET.Element
    attribute: str
    raw_index: int


@dataclass(frozen=True)
class _RubyRef:
    start: int
    end: int
    element: ET.Element


def _safe_path(value: str) -> str:
    candidate = PurePosixPath(value)
    if not value or candidate.is_absolute() or ".." in candidate.parts or "\\" in value:
        raise LinkedOutputError(f"Unsafe output path: {value!r}")
    return candidate.as_posix()


def _leaf_blocks(root: ET.Element) -> list[ET.Element]:
    candidates = [
        element
        for element in root.iter()
        if local_name(element.tag) in BLOCK_TAGS
        and not any(
            descendant is not element and local_name(descendant.tag) in BLOCK_TAGS
            for descendant in element.iter()
        )
    ]
    # Canonical extraction intentionally omits empty structural blocks. Linked
    # mapping must apply the same rule for production EPUBs containing empty
    # headings, list items, or paragraph placeholders.
    return [element for element in candidates if _visible_map(element)[0]]


def _visible_map(element: ET.Element) -> tuple[str, list[_CharRef], list[_RubyRef]]:
    characters: list[str] = []
    references: list[_CharRef] = []
    rubies: list[_RubyRef] = []

    def append(owner: ET.Element, attribute: str):
        raw = getattr(owner, attribute) or ""
        for index, character in enumerate(raw):
            if character.isspace():
                if characters and characters[-1] != " ":
                    characters.append(" ")
                    references.append(_CharRef(owner, attribute, index))
            else:
                characters.append(character)
                references.append(_CharRef(owner, attribute, index))

    def walk(node: ET.Element):
        name = local_name(node.tag)
        if name in HIDDEN_TAGS:
            return
        start = len(characters) if name == "ruby" else None
        append(node, "text")
        for child in node:
            walk(child)
            append(child, "tail")
        if start is not None:
            rubies.append(_RubyRef(start, len(characters), node))

    walk(element)
    if characters and characters[-1] == " ":
        characters.pop()
        references.pop()
    return "".join(characters), references, rubies


def _parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def _has_ancestor(element: ET.Element, name: str, parents: dict) -> bool:
    current = element
    while current in parents:
        current = parents[current]
        if local_name(current.tag) == name:
            return True
    return False


def _ruby_snapshot(element: ET.Element) -> bytes:
    value = copy.deepcopy(element)
    value.tail = None
    return ET.tostring(value, encoding="utf-8")


def _wrap_ruby_boundary(
    rubies: list[ET.Element] | ET.Element,
    ref_prefix_start: _CharRef | None,
    okuri_len: int,
    anchor_id: str,
    href: str,
    parents: dict[ET.Element, ET.Element],
    link_class: str = "study-link",
):
    if isinstance(rubies, ET.Element):
        ruby_list = [rubies]
    else:
        ruby_list = list(rubies)
    if not ruby_list:
        return
    for r in ruby_list:
        if _has_ancestor(r, "a", parents):
            raise LinkedOutputError(
                f"Ruby boundary occurrence is inside an existing link: {anchor_id}"
            )
    if ref_prefix_start is not None and _has_ancestor(ref_prefix_start.owner, "a", parents):
        raise LinkedOutputError(
            f"Ruby boundary occurrence is inside an existing link: {anchor_id}"
        )
    first_ruby = ruby_list[0]
    last_ruby = ruby_list[-1]
    parent = parents.get(first_ruby)
    if parent is None:
        raise LinkedOutputError(f"Ruby element has no parent: {anchor_id}")
    position = list(parent).index(first_ruby)

    prefix_text = None
    if ref_prefix_start is not None:
        raw = getattr(ref_prefix_start.owner, ref_prefix_start.attribute) or ""
        prefix_text = raw[ref_prefix_start.raw_index:]
        new_raw = raw[:ref_prefix_start.raw_index]
        setattr(ref_prefix_start.owner, ref_prefix_start.attribute, new_raw if new_raw else None)

    tail = last_ruby.tail or ""
    if okuri_len > 0:
        okuri_text = tail[:okuri_len]
        remaining_tail = tail[okuri_len:]
        last_ruby.tail = okuri_text if okuri_text else None
    else:
        remaining_tail = tail
        last_ruby.tail = None

    anchor = ET.Element(X + "a", {"id": anchor_id, "class": link_class, "href": href})
    if prefix_text:
        anchor.text = prefix_text
    for r in ruby_list:
        parent.remove(r)
        anchor.append(r)
    parent.insert(position, anchor)
    anchor.tail = remaining_tail if remaining_tail else None


def _wrap_ruby(
    ruby: ET.Element,
    anchor_id: str,
    href: str,
    parents: dict[ET.Element, ET.Element],
):
    _wrap_ruby_boundary(ruby, None, 0, anchor_id, href, parents)


def _wrap_ruby_with_tail(
    ruby: ET.Element,
    okuri_len: int,
    anchor_id: str,
    href: str,
    parents: dict[ET.Element, ET.Element],
    link_class: str = "study-link",
):
    _wrap_ruby_boundary(ruby, None, okuri_len, anchor_id, href, parents, link_class)


def _wrap_text(
    ref_start: _CharRef,
    ref_end: _CharRef,
    anchor_id: str,
    href: str,
    parents: dict[ET.Element, ET.Element],
    link_class: str = "study-link",
):
    if ref_start.owner is not ref_end.owner or ref_start.attribute != ref_end.attribute:
        raise LinkedOutputError(f"Selection crosses XHTML text slots: {anchor_id}")
    owner = ref_start.owner
    if _has_ancestor(owner, "a", parents) or (
        local_name(owner.tag) == "a" and ref_start.attribute == "text"
    ):
        raise LinkedOutputError(f"Selection is inside an existing link: {anchor_id}")
    raw = getattr(owner, ref_start.attribute) or ""
    start, end = ref_start.raw_index, ref_end.raw_index + 1
    anchor = ET.Element(X + "a", {"id": anchor_id, "class": link_class, "href": href})
    anchor.text = raw[start:end]
    if ref_start.attribute == "text":
        owner.text = raw[:start]
        anchor.tail = raw[end:]
        owner.insert(0, anchor)
        return
    parent = parents.get(owner)
    if parent is None:
        raise LinkedOutputError(f"Tail selection has no parent: {anchor_id}")
    position = list(parent).index(owner) + 1
    owner.tail = raw[:start]
    anchor.tail = raw[end:]
    parent.insert(position, anchor)


def _load_source(input_path: Path, source_path: str) -> bytes:
    source_path = _safe_path(source_path)
    if input_path.is_dir():
        path = input_path / PurePosixPath(source_path)
        if not path.is_file():
            raise LinkedOutputError(f"Missing extracted source: {source_path}")
        return path.read_bytes()
    with zipfile.ZipFile(input_path) as archive:
        try:
            return archive.read(source_path)
        except KeyError as error:
            raise LinkedOutputError(f"Missing EPUB source: {source_path}") from error


def _index_book(book: dict[str, Any]):
    if book.get("schema_version") != 2:
        raise LinkedOutputError("Linked output requires canonical schema v2")
    chapters = {}
    blocks = {}
    sentences = {}
    for chapter in book.get("chapters", []):
        if chapter["id"] in chapters:
            raise LinkedOutputError(f"Duplicate chapter ID: {chapter['id']}")
        chapters[chapter["id"]] = chapter
        for block in chapter["blocks"]:
            if block["id"] in blocks:
                raise LinkedOutputError(f"Duplicate block ID: {block['id']}")
            blocks[block["id"]] = block
            for sentence in block["sentences"]:
                if sentence["id"] in sentences:
                    raise LinkedOutputError(f"Duplicate sentence ID: {sentence['id']}")
                sentences[sentence["id"]] = sentence
    return chapters, blocks, sentences


def _relative_href(source: str, target: str, fragment: str) -> str:
    relative = posixpath.relpath(target, posixpath.dirname(source))
    return f"{relative}#{fragment}"


def _render_notes(
    plan: dict[str, Any],
    sentences: dict[str, dict],
    chapter_paths: dict[str, str],
    notes_path: str,
) -> bytes:
    root = ET.fromstring(render_study_notes(plan))
    style = root.find(X + "head/" + X + "style")
    style.text = (style.text or "") + LINK_STYLE
    sections = {
        section.attrib["data-item-id"]: section
        for section in root.findall(".//" + X + "section")
    }
    mixed_content = []
    for item in plan["items"]:
        section = sections[item["id"]]
        details = section.find(X + "dl")
        container = ET.Element(X + "div", {"class": "study-note__occurrences"})
        for occurrence in item["occurrences"]:
            sentence = sentences.get(occurrence["sentence_id"])
            if sentence is None:
                raise LinkedOutputError(
                    f"Unknown sentence: {occurrence['sentence_id']}"
                )
            start, end = occurrence["sentence_start"], occurrence["sentence_end"]
            if not 0 <= start < end <= len(sentence["text"]):
                raise LinkedOutputError(f"Invalid sentence offsets: {occurrence['id']}")
            occurrence_surface = sentence["text"][start:end]
            record = ET.Element(
                X + "div",
                {
                    "class": "study-note__occurrence",
                    "data-occurrence-id": occurrence["id"],
                },
            )
            quote = ET.SubElement(
                record, X + "blockquote", {"class": "study-note__context"}
            )
            quote.text = sentence["text"][:start]
            mark = ET.SubElement(quote, X + "mark", {"class": "study-note__target"})
            mark.text = occurrence_surface
            mark.tail = sentence["text"][end:]
            mixed_content.append((quote, mark, sentence["text"], start, end))
            paragraph = ET.SubElement(record, X + "p")
            link = ET.SubElement(
                paragraph,
                X + "a",
                {
                    "class": "study-note__backlink",
                    "href": _relative_href(
                        notes_path,
                        chapter_paths[occurrence["chapter_id"]],
                        occurrence["source_anchor_id"],
                    ),
                },
            )
            link.text = f"← return to text {occurrence['occurrence_number']}"
            container.append(record)
        section.insert(list(section).index(details), container)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    for quote, mark, sentence_text, start, end in mixed_content:
        quote.text = sentence_text[:start]
        mark.tail = sentence_text[end:]
    return (
        ET.tostring(
            root, encoding="utf-8", xml_declaration=True, short_empty_elements=True
        )
        + b"\n"
    )


def _all_ids(root: ET.Element) -> set[str]:
    ids = [element.attrib["id"] for element in root.iter() if element.get("id")]
    if len(ids) != len(set(ids)):
        raise LinkedOutputError("Duplicate XHTML ID")
    return set(ids)


def _validate_links(files: dict[str, bytes]):
    roots = {path: ET.fromstring(data) for path, data in files.items()}
    ids = {path: _all_ids(root) for path, root in roots.items()}
    links = []
    for source, root in roots.items():
        for link in root.findall(".//" + X + "a"):
            generated = (
                "study-link" in link.attrib.get("class", "").split()
                or "study-note__backlink" in link.attrib.get("class", "").split()
            )
            href = link.attrib.get("href", "")
            split = urlsplit(href)
            if split.scheme or split.netloc:
                if generated:
                    raise LinkedOutputError(f"Unsafe generated href: {href}")
                continue
            target = (
                posixpath.normpath(
                    posixpath.join(posixpath.dirname(source), split.path)
                )
                if split.path
                else source
            )
            internal_xhtml = split.path.endswith((".html", ".xhtml")) or bool(
                split.fragment
            )
            if not generated and not internal_xhtml:
                continue
            if target not in files or (generated and not split.fragment):
                raise LinkedOutputError(f"Unsafe or unresolved generated href: {href}")
            if split.fragment and split.fragment not in ids[target]:
                raise LinkedOutputError(f"Broken generated href: {href}")
            if not generated:
                continue
            links.append((source, target, split.fragment))
            if any(
                local_name(child.tag) == "a"
                for child in link.iter()
                if child is not link
            ):
                raise LinkedOutputError("Nested generated anchor")
    return links


def create_linked_output(
    input_path: str | Path,
    book: dict[str, Any],
    plan: dict[str, Any],
) -> LinkedOutput:
    validate_annotation_plan_for_notes(plan)
    if plan.get("book_id") != book.get("book_id"):
        raise LinkedOutputError("Book/annotation-plan identity mismatch")
    chapters, blocks, sentences = _index_book(book)
    chapter_paths = {
        key: _safe_path(value["source_path"]) for key, value in chapters.items()
    }
    if not chapter_paths:
        raise LinkedOutputError("Canonical book has no chapters")
    notes_path = posixpath.join(
        posixpath.dirname(next(iter(chapter_paths.values()))), NOTES_FILENAME
    )
    occurrences_by_chapter: dict[str, list[tuple[dict, dict]]] = {}
    chapter_blocks = {
        chapter_id: {block["id"] for block in chapter["blocks"]}
        for chapter_id, chapter in chapters.items()
    }
    block_sentences = {
        block["id"]: {sentence["id"] for sentence in block["sentences"]}
        for chapter in chapters.values()
        for block in chapter["blocks"]
    }
    for item in plan["items"]:
        for occurrence in item["occurrences"]:
            if occurrence["chapter_id"] not in chapters:
                raise LinkedOutputError(f"Unknown chapter: {occurrence['chapter_id']}")
            if occurrence["block_id"] not in chapter_blocks[occurrence["chapter_id"]]:
                raise LinkedOutputError(f"Unknown block: {occurrence['block_id']}")
            if occurrence["sentence_id"] not in block_sentences[occurrence["block_id"]]:
                raise LinkedOutputError(
                    f"Unknown sentence: {occurrence['sentence_id']}"
                )
            occurrences_by_chapter.setdefault(occurrence["chapter_id"], []).append(
                (item, occurrence)
            )

    files: dict[str, bytes] = {}
    input_path = Path(input_path)
    for chapter_id, chapter in chapters.items():
        source_path = chapter_paths[chapter_id]
        root = ET.fromstring(_load_source(input_path, source_path))
        elements = _leaf_blocks(root)
        canonical_blocks = chapter["blocks"]
        if len(elements) != len(canonical_blocks):
            raise LinkedOutputError(f"Ambiguous block mapping: {chapter_id}")
        mapped = dict(zip((block["id"] for block in canonical_blocks), elements))
        before_text = {}
        ruby_before = {}
        block_maps = {}
        for block in canonical_blocks:
            text, refs, rubies = _visible_map(mapped[block["id"]])
            if text != block["text"]:
                raise LinkedOutputError(f"Canonical block mismatch: {block['id']}")
            before_text[block["id"]] = text
            block_maps[block["id"]] = (refs, rubies)
            for ruby in rubies:
                anchor = ruby.element.attrib.get("id")
                if anchor:
                    ruby_before[anchor] = _ruby_snapshot(ruby.element)
        parents = _parent_map(root)
        chapter_occurrences = sorted(
            occurrences_by_chapter.get(chapter_id, []),
            key=lambda value: (
                value[1]["block_id"],
                -value[1]["block_start"],
                value[1]["id"],
            ),
        )
        occupied: dict[str, list[tuple[int, int]]] = {}
        for item, occurrence in chapter_occurrences:
            block = blocks.get(occurrence["block_id"])
            sentence = sentences.get(occurrence["sentence_id"])
            if block is None or sentence is None:
                raise LinkedOutputError(f"Unknown canonical source: {occurrence['id']}")
            start = sentence["start"] + occurrence["sentence_start"]
            end = sentence["start"] + occurrence["sentence_end"]
            if (start, end) != (occurrence["block_start"], occurrence["block_end"]):
                raise LinkedOutputError(f"Block offset mismatch: {occurrence['id']}")
            occurrence_surface = block["text"][start:end]
            if (
                sentence["text"][occurrence["sentence_start"] : occurrence["sentence_end"]]
                != occurrence_surface
            ):
                raise LinkedOutputError(f"Occurrence text mismatch: {occurrence['id']}")
            spans = occupied.setdefault(block["id"], [])
            if any(
                start < other_end and other_start < end
                for other_start, other_end in spans
            ):
                raise LinkedOutputError(
                    f"Overlapping link occurrence: {occurrence['id']}"
                )
            spans.append((start, end))
            refs, rubies = block_maps[block["id"]]
            href = _relative_href(source_path, notes_path, item["note_anchor_id"])
            if occurrence.get("publisher_ruby_id"):
                ruby_record = next(
                    (
                        record
                        for record in block["publisher_ruby"]
                        if record["id"] == occurrence["publisher_ruby_id"]
                    ),
                    None,
                )
                ruby_ref = next(
                    (
                        value
                        for value in rubies
                        if value.start == start or (value.start >= start and value.end <= end)
                    ),
                    None,
                )
                if ruby_record is None or ruby_ref is None:
                    raise LinkedOutputError(
                        f"Ambiguous publisher ruby: {occurrence['id']}"
                    )
                if ruby_record.get("source_anchor") != ruby_ref.element.get("id"):
                    raise LinkedOutputError(
                        f"Publisher ruby anchor mismatch: {occurrence['id']}"
                    )
                if (ruby_ref.start, ruby_ref.end) == (start, end):
                    _wrap_ruby(
                        ruby_ref.element,
                        occurrence["source_anchor_id"],
                        href,
                        parents,
                    )
                elif ruby_ref.start == start and ruby_ref.end < end:
                    _wrap_ruby_with_tail(
                        ruby_ref.element,
                        end - ruby_ref.end,
                        occurrence["source_anchor_id"],
                        href,
                        parents,
                    )
                else:
                    raise LinkedOutputError(
                        f"Unsupported ruby span alignment: {occurrence['id']}"
                    )
                parents = _parent_map(root)
            else:
                if end > len(refs):
                    raise LinkedOutputError(f"XHTML range mismatch: {occurrence['id']}")
                first, last = refs[start], refs[end - 1]
                contained_rubies = [
                    v for v in rubies if v.start >= start and v.end <= end
                ]
                if contained_rubies:
                    ref_prefix = first if contained_rubies[0].start > start else None
                    okuri_len = end - contained_rubies[-1].end
                    _wrap_ruby_boundary(
                        [v.element for v in contained_rubies],
                        ref_prefix,
                        okuri_len,
                        occurrence["source_anchor_id"],
                        href,
                        parents,
                    )
                else:
                    raw = getattr(first.owner, first.attribute) or ""
                    if (
                        first.owner is not last.owner
                        or first.attribute != last.attribute
                        or raw[first.raw_index : last.raw_index + 1] != occurrence_surface
                    ):
                        raise LinkedOutputError(
                            f"Ambiguous text insertion: {occurrence['id']}"
                        )
                    _wrap_text(
                        first,
                        last,
                        occurrence["source_anchor_id"],
                        href,
                        parents,
                    )
                parents = _parent_map(root)
        for block in canonical_blocks:
            after, _, _ = _visible_map(mapped[block["id"]])
            if after != before_text[block["id"]]:
                raise LinkedOutputError(f"Visible source text changed: {block['id']}")
        for ruby in root.findall(".//" + X + "ruby"):
            anchor = ruby.attrib.get("id")
            if anchor in ruby_before and _ruby_snapshot(ruby) != ruby_before[anchor]:
                raise LinkedOutputError(f"Publisher ruby changed: {anchor}")
            if ruby.findall(".//" + X + "ruby"):
                raise LinkedOutputError(f"Nested ruby generated: {anchor}")
        files[source_path] = (
            ET.tostring(
                root, encoding="utf-8", xml_declaration=True, short_empty_elements=True
            )
            + b"\n"
        )
    files[notes_path] = _render_notes(plan, sentences, chapter_paths, notes_path)
    links = _validate_links(files)
    expected = sum(len(item["occurrences"]) for item in plan["items"])
    if len(links) != expected * 2:
        raise LinkedOutputError("Missing generated forward link or backlink")
    return LinkedOutput(notes_path=notes_path, files=files)


def split_study_notes_by_source_document(
    output: LinkedOutput,
    book: dict[str, Any],
    *,
    items_per_note_page: int = 25,
) -> LinkedOutput:
    """Partition one generated Study Notes document by canonical source XHTML.

    The retained ``study-notes.xhtml`` becomes a lightweight index. Source
    links target deterministic page-local note documents so ebook readers do
    not need to load the complete book-wide note layer for one lookup.
    """
    if output.notes_path not in output.files:
        raise LinkedOutputError("Missing Study Notes document")
    if items_per_note_page < 1:
        raise LinkedOutputError("Study-note page size must be positive")
    chapters, _, _ = _index_book(book)
    source_paths = [
        _safe_path(chapter["source_path"])
        for chapter in chapters.values()
        if _safe_path(chapter["source_path"]) in output.files
    ]
    note_root_bytes = output.files[output.notes_path]
    note_directory = posixpath.dirname(output.notes_path)
    files = dict(output.files)
    pages: list[tuple[str, str, list[str]]] = []
    master_root = ET.fromstring(note_root_bytes)
    master_list = master_root.find(".//" + X + "div[@class='study-notes__list']")
    if master_list is None:
        raise LinkedOutputError("Study Notes list is missing")
    master_sections = {
        section.get("id"): section
        for section in master_list
        if section.get("id")
    }
    page_skeleton = copy.deepcopy(master_root)
    skeleton_list = page_skeleton.find(
        ".//" + X + "div[@class='study-notes__list']"
    )
    if skeleton_list is None:
        raise LinkedOutputError("Study Notes page skeleton is missing")
    for child in list(skeleton_list):
        skeleton_list.remove(child)

    for source_path in source_paths:
        source_root = ET.fromstring(files[source_path])
        forward_links = [
            link
            for link in source_root.findall(".//" + X + "a")
            if "study-link" in link.attrib.get("class", "").split()
        ]
        if not forward_links:
            continue
        fragments = []
        for link in forward_links:
            split = urlsplit(link.attrib.get("href", ""))
            target = posixpath.normpath(
                posixpath.join(posixpath.dirname(source_path), split.path)
            )
            if target != output.notes_path or not split.fragment:
                raise LinkedOutputError("Unexpected Study Notes target")
            fragments.append(split.fragment)
        ordered_fragments = list(dict.fromkeys(fragments))
        chunks = [
            ordered_fragments[index : index + items_per_note_page]
            for index in range(0, len(ordered_fragments), items_per_note_page)
        ]
        for chunk in chunks:
            page_number = len(pages) + 1
            page_path = posixpath.join(
                note_directory, f"study-notes-page-{page_number:04d}.xhtml"
            )
            page_root = copy.deepcopy(page_skeleton)
            page_title = f"Study Notes — Page {page_number}"
            title = page_root.find(X + "head/" + X + "title")
            heading = page_root.find(".//" + X + "h1")
            if title is not None:
                title.text = page_title
            if heading is not None:
                heading.text = page_title
            section_parent = page_root.find(
                ".//" + X + "div[@class='study-notes__list']"
            )
            if section_parent is None:
                raise LinkedOutputError("Study Notes list is missing")
            allowed_fragments = set(chunk)
            retained_occurrences = 0
            for fragment in chunk:
                if fragment not in master_sections:
                    raise LinkedOutputError("Unknown Study Notes fragment")
                section = copy.deepcopy(master_sections[fragment])
                occurrence_container = section.find(
                    X + "div[@class='study-note__occurrences']"
                )
                if occurrence_container is None:
                    raise LinkedOutputError("Study note has no occurrence records")
                local_count = 0
                for record in list(occurrence_container):
                    backlink = record.find(
                        ".//" + X + "a[@class='study-note__backlink']"
                    )
                    if backlink is None:
                        occurrence_container.remove(record)
                        continue
                    split = urlsplit(backlink.attrib.get("href", ""))
                    target = posixpath.normpath(
                        posixpath.join(
                            posixpath.dirname(output.notes_path), split.path
                        )
                    )
                    if target != source_path:
                        occurrence_container.remove(record)
                        continue
                    local_count += 1
                if local_count == 0:
                    raise LinkedOutputError("Page-local study note has no backlink")
                retained_occurrences += local_count
                details = section.find(X + "dl[@class='study-note__details']")
                if details is not None:
                    children = list(details)
                    for index, child in enumerate(children[:-1]):
                        if (
                            child.tag == X + "dt"
                            and (child.text or "") == "Occurrences"
                        ):
                            if children[index + 1].tag == X + "dd":
                                children[index + 1].text = str(local_count)
                            break
                section_parent.append(section)
            chunk_links = [
                link
                for link in forward_links
                if urlsplit(link.attrib["href"]).fragment in allowed_fragments
            ]
            if retained_occurrences != len(chunk_links):
                raise LinkedOutputError("Page-local link/backlink count mismatch")
            for link in chunk_links:
                fragment = urlsplit(link.attrib["href"]).fragment
                link.set("href", _relative_href(source_path, page_path, fragment))
            files[page_path] = (
                ET.tostring(
                    page_root,
                    encoding="utf-8",
                    xml_declaration=True,
                    short_empty_elements=True,
                )
                + b"\n"
            )
            pages.append(
                (
                    source_path,
                    page_path,
                    [
                        urlsplit(link.attrib["href"]).fragment
                        for link in chunk_links
                    ],
                )
            )
        files[source_path] = (
            ET.tostring(
                source_root,
                encoding="utf-8",
                xml_declaration=True,
                short_empty_elements=True,
            )
            + b"\n"
        )

    index_root = copy.deepcopy(page_skeleton)
    index_list = index_root.find(".//" + X + "div[@class='study-notes__list']")
    if index_list is None:
        raise LinkedOutputError("Study Notes index list is missing")
    for child in list(index_list):
        index_list.remove(child)
    ordered = ET.SubElement(index_list, X + "ol", {"class": "study-notes__pages"})
    for number, (_, page_path, _) in enumerate(pages, 1):
        item = ET.SubElement(ordered, X + "li")
        anchor = ET.SubElement(
            item,
            X + "a",
            {"href": posixpath.relpath(page_path, note_directory)},
        )
        anchor.text = f"Page {number} study notes"
    files[output.notes_path] = (
        ET.tostring(
            index_root,
            encoding="utf-8",
            xml_declaration=True,
            short_empty_elements=True,
        )
        + b"\n"
    )
    generated_links = _validate_links(files)
    expected = sum(len(fragments) for _, _, fragments in pages)
    if len(generated_links) != expected * 2:
        raise LinkedOutputError("Partitioned Study Notes link count mismatch")
    return LinkedOutput(notes_path=output.notes_path, files=files)


def write_linked_output(output: LinkedOutput, output_dir: str | Path):
    root = Path(output_dir)
    for relative_path, data in sorted(output.files.items()):
        target = root / PurePosixPath(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LinkedOutputError(f"Expected JSON object: {path}")
    return value
