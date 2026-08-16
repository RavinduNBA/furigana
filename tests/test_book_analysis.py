import json

import pytest

from furiganalyse.book_analysis import (
    BookAnalysisError,
    SCHEMA_VERSION,
    _resolve_archive_path,
    extract_book,
    serialize_book,
    write_book_json,
)
from tests.phase0_epub import build_fixture


@pytest.fixture
def extracted_fixture(tmp_path):
    epub = tmp_path / "fixture.epub"
    build_fixture(epub)
    return extract_book(epub)


def test_extracts_manifest_spine_order_and_blocks(extracted_fixture):
    book = extracted_fixture
    assert book.schema_version == SCHEMA_VERSION == 1
    assert book.book_id == "urn:uuid:furiganalyse-phase-0"
    assert book.package_path == "EPUB/package.opf"
    assert [chapter.id for chapter in book.chapters] == ["ch-0001", "ch-0002"]
    assert [chapter.spine_index for chapter in book.chapters] == [0, 1]
    assert [chapter.source_path for chapter in book.chapters] == [
        "EPUB/text/chapter-01.xhtml",
        "EPUB/text/chapter-02.xhtml",
    ]
    assert all("nav.xhtml" not in chapter.source_path for chapter in book.chapters)
    assert [block.id for block in book.chapters[0].blocks] == [
        f"ch-0001-b-{index:04d}" for index in range(1, 6)
    ]
    assert [block.id for block in book.chapters[1].blocks] == [
        f"ch-0002-b-{index:04d}" for index in range(1, 6)
    ]


def test_extracts_normalized_visible_text_and_paragraph_boundaries(extracted_fixture):
    chapter_1, chapter_2 = extracted_fixture.chapters
    assert [block.text for block in chapter_1.blocks] == [
        "第一章 出会い",
        "「今日は良い天気だね」と彼女は言った。",
        "強調された言葉と、句読点——そして English text.",
        "舞台は表舞台だった。 表舞台の漢字。 第一",
        "次の章へ",
    ]
    assert [block.text for block in chapter_2.blocks] == [
        "第二章 答え",
        "名前は雪乃。怪訝な顔で振り返った。",
        "未知の漢字は保存する。",
        "Numbers 123 and Greek text remain ordinary text.",
        "第一章へ戻る",
    ]
    for chapter in extracted_fixture.chapters:
        assert chapter.text == "\n".join(block.text for block in chapter.blocks)

    canonical_text = "\n".join(chapter.text for chapter in extracted_fixture.chapters)
    for reading in ("おもてぶたい", "ファースト", "ゆきの"):
        assert reading not in canonical_text
    assert "（" not in canonical_text
    assert "）" not in canonical_text


def test_attaches_publisher_ruby_with_deterministic_offsets(extracted_fixture):
    spans = {}
    for chapter in extracted_fixture.chapters:
        for block in chapter.blocks:
            for span in block.publisher_ruby:
                assert span.id not in spans
                assert 0 <= span.start < span.end <= len(block.text)
                assert block.text[span.start : span.end] == span.surface
                assert span.source == "publisher"
                spans[span.source_anchor] = span

    assert set(spans) == {
        "publisher-fallback",
        "publisher-grouped",
        "publisher-malformed",
        "publisher-nested",
        "publisher-unusual",
    }
    assert spans["publisher-grouped"].surface == "表舞台"
    assert spans["publisher-grouped"].reading == "おもてぶたい"
    assert spans["publisher-unusual"].reading == "ファースト"
    assert spans["publisher-fallback"].reading == "ゆきの"
    assert spans["publisher-malformed"].surface == "未知"
    assert spans["publisher-malformed"].reading is None


def test_serialized_json_is_byte_deterministic(tmp_path):
    epub = tmp_path / "fixture.epub"
    first = tmp_path / "first" / "book.json"
    second = tmp_path / "second" / "book.json"
    build_fixture(epub)

    first_book = extract_book(epub)
    second_book = extract_book(epub)
    assert serialize_book(first_book) == serialize_book(second_book)
    write_book_json(first_book, first)
    write_book_json(second_book, second)

    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["chapters"][0]["blocks"][3]["source_anchor"] == "publisher-ruby-cases"


@pytest.mark.parametrize("href", ["../../outside.xhtml", "/absolute.xhtml", "..\\outside.xhtml"])
def test_rejects_unsafe_manifest_paths(href):
    with pytest.raises(BookAnalysisError, match="Unsafe EPUB archive path"):
        _resolve_archive_path("EPUB/package.opf", href)
