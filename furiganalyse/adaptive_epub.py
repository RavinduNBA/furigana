"""Deterministic packaging for validated Phase 8 adaptive XHTML."""

from __future__ import annotations

import copy
import hashlib
import json
import posixpath
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from furiganalyse.adaptive_rendering import directory_hash
from furiganalyse.assistance_density import stable_hash
from furiganalyse.epub_packaging import FIXED_TIME, write_deterministic_epub
from furiganalyse.grammar_epub import (
    GrammarEpubError,
    validate_archive as validate_phase7_archive,
)

CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
XHTML = "http://www.w3.org/1999/xhtml"
EPUB = "http://www.idpf.org/2007/ops"
XML = "http://www.w3.org/XML/1998/namespace"
X = f"{{{XHTML}}}"
PACKAGE_PATH = "EPUB/package.opf"
NAV_PATH = "EPUB/nav.xhtml"
TEXT_PATHS = (
    "EPUB/text/grammar-01.xhtml",
    "EPUB/text/grammar-02.xhtml",
    "EPUB/text/grammar-notes.xhtml",
    "EPUB/text/study-notes.xhtml",
)
MEMBERS = {
    "mimetype", "META-INF/container.xml", PACKAGE_PATH, NAV_PATH, *TEXT_PATHS,
}
MEMBER_ORDER = ["mimetype", *sorted(MEMBERS - {"mimetype"})]
SPINE = [
    "grammar-ch1", "grammar-ch2", "furiganalyse-study-notes",
    "furiganalyse-grammar-notes",
]
NAVIGATION = [
    ("Synthetic Grammar Chapter 1", "text/grammar-01.xhtml"),
    ("Synthetic Grammar Chapter 2", "text/grammar-02.xhtml"),
    ("Study Notes", "text/study-notes.xhtml"),
    ("Grammar Study Notes", "text/grammar-notes.xhtml"),
]
EXPECTED_IDENTIFIER = "urn:uuid:furiganalyse-phase-8-synthetic-adaptive"
EXPECTED_TITLE = "Furiganalyse Phase 8 Synthetic Adaptive Assistance Fixture"
EXPECTED_MODIFIED = "2026-08-22T00:00:00Z"
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
SAFE_REASONS = {
    "disabled", "source-epub-hash-mismatch", "rendering-report-mismatch",
    "adaptive-directory-hash-mismatch", "adaptive-document-hash-mismatch",
    "unsupported-schema-or-field", "invalid-package-metadata",
    "unsafe-archive-path", "duplicate-archive-path", "missing-archive-member",
    "invalid-mimetype", "invalid-container", "invalid-manifest", "invalid-spine",
    "invalid-navigation", "broken-fragment", "suppressed-content-restoration",
    "missing-presented-reading", "missing-approved-meaning", "publisher-ruby-mismatch",
    "grammar-link-mismatch", "study-link-mismatch", "invalid-configuration",
    "corrupt-input", "unsafe-hidden-content",
}
ET.register_namespace("", OPF)
ET.register_namespace("dc", DC)
ET.register_namespace("", XHTML)
ET.register_namespace("epub", EPUB)


class AdaptiveEpubError(ValueError):
    """A deterministic adaptive-EPUB validation failure."""

    def __init__(self, reason: str):
        self.reason = reason if reason in SAFE_REASONS else "invalid-configuration"
        super().__init__(self.reason)


def _without_hash(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "hash"}


def _check_hash(value: dict[str, Any], reason: str) -> None:
    if value.get("hash") != stable_hash(_without_hash(value)):
        raise AdaptiveEpubError(reason)


