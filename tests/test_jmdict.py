from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from furiganalyse.book_analysis import (
    BookAnalysis,
    BookBlock,
    BookChapter,
    BookSentence,
    PublisherRubySpan,
    TextSpan,
    extract_book,
)
from furiganalyse.jmdict import (
    JmdictQuery,
    SqliteJmdictProvider,
    build_jmdict_index,
    parse_jmdict,
)
from furiganalyse.vocabulary_analysis import (
    VocabularyAnalysisError,
    ExpressionEnrichedVocabularyReport,
    analyze_vocabulary,
    enrich_vocabulary_report,
    serialize_vocabulary_report,
    validate_enriched_report,
)
from tests.phase0_epub import build_fixture

FIXTURE = Path(__file__).parent / "fixtures" / "jmdict-mini.xml"
EXPRESSION_FIXTURE = Path(__file__).parent / "fixtures" / "jmdict-expressions-mini.xml"
GOLDEN_DIR = Path(__file__).parent / "phase3_golden"
GOLDEN_REPORT = GOLDEN_DIR / "vocabulary-jmdict-v2.json"
REVIEWED_CASES = GOLDEN_DIR / "jmdict-review-cases-v2.json"
EXPRESSION_GOLDEN_REPORT = (
    GOLDEN_DIR / "vocabulary-jmdict-expressions-v3.json"
)
EXPRESSION_REVIEWED_CASES = GOLDEN_DIR / "expression-review-cases-v3.json"


@pytest.fixture
def provider(tmp_path):
    index = tmp_path / "jmdict.sqlite3"
    build_jmdict_index(FIXTURE, index)
    value = SqliteJmdictProvider(index)
    yield value
    value.close()


@pytest.fixture
def expression_provider(tmp_path):
    index = tmp_path / "jmdict-expressions.sqlite3"
    build_jmdict_index(EXPRESSION_FIXTURE, index)
    value = SqliteJmdictProvider(index)
    yield value
    value.close()


def expression_book(sentences, publisher_span=None):
    block_text = "".join(sentences)
    sentence_records = []
    offset = 0
    ruby_records = []
    for sentence_index, text in enumerate(sentences, start=1):
        sentence_id = f"ch-expr-b-0001-s-{sentence_index:04d}"
        spans = []
        ruby_ids = []
        if publisher_span and sentence_index == 1:
            start, end, reading = publisher_span
            ruby_id = "ch-expr-b-0001-r-0001"
            pieces = [
                (0, start, None),
                (start, end, ruby_id),
                (end, len(text), None),
            ]
            for span_index, (piece_start, piece_end, ruby) in enumerate(
                pieces, start=1
            ):
                if piece_start == piece_end:
                    continue
                spans.append(
                    TextSpan(
                        id=f"{sentence_id}-span-{span_index:04d}",
                        text=text[piece_start:piece_end],
                        kind="publisher_ruby" if ruby else "text",
                        source="publisher" if ruby else "canonical",
                        start=offset + piece_start,
                        end=offset + piece_end,
                        publisher_ruby_id=ruby,
                    )
                )
            ruby_records.append(
                PublisherRubySpan(
                    id=ruby_id,
                    surface=text[start:end],
                    reading=reading,
                    source="publisher",
                    start=offset + start,
                    end=offset + end,
                    source_anchor="expression-ruby",
                )
            )
            ruby_ids = [ruby_id]
        else:
            spans.append(
                TextSpan(
                    id=f"{sentence_id}-span-0001",
                    text=text,
                    kind="text",
                    source="canonical",
                    start=offset,
                    end=offset + len(text),
                    publisher_ruby_id=None,
                )
            )
        sentence_records.append(
            BookSentence(
                id=sentence_id,
                text=text,
                start=offset,
                end=offset + len(text),
                text_spans=spans,
                publisher_ruby=ruby_ids,
            )
        )
        offset += len(text)
    block = BookBlock(
        id="ch-expr-b-0001",
        text=block_text,
        source_anchor="expressions",
        publisher_ruby=ruby_records,
        sentences=sentence_records,
    )
    chapter = BookChapter(
        id="ch-expr",
        spine_index=0,
        source_path="EPUB/text/expressions.xhtml",
        text=block_text,
        blocks=[block],
    )
    return BookAnalysis(
        schema_version=2,
        book_id="expression-fixture",
        package_path="EPUB/package.opf",
        chapters=[chapter],
    )


