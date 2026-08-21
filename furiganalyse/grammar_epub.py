"""Deterministic EPUB packaging for approved Phase 7 linked grammar XHTML."""

from __future__ import annotations

import hashlib
import posixpath
import re
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from furiganalyse.epub_packaging import FIXED_TIME, write_deterministic_epub

CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
XHTML = "http://www.w3.org/1999/xhtml"
EPUB = "http://www.idpf.org/2007/ops"
X = f"{{{XHTML}}}"
PACKAGE_PATH = "EPUB/package.opf"
NAV_PATH = "EPUB/nav.xhtml"
TEXT_PATHS = (
    "EPUB/text/grammar-01.xhtml",
    "EPUB/text/grammar-02.xhtml",
    "EPUB/text/study-notes.xhtml",
)
GRAMMAR_NOTES_PATH = "EPUB/text/grammar-notes.xhtml"
STUDY_NOTES_ID = "furiganalyse-study-notes"
GRAMMAR_NOTES_ID = "furiganalyse-grammar-notes"
BASE_MEMBERS = {
    "mimetype",
    "META-INF/container.xml",
    PACKAGE_PATH,
    NAV_PATH,
    *TEXT_PATHS,
}
GRAMMAR_MEMBERS = BASE_MEMBERS | {GRAMMAR_NOTES_PATH}
SPINE_BASE = ["grammar-ch1", "grammar-ch2", STUDY_NOTES_ID]
SPINE_GRAMMAR = [*SPINE_BASE, GRAMMAR_NOTES_ID]
NAV_BASE = ["Synthetic Grammar Chapter 1", "Synthetic Grammar Chapter 2", "Study Notes"]
NAV_GRAMMAR = [*NAV_BASE, "Grammar Study Notes"]
EXPECTED_NOTE_ANCHORS = [f"grammar-note-{number:04d}" for number in range(1, 6)]
EXPECTED_STUDY_ANCHORS = [f"src-study-item-{number:04d}-occ-0001" for number in range(1, 6)]
EXPECTED_GRAMMAR_LINKS = {
    "grammar-src-grammar-occurrence-0002": "grammar-notes.xhtml#grammar-note-0002",
    "grammar-src-grammar-occurrence-0005": "grammar-notes.xhtml#grammar-note-0001",
    "grammar-src-grammar-occurrence-0008": "grammar-notes.xhtml#grammar-note-0005",
}
EXPECTED_DISPOSITIONS = [
    ("grammar-plan-occurrence-0001", "grammar-note-reference-only", False),
    ("grammar-plan-occurrence-0005", "grammar-link", True),
    ("grammar-plan-occurrence-0006", "publisher-ruby-preserved", False),
    ("grammar-plan-occurrence-0002", "separate-nonoverlapping-links", True),
    ("grammar-plan-occurrence-0003", "rejected-ambiguous-overlap", False),
    ("grammar-plan-occurrence-0004", "grammar-note-reference-only", False),
    ("grammar-plan-occurrence-0007", "grammar-link", True),
]
PACKAGE_IDENTIFIER = "urn:uuid:furiganalyse-phase-7-synthetic"
PACKAGE_TITLE = "Furiganalyse Phase 7 Synthetic Grammar Fixture"
PACKAGE_MODIFIED = "2026-08-20T00:00:00Z"
SAFE_DIAGNOSTICS = {
    "disabled",
    "stale-input",
    "invalid-input",
    "corrupt-input",
    "ambiguous-input",
    "unsafe-input",
}
ET.register_namespace("", OPF)
ET.register_namespace("dc", DC)
ET.register_namespace("", XHTML)
ET.register_namespace("epub", EPUB)


class GrammarEpubError(ValueError):
    """A safe deterministic grammar-EPUB validation failure."""

    def __init__(self, reason: str):
        if reason not in SAFE_DIAGNOSTICS - {"disabled"}:
            reason = "invalid-input"
        self.reason = reason
        super().__init__(reason)


