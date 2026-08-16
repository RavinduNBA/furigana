from dataclasses import replace

import pytest

from furiganalyse.book_analysis import extract_book
from furiganalyse.vocabulary_analysis import (
    SCHEMA_VERSION,
    VocabularyAnalysisError,
    _segment_tokens,
    analyze_vocabulary,
    serialize_vocabulary_report,
    validate_vocabulary_report,
    write_vocabulary_report,
)
from tests.phase0_epub import build_fixture


@pytest.fixture
def analyzed_fixture(tmp_path):
    epub = tmp_path / "fixture.epub"
    build_fixture(epub)
    book = extract_book(epub)
    return book, analyze_vocabulary(book)


def test_report_has_versioned_deterministic_provenance(analyzed_fixture):
    book, first = analyzed_fixture
    second = analyze_vocabulary(book)
    assert first.schema_version == SCHEMA_VERSION == 1
    assert first.book_id == book.book_id
    assert first.source_book_schema_version == book.schema_version
    assert first.tokenizer.name == "MeCab"
    assert first.tokenizer.version == "1.0.12"
    assert first.tokenizer.wrapper == "furigana"
    assert first.tokenizer.wrapper_version == "0.5"
    assert first.tokenizer.dictionary == "MeCab system dictionary"
    assert first.tokenizer.dictionary_version == "102"
    assert serialize_vocabulary_report(first) == serialize_vocabulary_report(second)


def test_tokens_have_stable_context_and_exact_offsets(analyzed_fixture):
    book, report = analyzed_fixture
    sentence_by_id = {}
    block_by_id = {}
    for chapter in book.chapters:
        for block in chapter.blocks:
            block_by_id[block.id] = block
            for sentence in block.sentences:
                sentence_by_id[sentence.id] = sentence

    assert len({token.id for token in report.tokens}) == len(report.tokens)
    for token in report.tokens:
        sentence = sentence_by_id[token.sentence_id]
        block = block_by_id[token.block_id]
        assert sentence.text[token.sentence_start : token.sentence_end] == token.surface
        assert block.text[token.block_start : token.block_end] == token.surface

    ids = [token.id for token in report.tokens if token.sentence_id == "ch-0001-b-0002-s-0001"]
    assert ids == [
        f"ch-0001-b-0002-s-0001-tok-{index:04d}"
        for index in range(1, len(ids) + 1)
    ]


def test_normalizes_inflected_verb_to_lemma(analyzed_fixture):
    _, report = analyzed_fixture
    token = next(token for token in report.tokens if token.surface == "振り返っ")
    assert token.lemma == "振り返る"
    assert token.reading == "フリカエッ"
    assert token.part_of_speech == "動詞,自立"


def test_excludes_symbols_and_latin_only_tokens_from_candidates(analyzed_fixture):
    _, report = analyzed_fixture
    candidate_token_ids = {candidate.token_id for candidate in report.candidates}
    excluded = [
        token
        for token in report.tokens
        if token.surface == "。" or token.surface == "English"
    ]
    assert {token.surface for token in excluded} == {"。", "English"}
    assert all(token.id not in candidate_token_ids for token in excluded)
    assert all(candidate.surface.strip() for candidate in report.candidates)


def test_publisher_ruby_is_one_authoritative_candidate(analyzed_fixture):
    _, report = analyzed_fixture
    candidates = [
        candidate
        for candidate in report.candidates
        if candidate.publisher_ruby_id == "ch-0001-b-0004-r-0001"
    ]
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.surface == candidate.lemma == "表舞台"
    assert candidate.reading == "おもてぶたい"
    assert candidate.reading_source == "publisher"
    assert candidate.part_of_speech is None
    assert all(token.surface != "おもてぶたい" for token in report.tokens)


def test_documents_ipadic_success_experience_split():
    tokens = list(_segment_tokens("成功体験", 0))
    assert [(token[0], token[1], token[2]) for token in tokens] == [
        ("成功", "成功", "セイコウ"),
        ("体験", "体験", "タイケン"),
    ]


def test_serialized_report_is_byte_deterministic(analyzed_fixture, tmp_path):
    _, report = analyzed_fixture
    first = tmp_path / "a" / "vocabulary.json"
    second = tmp_path / "b" / "vocabulary.json"
    write_vocabulary_report(report, first)
    write_vocabulary_report(report, second)
    assert first.read_bytes() == second.read_bytes()


def test_validation_rejects_duplicate_ids_invalid_offsets_and_overlap(analyzed_fixture):
    book, report = analyzed_fixture
    first, second = report.tokens[:2]
    duplicate = replace(second, id=first.id)
    with pytest.raises(VocabularyAnalysisError, match="Duplicate vocabulary ID"):
        validate_vocabulary_report(book, replace(report, tokens=[first, duplicate]))

    invalid = replace(first, sentence_end=10_000)
    with pytest.raises(VocabularyAnalysisError, match="Invalid token offsets"):
        validate_vocabulary_report(book, replace(report, tokens=[invalid]))

    same_sentence = [
        token for token in report.tokens if token.sentence_id == first.sentence_id
    ]
    overlapping = replace(
        same_sentence[1],
        sentence_start=same_sentence[0].sentence_start,
        block_start=same_sentence[0].block_start,
    )
    with pytest.raises(VocabularyAnalysisError, match="Token text mismatch|Overlapping"):
        validate_vocabulary_report(
            book, replace(report, tokens=[same_sentence[0], overlapping])
        )
