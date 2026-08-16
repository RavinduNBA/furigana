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
    TextSpan,
    extract_book,
)
from furiganalyse.jmnedict import (
    JmnedictQuery,
    SqliteJmnedictProvider,
    build_jmnedict_index,
    parse_jmnedict,
)
from furiganalyse.jmdict import (
    SqliteJmdictProvider,
    build_jmdict_index,
)
from furiganalyse.vocabulary_analysis import (
    NameEnrichedVocabularyReport,
    VocabularyAnalysisError,
    analyze_vocabulary,
    enrich_name_report,
    enrich_vocabulary_report,
    serialize_vocabulary_report,
    validate_name_report,
)
from tests.phase0_epub import build_fixture

FIXTURE = Path(__file__).parent / "fixtures" / "jmnedict-mini.xml"
EXPRESSION_FIXTURE = (
    Path(__file__).parent / "fixtures" / "jmdict-expressions-mini.xml"
)
GOLDEN_DIR = Path(__file__).parent / "phase3_golden"
GOLDEN_REPORT = GOLDEN_DIR / "vocabulary-jmnedict-v4.json"
REVIEWED_CASES = GOLDEN_DIR / "jmnedict-review-cases-v4.json"


@pytest.fixture
def provider(tmp_path):
    index = tmp_path / "jmnedict.sqlite3"
    build_jmnedict_index(FIXTURE, index)
    value = SqliteJmnedictProvider(index)
    yield value
    value.close()


@pytest.fixture
def expression_provider(tmp_path):
    index = tmp_path / "jmdict-expressions.sqlite3"
    build_jmdict_index(EXPRESSION_FIXTURE, index)
    value = SqliteJmdictProvider(index)
    yield value
    value.close()


def query(surface, reading=None, pos="名詞,固有名詞", publisher=False):
    return JmnedictQuery(
        surface=surface,
        reading=reading,
        part_of_speech=pos,
        publisher_reading=publisher,
    )


def book_with_text(text):
    sentence_id = "ch-name-b-0001-s-0001"
    span = TextSpan(
        id=f"{sentence_id}-span-0001",
        text=text,
        kind="text",
        source="canonical",
        start=0,
        end=len(text),
        publisher_ruby_id=None,
    )
    sentence = BookSentence(
        id=sentence_id,
        text=text,
        start=0,
        end=len(text),
        text_spans=[span],
        publisher_ruby=[],
    )
    block = BookBlock(
        id="ch-name-b-0001",
        text=text,
        source_anchor="names",
        publisher_ruby=[],
        sentences=[sentence],
    )
    chapter = BookChapter(
        id="ch-name",
        spine_index=0,
        source_path="EPUB/text/names.xhtml",
        text=text,
        blocks=[block],
    )
    return BookAnalysis(
        schema_version=2,
        book_id="name-fixture",
        package_path="EPUB/package.opf",
        chapters=[chapter],
    )


def combined_legal_report(tmp_path, dictionary_provider, name_provider):
    epub = tmp_path / "fixture.epub"
    build_fixture(epub)
    base = analyze_vocabulary(extract_book(epub))
    dictionary = enrich_vocabulary_report(
        base, dictionary_provider, include_expressions=True
    )
    return enrich_name_report(dictionary, name_provider)


def test_parses_name_types_translations_restrictions_and_provenance():
    provenance, entries = parse_jmnedict(FIXTURE)
    assert provenance.dataset_id == "furiganalyse-synthetic-jmnedict"
    assert provenance.dataset_version == "2026-08-16"
    assert provenance.format_version == 1
    assert provenance.sha256 == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert [entry.sequence for entry in entries] == list(range(2001, 2012))
    assert entries[0].translations[0].name_types == [
        "person",
        "female given name",
    ]
    assert entries[0].translations[0].translations == ["Yukino", "Yuki-no"]
    assert entries[-1].readings[0].written_restrictions == ["青木"]