def query(surface, lemma=None, reading=None, pos=None, publisher=False):
    return JmdictQuery(
        surface=surface,
        lemma=lemma or surface,
        reading=reading,
        part_of_speech=pos,
        publisher_reading=publisher,
    )


def test_parses_entries_senses_restrictions_and_provenance():
    provenance, entries = parse_jmdict(FIXTURE)
    assert provenance.dataset_id == "furiganalyse-synthetic-jmdict"
    assert provenance.dataset_version == "2026-08-16"
    assert provenance.format_version == 1
    assert provenance.sha256 == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert [entry.sequence for entry in entries] == list(range(1001, 1008))

    entry = entries[4]
    assert entry.written_forms == ["上手", "巧い"]
    assert [reading.written_restrictions for reading in entry.readings] == [
        ["上手"],
        ["巧い"],
    ]
    assert [sense.id for sense in entry.senses] == [
        "jmdict-1005-sense-0001",
        "jmdict-1005-sense-0002",
    ]
    assert entry.senses[0].written_restrictions == ["上手"]
    assert entry.senses[0].reading_restrictions == ["じょうず"]


def test_exact_written_lookup_preserves_multiple_senses(provider):
    matches = provider.lookup(query("言葉", reading="コトバ", pos="名詞,一般"))
    assert [match.sequence for match in matches] == [1001]
    assert matches[0].matched_by == "lemma"
    assert [sense.glosses for sense in matches[0].senses] == [
        ["language", "word"],
        ["expression"],
    ]


def test_inflected_verb_uses_lemma_without_rejecting_inflected_reading(provider):
    matches = provider.lookup(
        query("振り返っ", lemma="振り返る", reading="フリカエッ", pos="動詞,自立")
    )
    assert [match.sequence for match in matches] == [1002]
    assert matches[0].matched_by == "lemma"
    assert matches[0].senses[0].parts_of_speech == ["v5r"]


def test_kana_only_entry_lookup(provider):
    matches = provider.lookup(query("ありがとう", reading="アリガトウ"))
    assert [match.sequence for match in matches] == [1003]
    assert matches[0].written_forms == []
    assert matches[0].readings[0].no_kanji is True


def test_reading_and_written_form_restrictions(provider):
    matches = provider.lookup(query("開く", reading="ヒラク", pos="動詞,自立"))
    assert [reading.text for reading in matches[0].readings] == ["ひらく"]
    assert provider.lookup(query("開く", reading="アク", pos="動詞,自立")) == []


def test_sense_written_reading_and_pos_restrictions(provider):
    noun = provider.lookup(query("上手", reading="ジョウズ", pos="名詞,一般"))
    assert [sense.id for sense in noun[0].senses] == ["jmdict-1005-sense-0001"]
    assert provider.lookup(query("上手", reading="ジョウズ", pos="形容詞,自立")) == []


def test_no_match(provider):
    assert provider.lookup(query("未知語", reading="ミチゴ")) == []


def test_publisher_reading_is_authoritative(provider):
    matches = provider.lookup(
        query(
            "表舞台",
            reading="おもてぶたい",
            publisher=True,
        )
    )
    assert [match.sequence for match in matches] == [1006]
    assert matches[0].readings[0].text == "おもてぶたい"