def _safe_path(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or name != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in name
        or re.match(r"^[A-Za-z]:", name)
    ):
        raise GrammarEpubError("unsafe-input")
    return name


def _xml(element: ET.Element) -> bytes:
    return ET.tostring(element, encoding="utf-8", xml_declaration=True) + b"\n"


def _read_xhtml(directory: Path, names: tuple[str, ...]) -> dict[str, bytes]:
    if not directory.is_dir():
        raise GrammarEpubError("invalid-input")
    actual = set()
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise GrammarEpubError("unsafe-input")
        if path.is_file():
            relative = _safe_path(path.relative_to(directory).as_posix())
            actual.add(relative)
    if actual != set(names):
        raise GrammarEpubError("invalid-input")
    result = {}
    for name in names:
        path = directory / PurePosixPath(name)
        if not path.is_file():
            raise GrammarEpubError("invalid-input")
        result[name] = path.read_bytes()
    return result


def _container_bytes() -> bytes:
    ET.register_namespace("", CONTAINER)
    root = ET.Element(f"{{{CONTAINER}}}container", {"version": "1.0"})
    rootfiles = ET.SubElement(root, f"{{{CONTAINER}}}rootfiles")
    ET.SubElement(
        rootfiles,
        f"{{{CONTAINER}}}rootfile",
        {
            "full-path": PACKAGE_PATH,
            "media-type": "application/oebps-package+xml",
        },
    )
    return _xml(root)


def _package_bytes(grammar: bool) -> bytes:
    ET.register_namespace("", OPF)
    ET.register_namespace("dc", DC)
    package = ET.Element(
        f"{{{OPF}}}package",
        {
            "version": "3.0",
            "unique-identifier": "book-id",
            "{http://www.w3.org/XML/1998/namespace}lang": "ja",
        },
    )
    metadata = ET.SubElement(package, f"{{{OPF}}}metadata")
    ET.SubElement(metadata, f"{{{DC}}}identifier", {"id": "book-id"}).text = PACKAGE_IDENTIFIER
    ET.SubElement(metadata, f"{{{DC}}}title").text = PACKAGE_TITLE
    ET.SubElement(metadata, f"{{{DC}}}language").text = "ja"
    ET.SubElement(metadata, f"{{{OPF}}}meta", {"property": "dcterms:modified"}).text = PACKAGE_MODIFIED
    manifest = ET.SubElement(package, f"{{{OPF}}}manifest")
    entries = [
        ("nav", "nav.xhtml", "application/xhtml+xml", "nav"),
        ("grammar-ch1", "text/grammar-01.xhtml", "application/xhtml+xml", None),
        ("grammar-ch2", "text/grammar-02.xhtml", "application/xhtml+xml", None),
        (STUDY_NOTES_ID, "text/study-notes.xhtml", "application/xhtml+xml", None),
    ]
    if grammar:
        entries.append((GRAMMAR_NOTES_ID, "text/grammar-notes.xhtml", "application/xhtml+xml", None))
    for item_id, href, media_type, properties in entries:
        attributes = {"id": item_id, "href": href, "media-type": media_type}
        if properties:
            attributes["properties"] = properties
        ET.SubElement(manifest, f"{{{OPF}}}item", attributes)
    spine = ET.SubElement(package, f"{{{OPF}}}spine")
    for item_id in SPINE_GRAMMAR if grammar else SPINE_BASE:
        ET.SubElement(spine, f"{{{OPF}}}itemref", {"idref": item_id})
    return _xml(package)