@pytest.mark.parametrize(
    ("surface", "reading", "sequence", "name_type", "translation"),
    [
        ("雪乃", "ユキノ", 2001, "person", "Yukino"),
        ("東京", "トウキョウ", 2002, "place", "Tokyo"),
        ("架空社", "カクウシャ", 2003, "organization", "Fictional Corporation"),
    ],
)
def test_exact_name_types_and_kana_only_lookup(
    provider, surface, reading, sequence, name_type, translation
):
    matches = provider.lookup(query(surface, reading))
    assert [match.sequence for match in matches] == [sequence]
    assert name_type in matches[0].translations[0].name_types
    assert translation in matches[0].translations[0].translations


def test_kana_only_lookup_preserves_ordered_ambiguous_candidates(provider):
    matches = provider.lookup(query("ゆきの", "ユキノ"))
    assert [match.sequence for match in matches] == [2001, 2004]
    kana_only = matches[1]
    assert kana_only.written_forms == []
    assert kana_only.translations[0].name_types == ["female given name"]
    assert kana_only.translations[0].translations == ["Yukino"]


def test_ambiguous_entries_preserve_source_order(provider):
    matches = provider.lookup(query("春", "ハル"))
    assert [match.sequence for match in matches] == [2005, 2006]
    assert [
        match.translations[0].name_types for match in matches
    ] == [["given name"], ["surname"]]


def test_reading_restrictions_and_pos_compatibility(provider):
    accepted = provider.lookup(query("青木", "アオキ"))
    assert [match.sequence for match in accepted] == [2011]
    assert [reading.text for reading in accepted[0].readings] == ["あおき"]
    assert provider.lookup(query("青木", "セイジュ")) == []
    assert provider.lookup(
        query("言葉", "コトバ", pos="名詞,一般")
    ) == []


def test_no_match_and_publisher_reading_precedence(provider):
    assert provider.lookup(query("不存在", "フソンザイ")) == []
    matches = provider.lookup(
        query(
            "雪乃",
            "ゆきの",
            pos=None,
            publisher=True,
        )
    )
    assert [match.sequence for match in matches] == [2001]
    assert all(
        reading.text == "ゆきの"
        for match in matches
        for reading in match.readings
    )


def test_name_enrichment_uses_proper_pos_and_excludes_ordinary_vocabulary(provider):
    report = enrich_name_report(
        analyze_vocabulary(book_with_text("東京と言葉。")), provider
    )
    assert isinstance(report, NameEnrichedVocabularyReport)
    assert report.schema_version == 4
    assert [name.surface for name in report.name_occurrences] == ["東京"]
    assert report.name_occurrences[0].classification_evidence == (
        "tokenizer_proper_noun"
    )
    assert report.name_dictionary_matches[0].entries[0].sequence == 2002
    assert all(name.surface != "言葉" for name in report.name_occurrences)


def test_publisher_name_enrichment_is_ordered_and_deterministic(provider, tmp_path):
    epub = tmp_path / "fixture.epub"
    build_fixture(epub)
    base = analyze_vocabulary(extract_book(epub))
    first = enrich_name_report(base, provider)
    second = enrich_name_report(base, provider)
    assert serialize_vocabulary_report(first) == serialize_vocabulary_report(second)
    assert [name.surface for name in first.name_occurrences] == ["雪乃"]
    name = first.name_occurrences[0]
    assert name.reading == "ゆきの"
    assert name.publisher_ruby_id == "ch-0002-b-0002-r-0001"
    assert name.classification_evidence == "publisher_ruby"
    assert name.selection_reason == "publisher-reading-compatible"
    assert [entry.sequence for entry in first.name_dictionary_matches[0].entries] == [
        2001
    ]
    assert {diagnostic.reason for diagnostic in first.name_diagnostics} >= {
        "publisher-reading-mismatch-or-no-match"
    }