def test_publisher_ruby_without_reading_does_not_invent_authority(provider, tmp_path):
    epub = tmp_path / "fixture.epub"
    build_fixture(epub)
    base = analyze_vocabulary(extract_book(epub))
    candidates = [
        replace(candidate, reading=None)
        if candidate.surface == "表舞台"
        else candidate
        for candidate in base.candidates
    ]

    enriched = enrich_vocabulary_report(replace(base, candidates=candidates), provider)

    matching = [
        match
        for match in enriched.dictionary_matches
        if next(
            candidate
            for candidate in candidates
            if candidate.id == match.candidate_id
        ).surface == "表舞台"
    ]
    assert matching


def test_enrichment_is_optional_ordered_and_deterministic(provider, tmp_path):
    epub = tmp_path / "fixture.epub"
    build_fixture(epub)
    base = analyze_vocabulary(extract_book(epub))
    enriched = enrich_vocabulary_report(base, provider)
    second = enrich_vocabulary_report(base, provider)

    assert base.schema_version == 1
    assert enriched.schema_version == 2
    assert enriched.tokens == base.tokens
    assert enriched.candidates == base.candidates
    assert serialize_vocabulary_report(enriched) == serialize_vocabulary_report(second)
    by_candidate = {
        match.candidate_id: match for match in enriched.dictionary_matches
    }
    word = next(candidate for candidate in base.candidates if candidate.surface == "言葉")
    verb = next(
        candidate for candidate in base.candidates if candidate.surface == "振り返っ"
    )
    ruby = next(
        candidate
        for candidate in base.candidates
        if candidate.publisher_ruby_id == "ch-0001-b-0004-r-0001"
    )
    assert [entry.sequence for entry in by_candidate[word.id].entries] == [1001]
    assert [entry.sequence for entry in by_candidate[verb.id].entries] == [1002]
    assert [entry.sequence for entry in by_candidate[ruby.id].entries] == [1006]


def test_enriched_fixture_matches_complete_golden(provider, tmp_path):
    epub = tmp_path / "fixture.epub"
    build_fixture(epub)
    report = enrich_vocabulary_report(
        analyze_vocabulary(extract_book(epub)), provider
    )
    actual = serialize_vocabulary_report(report)
    expected = GOLDEN_REPORT.read_text(encoding="utf-8")
    assert actual == expected
    assert json.loads(actual) == json.loads(expected)


def test_manually_reviewed_dictionary_cases(provider, tmp_path):
    reviewed = json.loads(REVIEWED_CASES.read_text(encoding="utf-8"))
    epub = tmp_path / "fixture.epub"
    build_fixture(epub)
    report = enrich_vocabulary_report(
        analyze_vocabulary(extract_book(epub)), provider
    )

    assert reviewed["schema_version"] == report.schema_version
    assert reviewed["dictionary"] == {
        "dataset_id": report.dictionary.dataset_id,
        "dataset_version": report.dictionary.dataset_version,
        "format_version": report.dictionary.format_version,
        "sha256": report.dictionary.sha256,
    }
    assert reviewed["expected_counts"] == {
        "tokens": len(report.tokens),
        "candidates": len(report.candidates),
        "dictionary_matches": len(report.dictionary_matches),
        "matched_entries": sum(len(match.entries) for match in report.dictionary_matches),
        "matched_senses": sum(
            len(entry.senses)
            for match in report.dictionary_matches
            for entry in match.entries
        ),
    }
    actual_matches = []
    for match in report.dictionary_matches:
        actual_matches.append(
            {
                "candidate_id": match.candidate_id,
                "entry_ids": [entry.entry_id for entry in match.entries],
                "match_id": match.id,
                "sense_ids": [
                    sense.id
                    for entry in match.entries
                    for sense in entry.senses
                ],
            }
        )
    assert actual_matches == reviewed["report_matches"]

    for case in reviewed["lookup_cases"]:
        values = case["query"]
        matches = provider.lookup(
            query(
                values["surface"],
                lemma=values.get("lemma"),
                reading=values.get("reading"),
                pos=values.get("part_of_speech"),
                publisher=values.get("publisher_reading", False),
            )
        )
        assert [match.sequence for match in matches] == case["sequences"]
        if "sense_ids" in case:
            assert [
                sense.id for match in matches for sense in match.senses
            ] == case["sense_ids"]
        if "readings" in case:
            assert [
                reading.text for match in matches for reading in match.readings
            ] == case["readings"]
        if "written_forms" in case:
            assert matches[0].written_forms == case["written_forms"]