def _nav_bytes(grammar: bool) -> bytes:
    ET.register_namespace("", XHTML)
    ET.register_namespace("epub", EPUB)
    html = ET.Element(X + "html", {"lang": "ja", "{http://www.w3.org/XML/1998/namespace}lang": "ja"})
    head = ET.SubElement(html, X + "head")
    ET.SubElement(head, X + "title").text = "目次"
    body = ET.SubElement(html, X + "body")
    nav = ET.SubElement(body, X + "nav", {f"{{{EPUB}}}type": "toc", "id": "toc"})
    ET.SubElement(nav, X + "h1").text = "目次"
    ordered = ET.SubElement(nav, X + "ol")
    entries = [
        ("Synthetic Grammar Chapter 1", "text/grammar-01.xhtml"),
        ("Synthetic Grammar Chapter 2", "text/grammar-02.xhtml"),
        ("Study Notes", "text/study-notes.xhtml"),
    ]
    if grammar:
        entries.append(("Grammar Study Notes", "text/grammar-notes.xhtml"))
    for label, href in entries:
        item = ET.SubElement(ordered, X + "li")
        ET.SubElement(item, X + "a", {"href": href}).text = label
    return _xml(html)


def build_vocabulary_fixture_files(source_dir) -> dict[str, bytes]:
    """Build the seven-member legal vocabulary-only Phase 7 package skeleton."""
    files = {
        "mimetype": b"application/epub+zip",
        "META-INF/container.xml": _container_bytes(),
        PACKAGE_PATH: _package_bytes(False),
        NAV_PATH: _nav_bytes(False),
    }
    files.update(_read_xhtml(Path(source_dir), TEXT_PATHS))
    validate_package_files(files, grammar=False)
    return files


def build_vocabulary_fixture(source_dir, output_path) -> dict[str, bytes]:
    files = build_vocabulary_fixture_files(source_dir)
    write_deterministic_epub(files, output_path)
    return files


def _archive_files(path) -> tuple[dict[str, bytes], list[zipfile.ZipInfo]]:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [_safe_path(info.filename) for info in infos]
            if len(names) != len(set(names)):
                raise GrammarEpubError("invalid-input")
            files = {name: archive.read(name) for name in names}
    except GrammarEpubError:
        raise
    except (OSError, KeyError, zipfile.BadZipFile, RuntimeError) as error:
        raise GrammarEpubError("corrupt-input") from error
    return files, infos


def validate_archive(path, *, grammar: bool) -> dict:
    files, infos = _archive_files(path)
    expected = GRAMMAR_MEMBERS if grammar else BASE_MEMBERS
    if set(files) != expected:
        raise GrammarEpubError("invalid-input")
    expected_order = ["mimetype", *sorted(expected - {"mimetype"})]
    if [info.filename for info in infos] != expected_order:
        raise GrammarEpubError("invalid-input")
    for index, info in enumerate(infos):
        if info.date_time != FIXED_TIME or info.create_system != 3 or info.external_attr != 0o100644 << 16:
            raise GrammarEpubError("invalid-input")
        expected_compression = zipfile.ZIP_STORED if index == 0 else zipfile.ZIP_DEFLATED
        if info.compress_type != expected_compression or info.extra or info.comment or info.flag_bits & 0x1:
            raise GrammarEpubError("invalid-input")
    report = validate_package_files(files, grammar=grammar)
    report.update(
        {
            "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "archive_members": [info.filename for info in infos],
            "compression": ["stored" if info.compress_type == zipfile.ZIP_STORED else "deflated" for info in infos],
            "timestamps": [list(info.date_time) for info in infos],
            "permissions": [oct(info.external_attr >> 16) for info in infos],
        }
    )
    return report


def _manifest_and_spine(package: ET.Element):
    manifest = package.find(f"{{{OPF}}}manifest")
    spine = package.find(f"{{{OPF}}}spine")
    if manifest is None or spine is None:
        raise GrammarEpubError("invalid-input")
    return manifest, spine


def _resolve(source: str, target: str) -> tuple[str, str]:
    split = urlsplit(target)
    target_path = PurePosixPath(split.path)
    if (
        split.scheme
        or split.netloc
        or split.path.startswith("/")
        or "\\" in split.path
        or ".." in target_path.parts
        or re.match(r"^[A-Za-z]:", split.path)
        or not split.path and not split.fragment
    ):
        raise GrammarEpubError("unsafe-input")
    if split.path:
        _safe_path(posixpath.normpath(posixpath.join(posixpath.dirname(source), split.path)))
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), split.path)) if split.path else source
    return resolved, split.fragment


