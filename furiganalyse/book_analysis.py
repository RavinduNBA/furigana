"""Deterministic, read-only extraction of canonical EPUB book content."""

from __future__ import annotations

import json
import posixpath
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Optional
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

SCHEMA_VERSION = 1
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
BLOCK_TAGS = {"blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "li", "p"}
HIDDEN_TAGS = {"rp", "rt", "script", "style"}


class BookAnalysisError(ValueError):
    """Raised when an EPUB cannot produce a trustworthy canonical model."""


@dataclass(frozen=True)
class PublisherRubySpan:
    id: str
    surface: str
    reading: Optional[str]
    source: str
    start: int
    end: int
    source_anchor: Optional[str]


@dataclass(frozen=True)
class BookBlock:
    id: str
    text: str
    source_anchor: Optional[str]
    publisher_ruby: list[PublisherRubySpan]


@dataclass(frozen=True)
class BookChapter:
    id: str
    spine_index: int
    source_path: str
    text: str
    blocks: list[BookBlock]


@dataclass(frozen=True)
class BookAnalysis:
    schema_version: int
    book_id: str
    package_path: str
    chapters: list[BookChapter]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_archive_path(path: str) -> str:
    normalized = posixpath.normpath(unquote(urlsplit(path).path))
    candidate = PurePosixPath(normalized)
    if (
        not normalized
        or normalized == "."
        or candidate.is_absolute()
        or ".." in candidate.parts
        or "\\" in normalized
    ):
        raise BookAnalysisError(f"Unsafe EPUB archive path: {path!r}")
    return candidate.as_posix()


def _resolve_archive_path(source_path: str, href: str) -> str:
    href_path = unquote(urlsplit(href).path)
    combined = posixpath.join(posixpath.dirname(source_path), href_path)
    return _safe_archive_path(combined)


class _TextBuilder:
    def __init__(self):
        self.characters: list[str] = []

    def append(self, value: Optional[str]):
        for character in value or "":
            if character.isspace():
                if self.characters and self.characters[-1] != " ":
                    self.characters.append(" ")
            else:
                self.characters.append(character)

    @property
    def position(self) -> int:
        return len(self.characters)

    def finish(self) -> str:
        if self.characters and self.characters[-1] == " ":
            self.characters.pop()
        return "".join(self.characters)


def _normalized_text(values) -> str:
    builder = _TextBuilder()
    for value in values:
        builder.append(value)
    return builder.finish()


def _ruby_reading(ruby: ET.Element) -> Optional[str]:
    readings = []
    for descendant in ruby.iter():
        if local_name(descendant.tag) == "rt":
            readings.extend(descendant.itertext())
    reading = _normalized_text(readings)
    return reading or None


def _append_visible(
    element: ET.Element,
    builder: _TextBuilder,
    ruby_records: list[dict],
):
    element_name = local_name(element.tag)
    if element_name in HIDDEN_TAGS:
        return

    ruby_start = builder.position if element_name == "ruby" else None
    builder.append(element.text)
    for child in element:
        _append_visible(child, builder, ruby_records)
        builder.append(child.tail)

    if ruby_start is not None:
        ruby_records.append(
            {
                "start": ruby_start,
                "end": builder.position,
                "reading": _ruby_reading(element),
                "source_anchor": element.attrib.get("id"),
            }
        )


def _leaf_blocks(root: ET.Element):
    for element in root.iter():
        if local_name(element.tag) not in BLOCK_TAGS:
            continue
        nested_blocks = any(
            descendant is not element and local_name(descendant.tag) in BLOCK_TAGS
            for descendant in element.iter()
        )
        if not nested_blocks:
            yield element


def _extract_blocks(root: ET.Element, chapter_id: str) -> list[BookBlock]:
    blocks = []
    for element in _leaf_blocks(root):
        builder = _TextBuilder()
        ruby_records: list[dict] = []
        _append_visible(element, builder, ruby_records)
        text = builder.finish()
        if not text:
            continue

        block_id = f"{chapter_id}-b-{len(blocks) + 1:04d}"
        ruby_spans = []
        for ruby_index, record in enumerate(ruby_records, start=1):
            start = record["start"]
            end = min(record["end"], len(text))
            ruby_spans.append(
                PublisherRubySpan(
                    id=f"{block_id}-r-{ruby_index:04d}",
                    surface=text[start:end],
                    reading=record["reading"],
                    source="publisher",
                    start=start,
                    end=end,
                    source_anchor=record["source_anchor"],
                )
            )
        blocks.append(
            BookBlock(
                id=block_id,
                text=text,
                source_anchor=element.attrib.get("id"),
                publisher_ruby=ruby_spans,
            )
        )
    return blocks


def _book_identifier(package: ET.Element) -> str:
    identifiers = package.findall(f".//{{{DC_NS}}}identifier")
    unique_identifier = package.attrib.get("unique-identifier")
    if unique_identifier:
        for identifier in identifiers:
            if identifier.attrib.get("id") == unique_identifier and identifier.text:
                return identifier.text.strip()
    for identifier in identifiers:
        if identifier.text and identifier.text.strip():
            return identifier.text.strip()
    raise BookAnalysisError("EPUB package has no usable dc:identifier")


def extract_book(epub_path: str | Path) -> BookAnalysis:
    """Extract spine-ordered canonical chapter and block data from an EPUB."""
    with zipfile.ZipFile(epub_path) as archive:
        names = set(archive.namelist())
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(f".//{{{CONTAINER_NS}}}rootfile")
        if rootfile is None or not rootfile.attrib.get("full-path"):
            raise BookAnalysisError("EPUB container has no package rootfile")

        package_path = _safe_archive_path(rootfile.attrib["full-path"])
        if package_path not in names:
            raise BookAnalysisError(f"EPUB package is missing: {package_path}")
        package = ET.fromstring(archive.read(package_path))

        manifest = {}
        for item in package.findall(f".//{{{OPF_NS}}}manifest/{{{OPF_NS}}}item"):
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            if item_id and href:
                manifest[item_id] = {
                    "path": _resolve_archive_path(package_path, href),
                    "media_type": item.attrib.get("media-type"),
                }

        chapters = []
        spine = package.find(f".//{{{OPF_NS}}}spine")
        if spine is None:
            raise BookAnalysisError("EPUB package has no spine")
        for spine_index, itemref in enumerate(spine.findall(f"{{{OPF_NS}}}itemref")):
            idref = itemref.attrib.get("idref")
            item = manifest.get(idref)
            if item is None:
                raise BookAnalysisError(f"Spine references unknown manifest item: {idref}")
            if item["media_type"] != "application/xhtml+xml":
                continue
            source_path = item["path"]
            if source_path not in names:
                raise BookAnalysisError(f"Spine document is missing: {source_path}")

            chapter_id = f"ch-{len(chapters) + 1:04d}"
            root = ET.fromstring(archive.read(source_path))
            blocks = _extract_blocks(root, chapter_id)
            chapters.append(
                BookChapter(
                    id=chapter_id,
                    spine_index=spine_index,
                    source_path=source_path,
                    text="\n".join(block.text for block in blocks),
                    blocks=blocks,
                )
            )

    return BookAnalysis(
        schema_version=SCHEMA_VERSION,
        book_id=_book_identifier(package),
        package_path=package_path,
        chapters=chapters,
    )


def serialize_book(book: BookAnalysis) -> str:
    return json.dumps(asdict(book), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_book_json(book: BookAnalysis, output_path: str | Path):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialize_book(book), encoding="utf-8")