def test_enriched_validation_rejects_unstable_ids_order_and_invalid_content(
    provider, tmp_path
):
    epub = tmp_path / "fixture.epub"
    build_fixture(epub)
    report = enrich_vocabulary_report(
        analyze_vocabulary(extract_book(epub)), provider
    )
    first, second = report.dictionary_matches[:2]

    with pytest.raises(VocabularyAnalysisError, match="Duplicate dictionary match ID"):
        validate_enriched_report(
            replace(report, dictionary_matches=[first, replace(second, id=first.id)])
        )
    with pytest.raises(VocabularyAnalysisError, match="Unordered dictionary matches"):
        validate_enriched_report(
            replace(report, dictionary_matches=[second, first])
        )
    bad_entry = replace(first.entries[0], entry_id="unstable")
    with pytest.raises(VocabularyAnalysisError, match="Unstable dictionary entry ID"):
        validate_enriched_report(
            replace(
                report,
                dictionary_matches=[replace(first, entries=[bad_entry])],
            )
        )
    bad_sense = replace(first.entries[0].senses[0], glosses=[])
    bad_entry = replace(first.entries[0], senses=[bad_sense])
    with pytest.raises(VocabularyAnalysisError, match="no English gloss"):
        validate_enriched_report(
            replace(
                report,
                dictionary_matches=[replace(first, entries=[bad_entry])],
            )
        )
    with pytest.raises(VocabularyAnalysisError, match="Invalid dictionary provenance"):
        validate_enriched_report(
            replace(report, dictionary=replace(report.dictionary, sha256="invalid"))
        )


def expression_report(provider, *sentences, publisher_span=None):
    base = analyze_vocabulary(
        expression_book(list(sentences), publisher_span=publisher_span)
    )
    report = enrich_vocabulary_report(
        base, provider, include_expressions=True
    )
    assert isinstance(report, ExpressionEnrichedVocabularyReport)
    return report


def test_expression_lookup_is_longest_first_ordered_and_deterministic(
    expression_provider,
):
    first = expression_report(
        expression_provider, "気がする。", "仕方がない。"
    )
    second = expression_report(
        expression_provider, "気がする。", "仕方がない。"
    )
    assert serialize_vocabulary_report(first) == serialize_vocabulary_report(second)
    assert first.schema_version == 3
    assert [(value.surface, value.normalized_form) for value in first.expressions] == [
        ("気がする", "気がする"),
        ("仕方がない", "仕方がない"),
    ]
    assert [
        [entry.sequence for entry in match.entries]
        for match in first.expression_dictionary_matches
    ] == [[1009], [1010]]
    assert [
        sense.id
        for sense in first.expression_dictionary_matches[0].entries[0].senses
    ] == ["jmdict-1009-sense-0001", "jmdict-1009-sense-0002"]
    assert all(
        expression.id == f"{expression.sentence_id}-expr-0001"
        for expression in first.expressions
    )


def test_expression_normalizes_inflected_final_content_token(expression_provider):
    report = expression_report(expression_provider, "気がした。")
    assert len(report.expressions) == 1
    expression = report.expressions[0]
    assert expression.surface == "気がした"
    assert expression.normalized_form == "気がする"
    assert [report.tokens[index].surface for index in range(4)] == [
        "気", "が", "し", "た"
    ]
    assert len(expression.token_ids) == 4
    assert report.expression_dictionary_matches[0].entries[0].sequence == 1009


