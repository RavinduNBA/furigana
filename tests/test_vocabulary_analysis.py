from dataclasses import replace
import json
from pathlib import Path

import pytest

from furiganalyse.book_analysis import extract_book
from furiganalyse.vocabulary_analysis import (
    SCHEMA_VERSION,
    VocabularyAnalysisError,
    _segment_tokens,
    _single_token_lookup_allowed,
    analyze_vocabulary,
    serialize_vocabulary_report,
    validate_vocabulary_report,
    write_vocabulary_report,
)
from tests.phase0_epub import build_fixture

GOLDEN_DIR = Path(__file__).parent / "phase3_golden"
GOLDEN_REPORT = GOLDEN_DIR / "vocabulary-v1.json"
REVIEWED_CASES = GOLDEN_DIR / "review-cases-v1.json"


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


def test_particle_is_not_eligible_for_standalone_dictionary_study():
    from furiganalyse.vocabulary_analysis import VocabularyCandidate

    surface, lemma, reading, part_of_speech, _, _ = next(
        value for value in _segment_tokens("本書に掲載される", 0) if value[0] == "に"
    )
    candidate = VocabularyCandidate(
        id="particle-candidate",
        token_id="particle-token",
        surface=surface,
        lemma=lemma,
        reading=reading,
        part_of_speech=part_of_speech,
        chapter_id="chapter",
        block_id="block",
        sentence_id="sentence",
        sentence_start=0,
        sentence_end=1,
        block_start=0,
        block_end=1,
        reading_source="tokenizer",
        publisher_ruby_id=None,
    )

    assert part_of_speech.startswith("助詞")
    assert not _single_token_lookup_allowed(candidate)


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


def test_fixture_matches_complete_vocabulary_golden(analyzed_fixture):
    _, report = analyzed_fixture
    actual = serialize_vocabulary_report(report)
    expected = GOLDEN_REPORT.read_text(encoding="utf-8")
    assert actual == expected
    assert json.loads(actual) == json.loads(expected)


def test_manually_reviewed_vocabulary_cases(analyzed_fixture):
    _, report = analyzed_fixture
    reviewed = json.loads(REVIEWED_CASES.read_text(encoding="utf-8"))
    tokens = {token.id: token for token in report.tokens}
    candidate_token_ids = {candidate.token_id for candidate in report.candidates}

    assert reviewed["schema_version"] == report.schema_version
    assert reviewed["expected_counts"] == {
        "tokens": len(report.tokens),
        "candidates": len(report.candidates),
    }
    for case in reviewed["cases"]:
        token = tokens[case["token_id"]]
        for field, expected in case["token"].items():
            assert getattr(token, field) == expected
        assert (token.id in candidate_token_ids) is case["is_candidate"]

    assert [
        (token[0], token[1], token[2])
        for token in _segment_tokens(reviewed["ipadic_split"]["input"], 0)
    ] == [tuple(values) for values in reviewed["ipadic_split"]["tokens"]]


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


def test_inflected_word_with_ruby_stem_has_dictionary_lemma(tmp_path):
    from furiganalyse.book_analysis import BookAnalysis, BookChapter, BookBlock, BookSentence, PublisherRubySpan, TextSpan
    from furiganalyse.jmdict import SqliteJmdictProvider, JmdictQuery

    # Sentence: 能力を持った警察官 (持 in ruby span)
    text = "能力を持った警察官"
    ruby_span = PublisherRubySpan(
        id="ch1-b1-r0001",
        surface="持",
        reading="も",
        source="publisher",
        start=3,
        end=4,
        source_anchor=None,
    )
    sentence = BookSentence(
        id="ch1-b1-s0001",
        text=text,
        start=0,
        end=len(text),
        text_spans=[
            TextSpan(id="ch1-b1-s0001-span-1", text="能力を", kind="text", source="body", start=0, end=3, publisher_ruby_id=None),
            TextSpan(id="ch1-b1-s0001-span-2", text="持", kind="ruby", source="publisher", start=3, end=4, publisher_ruby_id="ch1-b1-r0001"),
            TextSpan(id="ch1-b1-s0001-span-3", text="った警察官", kind="text", source="body", start=4, end=len(text), publisher_ruby_id=None),
        ],
        publisher_ruby=["ch1-b1-r0001"],
    )
    block = BookBlock(
        id="ch1-b1",
        text=text,
        source_anchor=None,
        publisher_ruby=[ruby_span],
        sentences=[sentence],
    )
    chapter = BookChapter(
        id="ch1",
        spine_index=0,
        source_path="ch1.xhtml",
        text=text,
        blocks=[block],
    )
    book = BookAnalysis(
        schema_version=2,
        book_id="urn:uuid:test-inflected-ruby",
        package_path="content.opf",
        chapters=[chapter],
    )

    report = analyze_vocabulary(book)
    # Verify token for 持っ has lemma '持つ' and associated publisher_ruby_id
    motsu_tokens = [t for t in report.tokens if t.surface == "持っ"]
    assert len(motsu_tokens) == 1
    assert motsu_tokens[0].lemma == "持つ"
    assert motsu_tokens[0].part_of_speech.startswith("動詞")
    assert motsu_tokens[0].publisher_ruby_id == "ch1-b1-r0001"

    # Verify JMdict lookup succeeds for this candidate
    jmdict = SqliteJmdictProvider("data/edrdg/JMdict.sqlite")
    q = JmdictQuery(
        surface=motsu_tokens[0].surface,
        lemma=motsu_tokens[0].lemma,
        reading=motsu_tokens[0].reading,
        part_of_speech=motsu_tokens[0].part_of_speech,
    )
    matches = jmdict.lookup(q)
    assert len(matches) >= 1
    assert any("hold" in s.glosses[0] or "carry" in s.glosses[0] or "have" in s.glosses[0] for s in matches[0].senses)
    jmdict.close()