def test_name_validation_rejects_bad_ids_references_and_translations(
    provider, tmp_path
):
    epub = tmp_path / "fixture.epub"
    build_fixture(epub)
    report = enrich_name_report(
        analyze_vocabulary(extract_book(epub)), provider
    )
    occurrence = report.name_occurrences[0]
    with pytest.raises(VocabularyAnalysisError, match="Unstable name ID"):
        validate_name_report(
            replace(
                report,
                name_occurrences=[replace(occurrence, id="unstable")],
            )
        )
    entry = report.name_dictionary_matches[0].entries[0]
    translation = replace(entry.translations[0], translations=[])
    bad_entry = replace(entry, translations=[translation])
    with pytest.raises(VocabularyAnalysisError, match="Incomplete name translation"):
        validate_name_report(
            replace(
                report,
                name_dictionary_matches=[
                    replace(
                        report.name_dictionary_matches[0],
                        entries=[bad_entry],
                    )
                ],
            )
        )
    with pytest.raises(VocabularyAnalysisError, match="Invalid name dictionary provenance"):
        validate_name_report(
            replace(
                report,
                name_dictionary=replace(
                    report.name_dictionary, sha256="invalid"
                ),
            )
        )


def test_name_enriched_legal_fixture_matches_complete_golden(
    provider, expression_provider, tmp_path
):
    report = combined_legal_report(
        tmp_path, expression_provider, provider
    )
    actual = serialize_vocabulary_report(report)
    expected = GOLDEN_REPORT.read_text(encoding="utf-8")
    assert actual == expected
    assert json.loads(actual) == json.loads(expected)


def test_manually_reviewed_name_cases(provider, expression_provider, tmp_path):
    reviewed = json.loads(REVIEWED_CASES.read_text(encoding="utf-8"))
    report = combined_legal_report(
        tmp_path, expression_provider, provider
    )
    assert reviewed["schema_version"] == report.schema_version
    assert reviewed["name_dictionary"] == {
        "dataset_id": report.name_dictionary.dataset_id,
        "dataset_version": report.name_dictionary.dataset_version,
        "format_version": report.name_dictionary.format_version,
        "sha256": report.name_dictionary.sha256,
    }
    assert reviewed["expected_counts"] == {
        "tokens": len(report.tokens),
        "candidates": len(report.candidates),
        "dictionary_matches": len(report.dictionary_matches),
        "expressions": len(report.expressions),
        "name_occurrences": len(report.name_occurrences),
        "name_matches": len(report.name_dictionary_matches),
        "name_diagnostics": len(report.name_diagnostics),
    }
    occurrence = report.name_occurrences[0]
    match = report.name_dictionary_matches[0]
    assert reviewed["integration_name"] == {
        "id": occurrence.id,
        "candidate_id": occurrence.candidate_id,
        "token_id": occurrence.token_id,
        "surface": occurrence.surface,
        "reading": occurrence.reading,
        "publisher_ruby_id": occurrence.publisher_ruby_id,
        "classification_evidence": occurrence.classification_evidence,
        "selection_reason": occurrence.selection_reason,
        "sentence_start": occurrence.sentence_start,
        "sentence_end": occurrence.sentence_end,
        "block_start": occurrence.block_start,
        "block_end": occurrence.block_end,
        "entry_ids": [entry.entry_id for entry in match.entries],
        "name_types": [
            translation.name_types
            for entry in match.entries
            for translation in entry.translations
        ],
        "translations": [
            translation.translations
            for entry in match.entries
            for translation in entry.translations
        ],
    }
    assert reviewed["diagnostics"] == [
        {
            "candidate_id": diagnostic.candidate_id,
            "classification_evidence": diagnostic.classification_evidence,
            "reason": diagnostic.reason,
        }
        for diagnostic in report.name_diagnostics
    ]

    for case in reviewed["lookup_cases"]:
        values = case["query"]
        matches = provider.lookup(
            query(
                values["surface"],
                reading=values.get("reading"),
                pos=values.get("part_of_speech"),
                publisher=values.get("publisher_reading", False),
            )
        )
        assert [entry.sequence for entry in matches] == case["sequences"]
        if "name_types" in case:
            assert matches[0].translations[0].name_types == case["name_types"]
        if "translations" in case:
            assert (
                matches[0].translations[0].translations
                == case["translations"]
            )