@pytest.mark.parametrize(
    ("sentences", "forbidden_sequence"),
    [
        (["気が、する。"], 1012),
        (["気がEnglishする。"], 1013),
        (["気が する。"], 1017),
        (["気が", "する"], 1009),
    ],
)
def test_expression_does_not_cross_boundaries(
    expression_provider, sentences, forbidden_sequence
):
    report = expression_report(expression_provider, *sentences)
    sequences = {
        entry.sequence
        for match in report.expression_dictionary_matches
        for entry in match.entries
    }
    assert forbidden_sequence not in sequences


def test_expression_does_not_cross_publisher_ruby(expression_provider):
    report = expression_report(
        expression_provider,
        "気が表舞台する。",
        publisher_span=(2, 5, "おもてぶたい"),
    )
    sequences = {
        entry.sequence
        for match in report.expression_dictionary_matches
        for entry in match.entries
    }
    assert 1014 not in sequences


def test_expression_lookup_enforces_written_reading_and_pos_restrictions(
    expression_provider,
):
    skilled = expression_provider.lookup(
        query("上手になる", reading="ジョウズニナル", pos="動詞,自立")
    )
    assert [entry.sequence for entry in skilled] == [1015]
    assert [reading.text for reading in skilled[0].readings] == ["じょうずになる"]
    assert [sense.id for sense in skilled[0].senses] == [
        "jmdict-1015-sense-0001"
    ]
    assert expression_provider.lookup(
        query("上手になる", reading="ウマイニナル", pos="動詞,自立")
    ) == []
    assert [
        entry.sequence
        for entry in expression_provider.lookup(
            query("気がする", pos="動詞,自立")
        )
    ] == [1009]


def test_expression_no_match_and_schema_v2_single_matches_remain(expression_provider):
    report = expression_report(expression_provider, "未知表現。")
    assert report.expressions == []
    assert report.expression_dictionary_matches == []

    epub_report = enrich_vocabulary_report(
        analyze_vocabulary(expression_book(["言葉。振り返った。"])),
        expression_provider,
    )
    assert epub_report.schema_version == 2
    assert not hasattr(epub_report, "expressions")


def test_expression_validation_rejects_bad_references_and_overlap(
    expression_provider,
):
    report = expression_report(expression_provider, "気がする。仕方がない。")
    first, second = report.expressions
    with pytest.raises(VocabularyAnalysisError, match="Invalid expression token references"):
        validate_enriched_report(
            replace(report, expressions=[replace(first, token_ids=["missing"])])
        )
    overlapping = replace(
        second,
        sentence_id=first.sentence_id,
        token_ids=first.token_ids,
        candidate_ids=first.candidate_ids,
    )
    with pytest.raises(VocabularyAnalysisError):
        validate_enriched_report(replace(report, expressions=[first, overlapping]))


def test_expression_enriched_legal_fixture_matches_complete_golden(
    expression_provider, tmp_path
):
    epub = tmp_path / "fixture.epub"
    build_fixture(epub)
    report = enrich_vocabulary_report(
        analyze_vocabulary(extract_book(epub)),
        expression_provider,
        include_expressions=True,
    )
    actual = serialize_vocabulary_report(report)
    expected = EXPRESSION_GOLDEN_REPORT.read_text(encoding="utf-8")
    assert actual == expected
    assert json.loads(actual) == json.loads(expected)