def _snapshot(element: ET.Element) -> bytes:
    clone = ET.fromstring(ET.tostring(element, encoding="utf-8"))
    clone.tail = None
    return ET.tostring(clone, encoding="utf-8")


def _visible(element: ET.Element) -> str:
    return "".join(element.itertext())


def _validate_linked_replacement(base: dict[str, bytes], linked: dict[str, bytes]):
    if linked["EPUB/text/study-notes.xhtml"] != base["EPUB/text/study-notes.xhtml"]:
        raise GrammarEpubError("stale-input")
    for name in TEXT_PATHS[:2]:
        try:
            before = ET.fromstring(base[name])
            after = ET.fromstring(linked[name])
        except ET.ParseError as error:
            raise GrammarEpubError("corrupt-input") from error
        if _visible(before) != _visible(after):
            raise GrammarEpubError("ambiguous-input")
        for expression in ("a[@class='study-link']", "em", "ruby"):
            old = [_snapshot(x) for x in before.findall(f".//{X}{expression}")]
            new = [_snapshot(x) for x in after.findall(f".//{X}{expression}")]
            if old != new:
                raise GrammarEpubError("stale-input")


def package_grammar_epub(input_epub, linked_dir) -> dict[str, bytes]:
    validate_archive(input_epub, grammar=False)
    base, _ = _archive_files(input_epub)
    validate_package_files(base, grammar=False)
    linked = _read_xhtml(Path(linked_dir), (*TEXT_PATHS, GRAMMAR_NOTES_PATH))
    _validate_linked_replacement(base, linked)
    files = dict(base)
    files.update(linked)
    files[PACKAGE_PATH] = _package_bytes(True)
    files[NAV_PATH] = _nav_bytes(True)
    validate_package_files(files, grammar=True)
    return files


def build_grammar_epub(input_epub, linked_dir, output_path) -> dict[str, bytes]:
    files = package_grammar_epub(input_epub, linked_dir)
    write_deterministic_epub(files, output_path)
    return files


