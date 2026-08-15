import zipfile

from furiganalyse.__main__ import main
from furiganalyse.epub_format import write_epub_archive
from furiganalyse.params import FuriganaMode, OutputFormat
from tests.phase0_epub import build_fixture, validate_epub


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


def test_existing_conversion_preserves_fixture_structure(tmp_path):
    fixture = tmp_path / "fixture.epub"
    output = tmp_path / "converted.epub"
    build_fixture(fixture)
    main(
        str(fixture),
        str(output),
        furigana_mode=FuriganaMode.add,
        output_format=OutputFormat.epub,
    )
    assert validate_epub(output) == []
    with zipfile.ZipFile(output) as archive:
        chapter_1 = archive.read("EPUB/text/chapter-01.xhtml").decode()
        chapter_2 = archive.read("EPUB/text/chapter-02.xhtml").decode()
    assert "<ruby>\u8868\u821e\u53f0<rt>\u304a\u3082\u3066\u3076\u305f\u3044</rt></ruby>" in chapter_1
    assert "<ruby>\u96ea\u4e43<rt>\u3086\u304d\u306e</rt></ruby>" in chapter_2
    assert "English text." in chapter_1
    assert "Greek text remain ordinary text." in chapter_2
