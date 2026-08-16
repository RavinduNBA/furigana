import zipfile
from copy import deepcopy
from xml.etree import ElementTree as ET

from furiganalyse.__main__ import main
from furiganalyse.epub_format import write_epub_archive
from furiganalyse.params import FuriganaMode, OutputFormat
from tests.phase0_epub import build_fixture, validate_epub

XHTML = "{http://www.w3.org/1999/xhtml}"
PUBLISHER_RUBY_IDS = {
    "publisher-fallback",
    "publisher-grouped",
    "publisher-malformed",
    "publisher-nested",
    "publisher-unusual",
}


def publisher_ruby_snapshots(path):
    snapshots = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.endswith((".html", ".xhtml")):
                continue
            root = ET.fromstring(archive.read(name))
            for ruby in root.findall(f".//{XHTML}ruby"):
                ruby_id = ruby.attrib.get("id", "")
                if not ruby_id.startswith("publisher-"):
                    continue
                normalized = deepcopy(ruby)
                normalized.tail = None
                snapshots[ruby_id] = ET.tostring(normalized, encoding="unicode")
    return snapshots


def test_phase0_fixture_is_structurally_valid(tmp_path):
    fixture = tmp_path / "fixture.epub"
    build_fixture(fixture)
    assert validate_epub(fixture) == []


def test_archive_writer_obeys_epub_mimetype_rules(tmp_path):
    fixture = tmp_path / "fixture.epub"
    extracted = tmp_path / "extracted"
    output = tmp_path / "rewritten.epub"
    build_fixture(fixture)
    with zipfile.ZipFile(fixture) as archive:
        archive.extractall(extracted)
    write_epub_archive(extracted, output)
    assert validate_epub(output) == []


def test_existing_conversion_preserves_fixture_structure(tmp_path, caplog):
    fixture = tmp_path / "fixture.epub"
    output = tmp_path / "converted.epub"
    build_fixture(fixture)
    with caplog.at_level("WARNING"):
        main(
            str(fixture),
            str(output),
            furigana_mode=FuriganaMode.add,
            output_format=OutputFormat.epub,
        )
    assert validate_epub(output) == []
    original_ruby = publisher_ruby_snapshots(fixture)
    converted_ruby = publisher_ruby_snapshots(output)
    assert set(original_ruby) == PUBLISHER_RUBY_IDS
    assert converted_ruby == original_ruby
    assert "Preserving unsupported publisher ruby" in caplog.text

    with zipfile.ZipFile(output) as archive:
        chapter_1 = ET.fromstring(archive.read("EPUB/text/chapter-01.xhtml"))
        chapter_2 = ET.fromstring(archive.read("EPUB/text/chapter-02.xhtml"))
        chapter_1_text = ET.tostring(chapter_1, encoding="unicode", method="text")
        chapter_2_text = ET.tostring(chapter_2, encoding="unicode", method="text")

    for root in (chapter_1, chapter_2):
        for publisher in root.findall(f".//{XHTML}ruby"):
            if publisher.attrib.get("id", "").startswith("publisher-"):
                assert publisher.find(f".//{XHTML}ruby") is None

    malformed = chapter_2.find(f".//{XHTML}ruby[@id='publisher-malformed']")
    paragraph = chapter_2.find(f".//{XHTML}p[@id='malformed-ruby']")
    children = list(paragraph)
    following = children[children.index(malformed) + 1 :]
    assert any(child.tag == f"{XHTML}ruby" and "id" not in child.attrib for child in following)

    assert "English text." in chapter_1_text
    assert "Greek text remain ordinary text." in chapter_2_text
