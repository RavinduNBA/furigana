import hashlib
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import pytest
from furiganalyse.epub_packaging import EpubPackagingError, NOTES_ID, build_study_epub
from tests.phase0_epub import validate_epub

ROOT = Path(__file__).resolve().parents[1]
EPUB = ROOT / "artifacts/phase2/fixture.epub"
BOOK = ROOT / "artifacts/phase2/run-a/book.json"
PLAN = ROOT / "tests/phase4_golden/annotation-plan-v1.json"
OPF = "{http://www.idpf.org/2007/opf}"
X = "{http://www.w3.org/1999/xhtml}"


@pytest.fixture
def inputs():
    return json.loads(BOOK.read_text()), json.loads(PLAN.read_text())


def test_package_structure_navigation_and_resources(inputs, tmp_path):
    book, plan = inputs
    out = tmp_path / "study.epub"
    before = hashlib.sha256(EPUB.read_bytes()).hexdigest()
    build_study_epub(EPUB, book, plan, out)
    assert (
        hashlib.sha256(EPUB.read_bytes()).hexdigest() == before
        and validate_epub(out) == []
    )
    with zipfile.ZipFile(out) as z:
        infos = z.infolist()
        assert (
            infos[0].filename == "mimetype"
            and infos[0].compress_type == zipfile.ZIP_STORED
        )
        package = ET.fromstring(z.read("EPUB/package.opf"))
        nav = ET.fromstring(z.read("EPUB/nav.xhtml"))
        items = package.findall(".//" + OPF + "item")
        assert sum(i.get("id") == NOTES_ID for i in items) == 1
        assert (
            next(i for i in items if i.get("id") == NOTES_ID).get("href")
            == "text/study-notes.xhtml"
        )
        assert [x.get("idref") for x in package.findall(".//" + OPF + "itemref")] == [
            "ch1",
            "ch2",
            NOTES_ID,
        ]
        links = [
            a
            for a in nav.findall(".//" + X + "a")
            if (a.text or "").strip() == "Study Notes"
        ]
        assert len(links) == 1 and links[0].get("href") == "text/study-notes.xhtml"
        assert z.read("EPUB/styles/book.css") == zipfile.ZipFile(EPUB).read(
            "EPUB/styles/book.css"
        )
        assert z.read("EPUB/images/lantern.svg") == zipfile.ZipFile(EPUB).read(
            "EPUB/images/lantern.svg"
        )


def test_two_packages_are_byte_identical(inputs, tmp_path):
    book, plan = inputs
    a = tmp_path / "a.epub"
    b = tmp_path / "b.epub"
    build_study_epub(EPUB, book, plan, a)
    build_study_epub(EPUB, book, plan, b)
    assert a.read_bytes() == b.read_bytes()


@pytest.mark.parametrize(
    "member", ["META-INF/container.xml", "EPUB/package.opf", "EPUB/nav.xhtml"]
)
def test_rejects_missing_required_files(inputs, tmp_path, member):
    book, plan = inputs
    broken = tmp_path / "broken.epub"
    with zipfile.ZipFile(EPUB) as src, zipfile.ZipFile(broken, "w") as dst:
        for info in src.infolist():
            if info.filename != member:
                dst.writestr(info, src.read(info.filename))
    with pytest.raises((EpubPackagingError, KeyError, ET.ParseError)):
        build_study_epub(broken, book, plan, tmp_path / "out.epub")


def test_rejects_existing_note_manifest(inputs, tmp_path):
    book, plan = inputs
    broken = tmp_path / "broken.epub"
    with zipfile.ZipFile(EPUB) as src:
        files = {n: src.read(n) for n in src.namelist()}
    root = ET.fromstring(files["EPUB/package.opf"])
    manifest = root.find(OPF + "manifest")
    ET.SubElement(
        manifest,
        OPF + "item",
        {
            "id": NOTES_ID,
            "href": "text/other.xhtml",
            "media-type": "application/xhtml+xml",
        },
    )
    files["EPUB/package.opf"] = ET.tostring(root)
    with zipfile.ZipFile(broken, "w") as z:
        for n, v in files.items():
            z.writestr(n, v)
    with pytest.raises(EpubPackagingError, match="existing study-note"):
        build_study_epub(broken, book, plan, tmp_path / "out.epub")
