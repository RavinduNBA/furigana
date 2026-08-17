"""Deterministic EPUB packaging for validated Phase 4 linked XHTML."""

from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from furiganalyse.linked_output import create_linked_output

CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF = "http://www.idpf.org/2007/opf"
XHTML = "http://www.w3.org/1999/xhtml"
EPUB = "http://www.idpf.org/2007/ops"
NOTES_ID = "furiganalyse-study-notes"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
ET.register_namespace("", OPF)
ET.register_namespace("", XHTML)
ET.register_namespace("epub", EPUB)


class EpubPackagingError(ValueError):
    """Raised when deterministic safe EPUB packaging is impossible."""


def _safe(name: str) -> str:
    p = PurePosixPath(name)
    if not name or p.is_absolute() or ".." in p.parts or "\\" in name:
        raise EpubPackagingError(f"Unsafe EPUB member: {name!r}")
    return p.as_posix()


def _xml(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def _resolve(source: str, href: str) -> str:
    return posixpath.normpath(
        posixpath.join(posixpath.dirname(source), urlsplit(href).path)
    )


def package_study_epub(input_epub, book, plan) -> dict[str, bytes]:
    source = Path(input_epub)
    linked = create_linked_output(source, book, plan)
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        names = [_safe(info.filename) for info in infos]
        if len(names) != len(set(names)):
            raise EpubPackagingError("Duplicate EPUB archive member")
        files = {name: archive.read(name) for name in names}
    if files.get("mimetype") != b"application/epub+zip":
        raise EpubPackagingError("Invalid EPUB mimetype")
    try:
        container = ET.fromstring(files["META-INF/container.xml"])
    except KeyError as error:
        raise EpubPackagingError("Missing EPUB container") from error
    rootfile = container.find(f".//{{{CONTAINER}}}rootfile")
    if rootfile is None or not rootfile.get("full-path"):
        raise EpubPackagingError("Container has no package document")
    package_path = _safe(rootfile.get("full-path"))
    if package_path not in files:
        raise EpubPackagingError("Missing package document")
    package = ET.fromstring(files[package_path])
    manifest = package.find(f"{{{OPF}}}manifest")
    spine = package.find(f"{{{OPF}}}spine")
    if manifest is None or spine is None:
        raise EpubPackagingError("Package lacks manifest or spine")
    items = manifest.findall(f"{{{OPF}}}item")
    ids = [x.get("id") for x in items]
    hrefs = [x.get("href") for x in items]
    if len(ids) != len(set(ids)) or len(hrefs) != len(set(hrefs)):
        raise EpubPackagingError("Duplicate manifest ID or href")
    notes_href = posixpath.relpath(linked.notes_path, posixpath.dirname(package_path))
    if NOTES_ID in ids or notes_href in hrefs:
        raise EpubPackagingError("Incompatible existing study-note manifest item")
    nav_items = [x for x in items if "nav" in (x.get("properties") or "").split()]
    if len(nav_items) != 1:
        raise EpubPackagingError("Package must have exactly one navigation document")
    nav_path = _resolve(package_path, nav_items[0].get("href"))
    if nav_path not in files:
        raise EpubPackagingError("Missing navigation document")
    idrefs = [x.get("idref") for x in spine.findall(f"{{{OPF}}}itemref")]
    if len(idrefs) != len(set(idrefs)) or any(value not in ids for value in idrefs):
        raise EpubPackagingError("Duplicate or unknown spine reference")
    ET.SubElement(
        manifest,
        f"{{{OPF}}}item",
        {"id": NOTES_ID, "href": notes_href, "media-type": "application/xhtml+xml"},
    )
    ET.SubElement(spine, f"{{{OPF}}}itemref", {"idref": NOTES_ID})
    nav = ET.fromstring(files[nav_path])
    toc = next(
        (
            n
            for n in nav.findall(f".//{{{XHTML}}}nav")
            if n.get(f"{{{EPUB}}}type") == "toc"
        ),
        None,
    )
    if toc is None:
        raise EpubPackagingError("Navigation document has no TOC")
    ordered = toc.find(f"{{{XHTML}}}ol")
    if ordered is None:
        raise EpubPackagingError("TOC has no ordered list")
    if any(
        (a.text or "").strip() == "Study Notes" for a in toc.findall(f".//{{{XHTML}}}a")
    ):
        raise EpubPackagingError("Incompatible existing Study Notes navigation entry")
    li = ET.SubElement(ordered, f"{{{XHTML}}}li")
    anchor = ET.SubElement(
        li,
        f"{{{XHTML}}}a",
        {"href": posixpath.relpath(linked.notes_path, posixpath.dirname(nav_path))},
    )
    anchor.text = "Study Notes"
    files.update(linked.files)
    files[package_path] = _xml(package)
    files[nav_path] = _xml(nav)
    return files


def write_deterministic_epub(files: dict[str, bytes], output_path):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    ordered = ["mimetype"] + sorted(name for name in files if name != "mimetype")
    with zipfile.ZipFile(output, "w") as archive:
        for name in ordered:
            info = zipfile.ZipInfo(_safe(name), FIXED_TIME)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = (
                zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            )
            archive.writestr(info, files[name])


def build_study_epub(input_epub, book, plan, output_path):
    files = package_study_epub(input_epub, book, plan)
    write_deterministic_epub(files, output_path)
    return files