def validate_package_files(files: dict[str, bytes], *, grammar: bool) -> dict:
    expected = GRAMMAR_MEMBERS if grammar else BASE_MEMBERS
    if set(files) != expected or files.get("mimetype") != b"application/epub+zip":
        raise GrammarEpubError("invalid-input")
    try:
        container = ET.fromstring(files["META-INF/container.xml"])
        rootfiles = container.findall(f".//{{{CONTAINER}}}rootfile")
        if (
            len(rootfiles) != 1
            or rootfiles[0].get("full-path") != PACKAGE_PATH
            or rootfiles[0].get("media-type") != "application/oebps-package+xml"
        ):
            raise GrammarEpubError("invalid-input")
        package = ET.fromstring(files[PACKAGE_PATH])
        nav = ET.fromstring(files[NAV_PATH])
    except ET.ParseError as error:
        raise GrammarEpubError("corrupt-input") from error
    if (
        package.tag != f"{{{OPF}}}package"
        or package.get("version") != "3.0"
        or package.get("unique-identifier") != "book-id"
        or package.get("{http://www.w3.org/XML/1998/namespace}lang") != "ja"
    ):
        raise GrammarEpubError("invalid-input")
    metadata = package.find(f"{{{OPF}}}metadata")
    if metadata is None:
        raise GrammarEpubError("invalid-input")
    identifier = metadata.find(f"{{{DC}}}identifier")
    title = metadata.find(f"{{{DC}}}title")
    language = metadata.find(f"{{{DC}}}language")
    modified = next((node for node in metadata.findall(f"{{{OPF}}}meta") if node.get("property") == "dcterms:modified"), None)
    if (
        identifier is None
        or identifier.get("id") != "book-id"
        or identifier.text != PACKAGE_IDENTIFIER
        or title is None
        or title.text != PACKAGE_TITLE
        or language is None
        or language.text != "ja"
        or modified is None
        or modified.text != PACKAGE_MODIFIED
    ):
        raise GrammarEpubError("invalid-input")
    manifest, spine = _manifest_and_spine(package)
    items = manifest.findall(f"{{{OPF}}}item")
    item_ids = [item.get("id") for item in items]
    hrefs = [item.get("href") for item in items]
    if len(item_ids) != len(set(item_ids)) or len(hrefs) != len(set(hrefs)):
        raise GrammarEpubError("invalid-input")
    expected_manifest = {
        "nav": ("nav.xhtml", "application/xhtml+xml", "nav"),
        "grammar-ch1": ("text/grammar-01.xhtml", "application/xhtml+xml", None),
        "grammar-ch2": ("text/grammar-02.xhtml", "application/xhtml+xml", None),
        STUDY_NOTES_ID: ("text/study-notes.xhtml", "application/xhtml+xml", None),
    }
    if grammar:
        expected_manifest[GRAMMAR_NOTES_ID] = ("text/grammar-notes.xhtml", "application/xhtml+xml", None)
    actual_manifest = {item.get("id"): (item.get("href"), item.get("media-type"), item.get("properties")) for item in items}
    if actual_manifest != expected_manifest:
        raise GrammarEpubError("invalid-input")
    for href, _, _ in actual_manifest.values():
        target, _ = _resolve(PACKAGE_PATH, href)
        if target not in files:
            raise GrammarEpubError("invalid-input")
    idrefs = [item.get("idref") for item in spine.findall(f"{{{OPF}}}itemref")]
    if idrefs != (SPINE_GRAMMAR if grammar else SPINE_BASE):
        raise GrammarEpubError("invalid-input")
    navs = [node for node in nav.findall(f".//{X}nav") if node.get(f"{{{EPUB}}}type") == "toc"]
    if len(navs) != 1:
        raise GrammarEpubError("invalid-input")
    nav_links = navs[0].findall(f".//{X}a")
    labels = [(link.text or "").strip() for link in nav_links]
    if labels != (NAV_GRAMMAR if grammar else NAV_BASE):
        raise GrammarEpubError("invalid-input")
    xhtml_names = [name for name in sorted(files) if name.endswith(".xhtml")]
    ids_by_document = {}
    roots = {}
    for name in xhtml_names:
        try:
            root = ET.fromstring(files[name])
        except ET.ParseError as error:
            raise GrammarEpubError("corrupt-input") from error
        if root.tag != X + "html":
            raise GrammarEpubError("invalid-input")
        values = [node.get("id") for node in root.iter() if node.get("id")]
        if len(values) != len(set(values)):
            raise GrammarEpubError("invalid-input")
        ids_by_document[name] = set(values)
        roots[name] = root
    for name, root in roots.items():
        for node in root.iter():
            local = node.tag.rsplit("}", 1)[-1]
            if local in {"script", "iframe", "object", "embed"} or any(key.lower().startswith("on") for key in node.attrib):
                raise GrammarEpubError("unsafe-input")
            if local in {"a", "ruby"} and any(child.tag == node.tag for child in node.iter() if child is not node):
                raise GrammarEpubError("invalid-input")
            for attribute in ("href", "src"):
                href = node.get(attribute)
                if not href:
                    continue
                target, fragment = _resolve(name, href)
                if target not in files or fragment and fragment not in ids_by_document.get(target, set()):
                    raise GrammarEpubError("invalid-input")
    for link in nav_links:
        target, fragment = _resolve(NAV_PATH, link.get("href", ""))
        if target not in files or fragment:
            raise GrammarEpubError("invalid-input")
    grammar_notes = roots.get(GRAMMAR_NOTES_PATH)
    forwards = sum(len(root.findall(f".//{X}a[@class='grammar-link']")) for root in roots.values())
    backlinks = len(grammar_notes.findall(f".//{X}a[@class='grammar-study-note__backlink']")) if grammar_notes is not None else 0
    contexts = len(grammar_notes.findall(f".//{X}blockquote[@class='grammar-study-note__context']")) if grammar_notes is not None else 0
    notes = len(grammar_notes.findall(f".//{X}section[@class='grammar-study-note']")) if grammar_notes is not None else 0
    study_links = sum(len(root.findall(f".//{X}a[@class='study-link']")) for root in roots.values())
    expected_counts = (3, 3, 7, 5, 5) if grammar else (0, 0, 0, 0, 5)
    if (forwards, backlinks, contexts, notes, study_links) != expected_counts:
        raise GrammarEpubError("invalid-input")
    if grammar:
        note_sections = grammar_notes.findall(f".//{X}section[@class='grammar-study-note']")
        if [section.get("id") for section in note_sections] != EXPECTED_NOTE_ANCHORS:
            raise GrammarEpubError("invalid-input")
        records = grammar_notes.findall(f".//{X}div[@class='grammar-study-note__occurrence']")
        actual_dispositions = [
            (
                record.get("data-occurrence-id"),
                record.get("data-disposition"),
                record.find(f".//{X}a[@class='grammar-study-note__backlink']") is not None,
            )
            for record in records
        ]
        if actual_dispositions != EXPECTED_DISPOSITIONS:
            raise GrammarEpubError("invalid-input")
        source_links = {
            link.get("id"): link.get("href")
            for root in roots.values()
            for link in root.findall(f".//{X}a[@class='grammar-link']")
        }
        if source_links != EXPECTED_GRAMMAR_LINKS:
            raise GrammarEpubError("invalid-input")
        study_ids = sorted(
            link.get("id")
            for root in roots.values()
            for link in root.findall(f".//{X}a[@class='study-link']")
        )
        if study_ids != EXPECTED_STUDY_ANCHORS:
            raise GrammarEpubError("invalid-input")
        rubies = roots["EPUB/text/grammar-01.xhtml"].findall(f".//{X}ruby")
        if (
            len(rubies) != 1
            or rubies[0].get("id") != "publisher-ruby-1-8-1"
            or (rubies[0].text or "") != "表舞台"
            or rubies[0].find(X + "rt") is None
            or rubies[0].find(X + "rt").text != "おもてぶたい"
        ):
            raise GrammarEpubError("invalid-input")
        for root in roots.values():
            parents = {child: parent for parent in root.iter() for child in parent}
            for link in root.findall(f".//{X}a[@class='grammar-link']"):
                parent = parents.get(link)
                while parent is not None:
                    if parent.tag in {X + "a", X + "ruby", X + "rb", X + "rt", X + "rp"}:
                        raise GrammarEpubError("invalid-input")
                    parent = parents.get(parent)
    blob = b"\n".join(files[name] for name in sorted(files)).lower()
    for banned in (b"<script", b"cache-key", b"context-hash", b"provider-id", b"model-id", b"prompt-version"):
        if banned in blob:
            raise GrammarEpubError("unsafe-input")
    return {
        "schema_version": 1,
        "container_path": PACKAGE_PATH,
        "package_metadata": {
            "identifier": identifier.text,
            "title": title.text,
            "language": language.text,
            "modified": modified.text,
        },
        "member_count": len(files),
        "manifest": [
            {"id": item_id, "href": values[0], "media_type": values[1], "properties": values[2]}
            for item_id, values in actual_manifest.items()
        ],
        "spine": idrefs,
        "navigation": labels,
        "navigation_hrefs": [link.get("href") for link in nav_links],
        "grammar_notes": notes,
        "grammar_contexts": contexts,
        "grammar_forward_links": forwards,
        "grammar_backlinks": backlinks,
        "study_links": study_links,
    }