def test_manually_reviewed_expression_cases(expression_provider, tmp_path):
    reviewed = json.loads(EXPRESSION_REVIEWED_CASES.read_text(encoding="utf-8"))
    epub = tmp_path / "fixture.epub"
    build_fixture(epub)
    report = enrich_vocabulary_report(
        analyze_vocabulary(extract_book(epub)),
        expression_provider,
        include_expressions=True,
    )
    assert reviewed["schema_version"] == report.schema_version
    assert reviewed["dictionary"] == {
        "dataset_id": report.dictionary.dataset_id,
        "dataset_version": report.dictionary.dataset_version,
        "format_version": report.dictionary.format_version,
        "sha256": report.dictionary.sha256,
    }
    assert reviewed["expected_counts"] == {
        "tokens": len(report.tokens),
        "candidates": len(report.candidates),
        "dictionary_matches": len(report.dictionary_matches),
        "expressions": len(report.expressions),
        "expression_dictionary_matches": len(
            report.expression_dictionary_matches
        ),
    }
    expression = report.expressions[0]
    match = report.expression_dictionary_matches[0]
    actual = {
        "block_end": expression.block_end,
        "block_id": expression.block_id,
        "block_start": expression.block_start,
        "candidate_ids": expression.candidate_ids,
        "chapter_id": expression.chapter_id,
        "entry_ids": [entry.entry_id for entry in match.entries],
        "expression_id": expression.id,
        "glosses": [
            sense.glosses for entry in match.entries for sense in entry.senses
        ],
        "match_id": match.id,
        "normalized_form": expression.normalized_form,
        "sentence_end": expression.sentence_end,
        "sentence_id": expression.sentence_id,
        "sentence_start": expression.sentence_start,
        "sense_ids": [
            sense.id for entry in match.entries for sense in entry.senses
        ],
        "surface": expression.surface,
        "token_ids": expression.token_ids,
    }
    assert actual == reviewed["integration_expression"]

    longest = expression_report(expression_provider, "気がする。")
    longest_case = reviewed["focused_cases"]["longest_match"]
    assert longest.expressions[0].surface == longest_case["surface"]
    assert [
        entry.sequence
        for entry in longest.expression_dictionary_matches[0].entries
    ] == [longest_case["selected_sequence"]]
    assert longest_case["rejected_overlap_sequence"] not in {
        entry.sequence
        for item in longest.expression_dictionary_matches
        for entry in item.entries
    }
    assert [
        sense.id
        for sense in longest.expression_dictionary_matches[0].entries[0].senses
    ] == longest_case["sense_ids"]

    inflected = expression_report(expression_provider, "気がした。")
    inflected_case = reviewed["focused_cases"]["inflected_final_token"]
    assert {
        "surface": inflected.expressions[0].surface,
        "normalized_form": inflected.expressions[0].normalized_form,
        "sequence": inflected.expression_dictionary_matches[0].entries[0].sequence,
    } == inflected_case

    for case in reviewed["boundary_cases"]:
        boundary = expression_report(expression_provider, *case["sentences"])
        assert case["forbidden_sequence"] not in {
            entry.sequence
            for item in boundary.expression_dictionary_matches
            for entry in item.entries
        }

    publisher_case = reviewed["focused_cases"]["publisher_boundary"]
    publisher = expression_report(
        expression_provider,
        publisher_case["surface"],
        publisher_span=(2, 5, "おもてぶたい"),
    )
    assert publisher_case["forbidden_sequence"] not in {
        entry.sequence
        for item in publisher.expression_dictionary_matches
        for entry in item.entries
    }

    no_match_case = reviewed["focused_cases"]["no_match"]
    no_match_report = expression_report(
        expression_provider, no_match_case["surface"]
    )
    assert len(no_match_report.expressions) == no_match_case["expressions"]

    restriction_case = reviewed["focused_cases"]["restrictions"]
    accepted = expression_provider.lookup(
        query(
            restriction_case["surface"],
            reading="ジョウズニナル",
            pos="動詞,自立",
        )
    )
    assert [reading.text for reading in accepted[0].readings] == [
        restriction_case["accepted_reading"]
    ]
    assert [sense.id for sense in accepted[0].senses] == [
        restriction_case["accepted_sense_id"]
    ]
    assert expression_provider.lookup(
        query(
            restriction_case["surface"],
            reading="ウマイニナル",
            pos="動詞,自立",
        )
    ) == []