def _add_hash(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result["hash"] = stable_hash(result)
    return result


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdaptiveEpubError("corrupt-input")
    return value


def serialize_report(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _safe_path(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name or path.is_absolute() or name != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in name or re.match(r"^[A-Za-z]:", name)
    ):
        raise AdaptiveEpubError("unsafe-archive-path")
    return name


def _read_archive(path: str | Path) -> tuple[dict[str, bytes], list[zipfile.ZipInfo]]:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [_safe_path(info.filename) for info in infos]
            if len(names) != len(set(names)):
                raise AdaptiveEpubError("duplicate-archive-path")
            files = {name: archive.read(name) for name in names}
    except AdaptiveEpubError:
        raise
    except (OSError, KeyError, RuntimeError, zipfile.BadZipFile) as error:
        raise AdaptiveEpubError("corrupt-input") from error
    return files, infos


def _read_adaptive_xhtml(directory: str | Path) -> dict[str, bytes]:
    root = Path(directory)
    if not root.is_dir():
        raise AdaptiveEpubError("missing-archive-member")
    files: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise AdaptiveEpubError("unsafe-archive-path")
        if path.is_file():
            relative = _safe_path(path.relative_to(root).as_posix())
            if relative in files:
                raise AdaptiveEpubError("duplicate-archive-path")
            files[relative] = path.read_bytes()
    if set(files) != set(TEXT_PATHS):
        extra = set(files) - set(TEXT_PATHS)
        if any("\\" in value or value.startswith("/") for value in extra):
            raise AdaptiveEpubError("unsafe-archive-path")
        raise AdaptiveEpubError("missing-archive-member")
    return files


def build_package_metadata(
    base_epub: str | Path,
    rendering_report: dict[str, Any],
    adaptive_dir: str | Path,
) -> dict[str, Any]:
    xhtml = _read_adaptive_xhtml(adaptive_dir)
    value = {
        "schema_version": 1,
        "id": "phase8-adaptive-epub-metadata-v1",
        "book_id": "urn:uuid:furiganalyse-phase-7-synthetic",
        "identifier": EXPECTED_IDENTIFIER,
        "title": EXPECTED_TITLE,
        "language": "ja",
        "modified": EXPECTED_MODIFIED,
        "fixture_notice": "Synthetic adaptive-assistance packaging mechanics only.",
        "provenance": "local-synthetic-adaptive-epub-fixture",
        "base_epub_sha256": hashlib.sha256(Path(base_epub).read_bytes()).hexdigest(),
        "adaptive_rendering_report_hash": rendering_report.get("hash"),
        "adaptive_xhtml_directory_hash": directory_hash(xhtml),
    }
    return _add_hash(value)


def validate_metadata(
    metadata: dict[str, Any],
    book_id: str,
    base_epub: str | Path,
    rendering_report: dict[str, Any],
    xhtml: dict[str, bytes],
) -> None:
    expected_fields = {
        "schema_version", "id", "book_id", "identifier", "title", "language",
        "modified", "fixture_notice", "provenance", "base_epub_sha256",
        "adaptive_rendering_report_hash", "adaptive_xhtml_directory_hash", "hash",
    }
    if set(metadata) != expected_fields or metadata.get("schema_version") != 1:
        raise AdaptiveEpubError("unsupported-schema-or-field")
    _check_hash(metadata, "invalid-package-metadata")
    if (
        metadata.get("id") != "phase8-adaptive-epub-metadata-v1"
        or metadata.get("book_id") != book_id
        or metadata.get("identifier") != EXPECTED_IDENTIFIER
        or metadata.get("title") != EXPECTED_TITLE
        or metadata.get("language") != "ja"
        or metadata.get("modified") != EXPECTED_MODIFIED
        or metadata.get("provenance") != "local-synthetic-adaptive-epub-fixture"
    ):
        raise AdaptiveEpubError("invalid-package-metadata")
    actual = hashlib.sha256(Path(base_epub).read_bytes()).hexdigest()
    if metadata.get("base_epub_sha256") != actual:
        raise AdaptiveEpubError("source-epub-hash-mismatch")
    if metadata.get("adaptive_rendering_report_hash") != rendering_report.get("hash"):
        raise AdaptiveEpubError("rendering-report-mismatch")
    if metadata.get("adaptive_xhtml_directory_hash") != directory_hash(xhtml):
        raise AdaptiveEpubError("adaptive-directory-hash-mismatch")


def validate_rendering_report(report: dict[str, Any], xhtml: dict[str, bytes]) -> None:
    expected_fields = {
        "schema_version", "report_id", "book_id", "source_schema_versions",
        "source_hashes", "precedence", "configuration", "document_results",
        "occurrence_results", "diagnostics", "hash",
    }
    if set(report) != expected_fields or report.get("schema_version") != 1:
        raise AdaptiveEpubError("unsupported-schema-or-field")
    if report.get("report_id") != "adaptive-rendering-report-v1":
        raise AdaptiveEpubError("rendering-report-mismatch")
    _check_hash(report, "rendering-report-mismatch")
    for value in report.get("document_results", []) + report.get("occurrence_results", []) + report.get("diagnostics", []):
        _check_hash(value, "rendering-report-mismatch")
    documents = report.get("document_results", [])
    paths = [value.get("path") for value in documents]
    if len(paths) != len(set(paths)):
        raise AdaptiveEpubError("duplicate-archive-path")
    if paths != list(TEXT_PATHS) or len(report.get("occurrence_results", [])) != 12:
        raise AdaptiveEpubError("rendering-report-mismatch")
    for value in documents:
        if hashlib.sha256(xhtml[value["path"]]).hexdigest() != value.get("output_sha256"):
            raise AdaptiveEpubError("adaptive-document-hash-mismatch")
    if [(x.get("reason"), x.get("source_id")) for x in report.get("diagnostics", [])] != [
        ("missing-approved-reading", "study-item-0002-occ-0001")
    ]:
        raise AdaptiveEpubError("rendering-report-mismatch")


def _replace_metadata(package_bytes: bytes, metadata: dict[str, Any]) -> bytes:
    try:
        package = ET.fromstring(package_bytes)
    except ET.ParseError as error:
        raise AdaptiveEpubError("invalid-manifest") from error
    values = package.find(f"{{{OPF}}}metadata")
    if values is None:
        raise AdaptiveEpubError("invalid-manifest")
    identifier = values.find(f"{{{DC}}}identifier")
    title = values.find(f"{{{DC}}}title")
    language = values.find(f"{{{DC}}}language")
    modified = next(
        (node for node in values.findall(f"{{{OPF}}}meta") if node.get("property") == "dcterms:modified"),
        None,
    )
    if any(value is None for value in (identifier, title, language, modified)):
        raise AdaptiveEpubError("invalid-manifest")
    identifier.text = metadata["identifier"]
    title.text = metadata["title"]
    language.text = metadata["language"]
    modified.text = metadata["modified"]
    return ET.tostring(package, encoding="utf-8", xml_declaration=True) + b"\n"


def _resolve(source: str, href: str) -> tuple[str, str]:
    split = urlsplit(href)
    if (
        split.scheme or split.netloc or split.path.startswith("/") or "\\" in split.path
        or ".." in PurePosixPath(split.path).parts or re.match(r"^[A-Za-z]:", split.path)
    ):
        raise AdaptiveEpubError("unsafe-archive-path")
    target = source if not split.path else posixpath.normpath(
        posixpath.join(posixpath.dirname(source), split.path)
    )
    return _safe_path(target), split.fragment


def _xhtml_summary(files: dict[str, bytes]) -> dict[str, Any]:
    roots: dict[str, ET.Element] = {}
    ids: dict[str, set[str]] = {}
    for path in (NAV_PATH, *TEXT_PATHS):
        try:
            root = ET.fromstring(files[path])
        except ET.ParseError as error:
            raise AdaptiveEpubError("corrupt-input") from error
        if root.tag != X + "html":
            raise AdaptiveEpubError("unsupported-schema-or-field")
        values = [node.get("id") for node in root.iter() if node.get("id")]
        if len(values) != len(set(values)):
            raise AdaptiveEpubError("duplicate-archive-path")
        if path in TEXT_PATHS and (
            root.get("lang") != "ja" or root.get(f"{{{XML}}}lang") != "ja"
        ):
            raise AdaptiveEpubError("unsupported-schema-or-field")
        roots[path] = root
        ids[path] = set(values)
    for path, root in roots.items():
        parents = {child: parent for parent in root.iter() for child in parent}
        for node in root.iter():
            local = node.tag.rsplit("}", 1)[-1]
            if local in {"script", "iframe", "object", "embed"} or any(
                key.lower().startswith("on") for key in node.attrib
            ):
                raise AdaptiveEpubError("unsafe-hidden-content")
            if node.tag in {X + "a", X + "ruby"} and any(
                child.tag == node.tag for child in node.iter() if child is not node
            ):
                raise AdaptiveEpubError("unsafe-hidden-content")
            if node.tag == X + "a":
                parent = parents.get(node)
                while parent is not None:
                    if parent.tag in {X + "a", X + "ruby", X + "rb", X + "rt", X + "rp"}:
                        raise AdaptiveEpubError("unsafe-hidden-content")
                    parent = parents.get(parent)
            for attribute in ("href", "src"):
                href = node.get(attribute)
                if not href:
                    continue
                target, fragment = _resolve(path, href)
                if target not in files or fragment and fragment not in ids.get(target, set()):
                    raise AdaptiveEpubError("broken-fragment")
    chapter = roots["EPUB/text/grammar-01.xhtml"]
    notes = roots["EPUB/text/study-notes.xhtml"]
    grammar_notes = roots["EPUB/text/grammar-notes.xhtml"]
    reading = next(
        (node for node in chapter.iter() if node.get("id") == "adaptive-reading-study-item-0005-occ-0001"),
        None,
    )
    if reading is None or reading.text != "前" or reading.find(X + "rt") is None or reading.find(X + "rt").text != "まえ":
        raise AdaptiveEpubError("missing-presented-reading")
    meanings = [
        (node.text or "") for node in notes.iter()
        if node.get("class") == "adaptive-meaning-assistance"
    ]
    if meanings != ["to read"]:
        raise AdaptiveEpubError("missing-approved-meaning")
    study_links = sum(
        1 for root in roots.values() for node in root.iter()
        if node.tag == X + "a" and node.get("class") == "study-link"
    )
    study_backlinks = sum(
        1 for node in notes.iter()
        if node.tag == X + "a" and node.get("class") == "study-note__backlink"
    )
    if (study_links, study_backlinks) != (5, 5):
        raise AdaptiveEpubError("study-link-mismatch")
    grammar_links = sum(
        1 for root in roots.values() for node in root.iter()
        if node.tag == X + "a" and node.get("class") == "grammar-link"
    )
    grammar_backlinks = sum(
        1 for node in grammar_notes.iter()
        if node.tag == X + "a" and node.get("class") == "grammar-study-note__backlink"
    )
    grammar_sections = [
        node for node in grammar_notes.iter()
        if node.tag == X + "section" and "grammar-study-note" in (node.get("class") or "").split()
    ]
    contexts = [node for node in grammar_notes.iter() if node.get("data-occurrence-id")]
    if (
        (grammar_links, grammar_backlinks) != (2, 2)
        or [node.get("id") for node in grammar_sections] != ["grammar-note-0001", "grammar-note-0002", "grammar-note-0005"]
        or [node.get("data-occurrence-id") for node in contexts] != [
            "grammar-plan-occurrence-0001", "grammar-plan-occurrence-0002",
            "grammar-plan-occurrence-0007",
        ]
    ):
        raise AdaptiveEpubError("grammar-link-mismatch")
    span = next(
        (node for node in chapter.iter() if node.get("id") == "grammar-src-grammar-occurrence-0005"),
        None,
    )
    if span is None or span.tag != X + "span" or span.text != "読んでいる":
        raise AdaptiveEpubError("grammar-link-mismatch")
    ruby = next(
        (node for node in chapter.iter() if node.get("id") == "publisher-ruby-1-8-1"),
        None,
    )
    if ruby is None or ruby.text != "表舞台" or ruby.find(X + "rt") is None or ruby.find(X + "rt").text != "おもてぶたい":
        raise AdaptiveEpubError("publisher-ruby-mismatch")
    blob = b"\n".join(files[path] for path in sorted(files)).lower().replace(b" ", b"")
    for value in (
        "よん", "まいにちよむ", "to forget completely", "to read every day",
        "Mae (synthetic name)",
    ):
        if value.lower().encode().replace(b" ", b"") in blob:
            raise AdaptiveEpubError("suppressed-content-restoration")
    for value in (
        b"display:none", b"visibility:hidden", b"data-meaning", b"<!--",
        b"position:absolute", b"font-size:0", b"opacity:0", b"url(",
        b"provider", b"model-id", b"cache-key", b"prompt", b"source-path",
        b"learner-identity", b"learner-profile", b"profile-label",
        b"exposure-history", b"density-rationale", b"override-note",
        b"reviewer-note", b"telemetry",
    ):
        if value in blob:
            raise AdaptiveEpubError("unsafe-hidden-content")
    return {
        "xhtml_document_hashes": [
            {"path": path, "sha256": hashlib.sha256(files[path]).hexdigest()}
            for path in TEXT_PATHS
        ],
        "rendering_result_count": 12,
        "generated_reading_count": 1,
        "displayed_meaning_count": 1,
        "study_forward_links": study_links,
        "study_backlinks": study_backlinks,
        "grammar_forward_links": grammar_links,
        "grammar_backlinks": grammar_backlinks,
        "grammar_notes": len(grammar_sections),
        "grammar_contexts": len(contexts),
        "publisher_ruby": {"id": ruby.get("id"), "surface": ruby.text, "reading": ruby.find(X + "rt").text},
    }


def _package_summary(files: dict[str, bytes], metadata: dict[str, Any]) -> dict[str, Any]:
    try:
        container = ET.fromstring(files["META-INF/container.xml"])
        package = ET.fromstring(files[PACKAGE_PATH])
        nav = ET.fromstring(files[NAV_PATH])
    except (KeyError, ET.ParseError) as error:
        raise AdaptiveEpubError("invalid-container") from error
    roots = container.findall(f".//{{{CONTAINER}}}rootfile")
    if len(roots) != 1 or roots[0].get("full-path") != PACKAGE_PATH or roots[0].get("media-type") != "application/oebps-package+xml":
        raise AdaptiveEpubError("invalid-container")
    if package.tag != f"{{{OPF}}}package" or package.get("version") != "3.0":
        raise AdaptiveEpubError("invalid-manifest")
    package_metadata = package.find(f"{{{OPF}}}metadata")
    manifest = package.find(f"{{{OPF}}}manifest")
    spine = package.find(f"{{{OPF}}}spine")
    if any(value is None for value in (package_metadata, manifest, spine)):
        raise AdaptiveEpubError("invalid-manifest")
    identifier = package_metadata.find(f"{{{DC}}}identifier")
    title = package_metadata.find(f"{{{DC}}}title")
    language = package_metadata.find(f"{{{DC}}}language")
    modified = next((x for x in package_metadata.findall(f"{{{OPF}}}meta") if x.get("property") == "dcterms:modified"), None)
    actual_metadata = {
        "identifier": identifier.text if identifier is not None else None,
        "title": title.text if title is not None else None,
        "language": language.text if language is not None else None,
        "modified": modified.text if modified is not None else None,
    }
    if actual_metadata != {key: metadata[key] for key in ("identifier", "title", "language", "modified")}:
        raise AdaptiveEpubError("invalid-package-metadata")
    items = manifest.findall(f"{{{OPF}}}item")
    manifest_values = [
        {"id": item.get("id"), "href": item.get("href"), "media_type": item.get("media-type"), "properties": item.get("properties")}
        for item in items
    ]
    if len({x["id"] for x in manifest_values}) != len(items) or len({x["href"] for x in manifest_values}) != len(items):
        raise AdaptiveEpubError("invalid-manifest")
    expected_manifest = [
        {"id": "nav", "href": "nav.xhtml", "media_type": "application/xhtml+xml", "properties": "nav"},
        {"id": "grammar-ch1", "href": "text/grammar-01.xhtml", "media_type": "application/xhtml+xml", "properties": None},
        {"id": "grammar-ch2", "href": "text/grammar-02.xhtml", "media_type": "application/xhtml+xml", "properties": None},
        {"id": "furiganalyse-study-notes", "href": "text/study-notes.xhtml", "media_type": "application/xhtml+xml", "properties": None},
        {"id": "furiganalyse-grammar-notes", "href": "text/grammar-notes.xhtml", "media_type": "application/xhtml+xml", "properties": None},
    ]
    if manifest_values != expected_manifest:
        raise AdaptiveEpubError("invalid-manifest")
    for item in manifest_values:
        target, fragment = _resolve(PACKAGE_PATH, item["href"])
        if target not in files or fragment:
            raise AdaptiveEpubError("invalid-manifest")
    spine_values = [item.get("idref") for item in spine.findall(f"{{{OPF}}}itemref")]
    if spine_values != SPINE:
        raise AdaptiveEpubError("invalid-spine")
    navs = [node for node in nav.findall(f".//{X}nav") if node.get(f"{{{EPUB}}}type") == "toc"]
    if len(navs) != 1:
        raise AdaptiveEpubError("invalid-navigation")
    nav_values = [
        {"label": (link.text or "").strip(), "href": link.get("href")}
        for link in navs[0].findall(f".//{X}a")
    ]
    if nav_values != [{"label": label, "href": href} for label, href in NAVIGATION]:
        raise AdaptiveEpubError("invalid-navigation")
    summary = {
        "archive_member_order": MEMBER_ORDER,
        "container_rootfile": PACKAGE_PATH,
        "package_metadata": actual_metadata,
        "manifest": manifest_values,
        "spine": spine_values,
        "navigation": nav_values,
        **_xhtml_summary(files),
    }
    return summary


def _manifest_id(path: str) -> str | None:
    return {
        NAV_PATH: "nav", "EPUB/text/grammar-01.xhtml": "grammar-ch1",
        "EPUB/text/grammar-02.xhtml": "grammar-ch2",
        "EPUB/text/study-notes.xhtml": "furiganalyse-study-notes",
        "EPUB/text/grammar-notes.xhtml": "furiganalyse-grammar-notes",
    }.get(path)


def package_adaptive_epub(
    base_epub: str | Path,
    rendering_report: dict[str, Any],
    adaptive_dir: str | Path,
    metadata: dict[str, Any],
    output_epub: str | Path,
) -> dict[str, Any]:
    xhtml = _read_adaptive_xhtml(adaptive_dir)
    validate_metadata(
        metadata, rendering_report.get("book_id"), base_epub,
        rendering_report, xhtml,
    )
    try:
        validate_phase7_archive(base_epub, grammar=True)
    except GrammarEpubError as error:
        raise AdaptiveEpubError("source-epub-hash-mismatch") from error
    base, _ = _read_archive(base_epub)
    if set(base) != MEMBERS or base.get("mimetype") != b"application/epub+zip":
        raise AdaptiveEpubError("invalid-mimetype")
    validate_rendering_report(rendering_report, xhtml)
    files = dict(base)
    files.update(xhtml)
    files[PACKAGE_PATH] = _replace_metadata(base[PACKAGE_PATH], metadata)
    _package_summary(files, metadata)
    write_deterministic_epub(files, output_epub)
    return build_packaging_report(
        base_epub, rendering_report, xhtml, metadata, output_epub,
    )


def build_packaging_report(
    base_epub: str | Path,
    rendering_report: dict[str, Any],
    xhtml: dict[str, bytes],
    metadata: dict[str, Any],
    output_epub: str | Path,
) -> dict[str, Any]:
    files, infos = _read_archive(output_epub)
    if set(files) != MEMBERS or files.get("mimetype") != b"application/epub+zip":
        raise AdaptiveEpubError("invalid-mimetype")
    if [info.filename for info in infos] != MEMBER_ORDER:
        raise AdaptiveEpubError("invalid-configuration")
    if infos[0].compress_type != zipfile.ZIP_STORED or any(
        info.compress_type != zipfile.ZIP_DEFLATED for info in infos[1:]
    ):
        raise AdaptiveEpubError("invalid-configuration")
    if any(
        info.date_time != FIXED_TIME or info.create_system != 3
        or info.external_attr != 0o100644 << 16 or info.extra or info.comment
        for info in infos
    ):
        raise AdaptiveEpubError("invalid-configuration")
    summary = _package_summary(files, metadata)
    summary["rendering_diagnostic_references"] = [
        {"id": value["id"], "reason": value["reason"], "source_id": value["source_id"]}
        for value in rendering_report["diagnostics"]
    ]
    summary = _add_hash(summary)
    member_records = []
    for number, info in enumerate(infos, 1):
        data = files[info.filename]
        member_records.append(_add_hash({
            "id": f"adaptive-epub-member-{number:04d}",
            "path": info.filename,
            "compression": "stored" if info.compress_type == zipfile.ZIP_STORED else "deflated",
            "timestamp": list(info.date_time),
            "permissions": oct(info.external_attr >> 16),
            "creator_system": info.create_system,
            "uncompressed_size": info.file_size,
            "compressed_size": info.compress_size,
            "crc": info.CRC,
            "sha256": hashlib.sha256(data).hexdigest(),
            "manifest_id": _manifest_id(info.filename),
        }))
    configuration = _add_hash({"enabled": True})
    report = {
        "schema_version": 1,
        "report_id": "adaptive-epub-packaging-report-v1",
        "book_id": rendering_report["book_id"],
        "source_hashes": {
            "base_epub": hashlib.sha256(Path(base_epub).read_bytes()).hexdigest(),
            "adaptive_rendering_report": rendering_report["hash"],
            "adaptive_xhtml_directory": directory_hash(xhtml),
        },
        "package_metadata": {"id": metadata["id"], "hash": metadata["hash"], "provenance": metadata["provenance"]},
        "configuration": configuration,
        "output_epub_sha256": hashlib.sha256(Path(output_epub).read_bytes()).hexdigest(),
        "archive_members": member_records,
        "structural_summary": summary,
        "diagnostics": [],
    }
    report["hash"] = stable_hash(report)
    return report


def empty_report(book_id: str | None, reason: str) -> dict[str, Any]:
    configuration = _add_hash({"enabled": False})
    diagnostic = _add_hash({
        "id": "adaptive-epub-diagnostic-0001", "reason": reason,
        "source_id": "adaptive-epub-packaging",
    })
    report = {
        "schema_version": 1,
        "report_id": "adaptive-epub-packaging-report-v1",
        "book_id": book_id,
        "source_hashes": {},
        "package_metadata": None,
        "configuration": configuration,
        "output_epub_sha256": None,
        "archive_members": [],
        "structural_summary": None,
        "diagnostics": [diagnostic],
    }
    report["hash"] = stable_hash(report)
    return report


def safe_package_adaptive_epub(
    base_epub: str | Path,
    rendering_report: dict[str, Any] | None,
    adaptive_dir: str | Path | None,
    metadata: dict[str, Any] | None,
    output_epub: str | Path,
    *,
    enabled: bool = False,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    output = Path(output_epub)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not enabled or failure_reason:
        output.write_bytes(Path(base_epub).read_bytes())
        return empty_report(
            rendering_report.get("book_id") if rendering_report else None,
            failure_reason or "disabled",
        )
    try:
        if rendering_report is None or adaptive_dir is None or metadata is None:
            raise AdaptiveEpubError("invalid-configuration")
        return package_adaptive_epub(
            base_epub, rendering_report, adaptive_dir, metadata, output,
        )
    except AdaptiveEpubError as error:
        output.write_bytes(Path(base_epub).read_bytes())
        return empty_report(
            rendering_report.get("book_id") if rendering_report else None,
            error.reason,
        )
