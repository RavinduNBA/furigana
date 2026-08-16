from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from furiganalyse.book_analysis import extract_book
from furiganalyse.jmdict import (
    JmdictQuery,
    SqliteJmdictProvider,
    build_jmdict_index,
    parse_jmdict,
)
from furiganalyse.vocabulary_analysis import (
    VocabularyAnalysisError,
    analyze_vocabulary,
    enrich_vocabulary_report,
    serialize_vocabulary_report,
    validate_enriched_report,
)
from tests.phase0_epub import build_fixture

FIXTURE = Path(__file__).parent / "fixtures" / "jmdict-mini.xml"
GOLDEN_DIR = Path(__file__).parent / "phase3_golden"
GOLDEN_REPORT = GOLDEN_DIR / "vocabulary-jmdict-v2.json"
REVIEWED_CASES = GOLDEN_DIR / "jmdict-review-cases-v2.json"


@pytest.fixture
def provider(tmp_path):
    index = tmp_path / "jmdict.sqlite3"
    build_jmdict_index(FIXTURE, index)
    value = SqliteJmdictProvider(index)
    yield value
    value.close()


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
