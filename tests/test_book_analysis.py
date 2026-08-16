import json
from dataclasses import replace
from pathlib import Path

import pytest

from furiganalyse.book_analysis import (
    BookAnalysisError,
    SCHEMA_VERSION,
    _resolve_archive_path,
    extract_book,
    serialize_book,
    validate_book,
    write_book_json,
)
from tests.phase0_epub import build_fixture

GOLDEN_BOOK = Path(__file__).parent / "golden" / "phase2-book-v2.json"


@pytest.fixture
def extracted_fixture(tmp_path):
    epub = tmp_path / "fixture.epub"
    build_fixture(epub)
    return extract_book(epub)


def test_extracts_manifest_spine_order_and_blocks(extracted_fixture):
    book = extracted_fixture
    assert book.schema_version == SCHEMA_VERSION == 2
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


def test_extracts_sentences_with_block_relative_offsets(extracted_fixture):
    block = extracted_fixture.chapters[0].blocks[3]
    assert [
        (sentence.id, sentence.text, sentence.start, sentence.end)
        for sentence in block.sentences
    ] == [
        ("ch-0001-b-0004-s-0001", "舞台は表舞台だった。", 0, 10),
        ("ch-0001-b-0004-s-0002", "表舞台の漢字。", 11, 18),
        ("ch-0001-b-0004-s-0003", "第一", 19, 21),
    ]


def test_text_spans_partition_sentences_and_reference_publisher_ruby(extracted_fixture):
    block = extracted_fixture.chapters[0].blocks[3]
    first, second, third = block.sentences
    assert [span.text for span in first.text_spans] == ["舞台は", "表舞台", "だった。"]
    assert [span.kind for span in first.text_spans] == ["text", "ruby", "text"]
    assert first.publisher_ruby == ["ch-0001-b-0004-r-0001"]
    assert second.publisher_ruby == ["ch-0001-b-0004-r-0002"]
    assert third.publisher_ruby == ["ch-0001-b-0004-r-0003"]
    assert "おもてぶたい" not in "".join(span.text for span in first.text_spans)
    for sentence in (first, second, third):
        assert "".join(span.text for span in sentence.text_spans) == sentence.text
        assert sentence.text_spans[0].start == sentence.start
        assert sentence.text_spans[-1].end == sentence.end


def test_validation_rejects_duplicate_ids_and_invalid_spans(extracted_fixture):
    chapter = extracted_fixture.chapters[0]
    block = chapter.blocks[0]
    duplicate = replace(block.sentences[0], id=block.id)
    bad_book = replace(
        extracted_fixture,
        chapters=[
            replace(chapter, blocks=[replace(block, sentences=[duplicate])]),
            *extracted_fixture.chapters[1:],
        ],
    )
    with pytest.raises(BookAnalysisError, match="Duplicate canonical ID"):
        validate_book(bad_book)

    bad_span = replace(block.sentences[0].text_spans[0], end=len(block.text) + 1)
    bad_book = replace(
        extracted_fixture,
        chapters=[
            replace(
                chapter,
                blocks=[
                    replace(
                        block,
                        sentences=[replace(block.sentences[0], text_spans=[bad_span])],
                    )
                ],
            ),
            *extracted_fixture.chapters[1:],
        ],
    )
    with pytest.raises(BookAnalysisError, match="Invalid or overlapping text spans"):
        validate_book(bad_book)

    sentence = block.sentences[0]
    overlapping = replace(sentence.text_spans[0], start=sentence.start + 1)
    bad_book = replace(
        extracted_fixture,
        chapters=[
            replace(
                chapter,
                blocks=[
                    replace(
                        block,
                        sentences=[replace(sentence, text_spans=[overlapping])],
                    )
                ],
            ),
            *extracted_fixture.chapters[1:],
        ],
    )
    with pytest.raises(BookAnalysisError, match="Invalid or overlapping text spans"):
        validate_book(bad_book)


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
    assert payload["schema_version"] == 2
    assert payload["chapters"][0]["blocks"][3]["source_anchor"] == "publisher-ruby-cases"
    sentence = payload["chapters"][0]["blocks"][3]["sentences"][0]
    assert sentence["id"] == "ch-0001-b-0004-s-0001"
    assert (sentence["text"], sentence["start"], sentence["end"]) == (
        "舞台は表舞台だった。",
        0,
        10,
    )
    assert [span["text"] for span in sentence["text_spans"]] == [
        "舞台は",
        "表舞台",
        "だった。",
    ]
    assert sentence["text_spans"][1]["publisher_ruby_id"] == (
        "ch-0001-b-0004-r-0001"
    )


def test_fixture_matches_complete_schema_v2_golden(tmp_path):
    epub = tmp_path / "fixture.epub"
    build_fixture(epub)
    actual = serialize_book(extract_book(epub))
    expected = GOLDEN_BOOK.read_text(encoding="utf-8")
    assert actual == expected
    assert json.loads(actual) == json.loads(expected)


def test_complete_fixture_invariants(extracted_fixture):
    identifiers = []
    ruby_ids = set()
    referenced_ruby_ids = []
    for chapter in extracted_fixture.chapters:
        identifiers.append(chapter.id)
        assert chapter.text == "\n".join(block.text for block in chapter.blocks)
        for block in chapter.blocks:
            identifiers.append(block.id)
            for ruby in block.publisher_ruby:
                identifiers.append(ruby.id)
                ruby_ids.add(ruby.id)
                assert block.text[ruby.start : ruby.end] == ruby.surface
            previous_end = 0
            for sentence in block.sentences:
                identifiers.append(sentence.id)
                assert previous_end <= sentence.start < sentence.end <= len(block.text)
                assert block.text[sentence.start : sentence.end] == sentence.text
                assert "".join(span.text for span in sentence.text_spans) == sentence.text
                assert sentence.publisher_ruby == [
                    span.publisher_ruby_id
                    for span in sentence.text_spans
                    if span.publisher_ruby_id is not None
                ]
                previous_span_end = sentence.start
                for span in sentence.text_spans:
                    identifiers.append(span.id)
                    assert span.start == previous_span_end
                    assert block.text[span.start : span.end] == span.text
                    previous_span_end = span.end
                    if span.publisher_ruby_id is not None:
                        referenced_ruby_ids.append(span.publisher_ruby_id)
                assert previous_span_end == sentence.end
                previous_end = sentence.end
    assert len(identifiers) == len(set(identifiers))
    assert set(referenced_ruby_ids) == ruby_ids
    assert len(referenced_ruby_ids) == len(set(referenced_ruby_ids))


@pytest.mark.parametrize("href", ["../../outside.xhtml", "/absolute.xhtml", "..\\outside.xhtml"])
def test_rejects_unsafe_manifest_paths(href):
    with pytest.raises(BookAnalysisError, match="Unsafe EPUB archive path"):
        _resolve_archive_path("EPUB/package.opf", href)
