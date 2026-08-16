import hashlib
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
    analyze_vocabulary,
    enrich_vocabulary_report,
    serialize_vocabulary_report,
)
from tests.phase0_epub import build_fixture

FIXTURE = Path(__file__).parent / "fixtures" / "jmdict-mini.xml"


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
