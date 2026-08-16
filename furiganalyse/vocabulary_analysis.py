"""Deterministic vocabulary candidates over the canonical Phase 2 book model."""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from furiganalyse.book_analysis import BookAnalysis
from furiganalyse.jmdict import (
    JmdictEntryMatch,
    JmdictProvider,
    JmdictProvenance,
    JmdictQuery,
    normalize_reading,
    pos_compatible,
)

SCHEMA_VERSION = 1
JAPANESE_PATTERN = re.compile(r"[一-龯々〆ヵヶぁ-ゖァ-ヺー]")


class VocabularyAnalysisError(ValueError):
    """Raised when a vocabulary report violates canonical invariants."""


@dataclass(frozen=True)
class TokenizerProvenance:
    name: str
    version: str
    wrapper: str
    wrapper_version: str
    dictionary: str
    dictionary_version: str


@dataclass(frozen=True)
class VocabularyToken:
    id: str
    surface: str
    lemma: str
    reading: Optional[str]
    part_of_speech: Optional[str]
    chapter_id: str
    block_id: str
    sentence_id: str
    sentence_start: int
    sentence_end: int
    block_start: int
    block_end: int
    reading_source: Optional[str]
    publisher_ruby_id: Optional[str]


@dataclass(frozen=True)
class VocabularyCandidate:
    id: str
    token_id: str
    surface: str
    lemma: str
    reading: Optional[str]
    part_of_speech: Optional[str]
    chapter_id: str
    block_id: str
    sentence_id: str
    sentence_start: int
    sentence_end: int
    block_start: int
    block_end: int
    reading_source: Optional[str]
    publisher_ruby_id: Optional[str]


@dataclass(frozen=True)
class VocabularyReport:
    schema_version: int
    book_id: str
    source_book_schema_version: int
    tokenizer: TokenizerProvenance
    tokens: list[VocabularyToken]
    candidates: list[VocabularyCandidate]


@dataclass(frozen=True)
class CandidateDictionaryMatches:
    id: str
    candidate_id: str
    entries: list[JmdictEntryMatch]


@dataclass(frozen=True)
class EnrichedVocabularyReport:
    schema_version: int
    book_id: str
    source_book_schema_version: int
    tokenizer: TokenizerProvenance
    tokens: list[VocabularyToken]
    candidates: list[VocabularyCandidate]
    dictionary: JmdictProvenance
    dictionary_matches: list[CandidateDictionaryMatches]


def _tokenizer():
    return importlib.import_module("furigana.furigana").mecab


def tokenizer_provenance() -> TokenizerProvenance:
    mecab = _tokenizer()
    dictionary = mecab.dictionary_info()
    return TokenizerProvenance(
        name="MeCab",
        version=importlib.metadata.version("mecab-python3"),
        wrapper="furigana",
        wrapper_version=importlib.metadata.version("furigana"),
        dictionary="MeCab system dictionary",
        dictionary_version=str(dictionary.version),
    )


def _node_values(node) -> tuple[str, Optional[str], Optional[str]]:
    fields = node.feature.split(",")
    part_of_speech = ",".join(fields[:2]) if fields and fields[0] != "BOS/EOS" else None
    lemma = fields[6] if len(fields) > 6 and fields[6] != "*" else node.surface
    reading = fields[7] if len(fields) > 7 and fields[7] != "*" else None
    return lemma, reading, part_of_speech


def _segment_tokens(text: str, offset: int):
    mecab = _tokenizer()
    mecab.parse("")
    node = mecab.parseToNode(text)
    cursor = 0
    while node is not None:
        surface = node.surface
        if surface:
            start = text.find(surface, cursor)
            if start < 0:
                raise VocabularyAnalysisError(
                    f"Tokenizer surface cannot be located: {surface!r}"
                )
            end = start + len(surface)
            lemma, reading, part_of_speech = _node_values(node)
            yield surface, lemma, reading, part_of_speech, offset + start, offset + end
            cursor = end
        node = node.next


def _is_candidate(token: VocabularyToken) -> bool:
    return (
        bool(JAPANESE_PATTERN.search(token.surface))
        and not token.surface.isspace()
        and not (token.part_of_speech or "").startswith("記号")
    )


def analyze_vocabulary(book: BookAnalysis) -> VocabularyReport:
    """Create ordered tokenizer records and Japanese vocabulary candidates."""
    tokens = []
    for chapter in book.chapters:
        for block in chapter.blocks:
            ruby_by_id = {ruby.id: ruby for ruby in block.publisher_ruby}
            for sentence in block.sentences:
                pending = []
                for span in sentence.text_spans:
                    sentence_offset = span.start - sentence.start
                    if span.publisher_ruby_id:
                        ruby = ruby_by_id[span.publisher_ruby_id]
                        pending.append(
                            (
                                span.text,
                                span.text,
                                ruby.reading,
                                None,
                                sentence_offset,
                                sentence_offset + len(span.text),
                                "publisher",
                                ruby.id,
                            )
                        )
                        continue
                    for values in _segment_tokens(span.text, sentence_offset):
                        surface, lemma, reading, pos, start, end = values
                        pending.append(
                            (
                                surface,
                                lemma,
                                reading,
                                pos,
                                start,
                                end,
                                "tokenizer" if reading else None,
                                None,
                            )
                        )

                pending.sort(key=lambda item: (item[4], item[5]))
                for index, values in enumerate(pending, start=1):
                    surface, lemma, reading, pos, start, end, source, ruby_id = values
                    tokens.append(
                        VocabularyToken(
                            id=f"{sentence.id}-tok-{index:04d}",
                            surface=surface,
                            lemma=lemma,
                            reading=reading,
                            part_of_speech=pos,
                            chapter_id=chapter.id,
                            block_id=block.id,
                            sentence_id=sentence.id,
                            sentence_start=start,
                            sentence_end=end,
                            block_start=sentence.start + start,
                            block_end=sentence.start + end,
                            reading_source=source,
                            publisher_ruby_id=ruby_id,
                        )
                    )

    candidates = []
    for token in tokens:
        if not _is_candidate(token):
            continue
        candidates.append(
            VocabularyCandidate(
                id=f"{token.id}-cand",
                token_id=token.id,
                surface=token.surface,
                lemma=token.lemma,
                reading=token.reading,
                part_of_speech=token.part_of_speech,
                chapter_id=token.chapter_id,
                block_id=token.block_id,
                sentence_id=token.sentence_id,
                sentence_start=token.sentence_start,
                sentence_end=token.sentence_end,
                block_start=token.block_start,
                block_end=token.block_end,
                reading_source=token.reading_source,
                publisher_ruby_id=token.publisher_ruby_id,
            )
        )

    report = VocabularyReport(
        schema_version=SCHEMA_VERSION,
        book_id=book.book_id,
        source_book_schema_version=book.schema_version,
        tokenizer=tokenizer_provenance(),
        tokens=tokens,
        candidates=candidates,
    )
    validate_vocabulary_report(book, report)
    return report


def validate_vocabulary_report(book: BookAnalysis, report: VocabularyReport):
    """Reject duplicate IDs, invalid offsets, mismatches, and overlap."""
    sentences = {}
    for chapter in book.chapters:
        for block in chapter.blocks:
            for sentence in block.sentences:
                sentences[sentence.id] = (chapter.id, block, sentence)

    identifiers = set()
    previous_by_sentence = {}
    token_by_id = {}
    for token in report.tokens:
        if token.id in identifiers:
            raise VocabularyAnalysisError(f"Duplicate vocabulary ID: {token.id}")
        identifiers.add(token.id)
        context = sentences.get(token.sentence_id)
        if context is None:
            raise VocabularyAnalysisError(f"Unknown sentence: {token.sentence_id}")
        chapter_id, block, sentence = context
        if token.chapter_id != chapter_id or token.block_id != block.id:
            raise VocabularyAnalysisError(f"Invalid token context: {token.id}")
        if not 0 <= token.sentence_start < token.sentence_end <= len(sentence.text):
            raise VocabularyAnalysisError(f"Invalid token offsets: {token.id}")
        if sentence.text[token.sentence_start : token.sentence_end] != token.surface:
            raise VocabularyAnalysisError(f"Token text mismatch: {token.id}")
        if (token.block_start, token.block_end) != (
            sentence.start + token.sentence_start,
            sentence.start + token.sentence_end,
        ):
            raise VocabularyAnalysisError(f"Invalid block offsets: {token.id}")
        if block.text[token.block_start : token.block_end] != token.surface:
            raise VocabularyAnalysisError(f"Block text mismatch: {token.id}")
        previous_end = previous_by_sentence.get(token.sentence_id, 0)
        if token.sentence_start < previous_end:
            raise VocabularyAnalysisError(f"Overlapping tokens: {token.sentence_id}")
        previous_by_sentence[token.sentence_id] = token.sentence_end
        token_by_id[token.id] = token

    for candidate in report.candidates:
        if candidate.id in identifiers:
            raise VocabularyAnalysisError(f"Duplicate vocabulary ID: {candidate.id}")
        identifiers.add(candidate.id)
        token = token_by_id.get(candidate.token_id)
        if token is None or asdict(candidate) != {
            "id": candidate.id,
            "token_id": candidate.token_id,
            **{key: value for key, value in asdict(token).items() if key != "id"},
        }:
            raise VocabularyAnalysisError(f"Candidate/token mismatch: {candidate.id}")
        if not _is_candidate(token):
            raise VocabularyAnalysisError(f"Ineligible candidate: {candidate.id}")


def enrich_vocabulary_report(
    report: VocabularyReport, provider: JmdictProvider
) -> EnrichedVocabularyReport:
    matches = []
    for candidate in report.candidates:
        entries = provider.lookup(
            JmdictQuery(
                surface=candidate.surface,
                lemma=candidate.lemma,
                reading=candidate.reading,
                part_of_speech=candidate.part_of_speech,
                publisher_reading=candidate.reading_source == "publisher",
            )
        )
        if entries:
            matches.append(
                CandidateDictionaryMatches(
                    id=f"{candidate.id}-jmdict",
                    candidate_id=candidate.id,
                    entries=entries,
                )
            )
    enriched = EnrichedVocabularyReport(
        schema_version=2,
        book_id=report.book_id,
        source_book_schema_version=report.source_book_schema_version,
        tokenizer=report.tokenizer,
        tokens=report.tokens,
        candidates=report.candidates,
        dictionary=provider.provenance,
        dictionary_matches=matches,
    )
    validate_enriched_report(enriched)
    return enriched


def validate_enriched_report(report: EnrichedVocabularyReport):
    if (
        not report.dictionary.dataset_id
        or not report.dictionary.dataset_version
        or report.dictionary.format_version < 1
        or not re.fullmatch(r"[0-9a-f]{64}", report.dictionary.sha256)
    ):
        raise VocabularyAnalysisError("Invalid dictionary provenance")
    candidates = {candidate.id: candidate for candidate in report.candidates}
    candidate_order = {
        candidate.id: index for index, candidate in enumerate(report.candidates)
    }
    identifiers = set()
    previous_candidate_index = -1
    for match in report.dictionary_matches:
        if match.id in identifiers:
            raise VocabularyAnalysisError(f"Duplicate dictionary match ID: {match.id}")
        identifiers.add(match.id)
        candidate = candidates.get(match.candidate_id)
        if candidate is None:
            raise VocabularyAnalysisError(
                f"Unknown dictionary-match candidate: {match.candidate_id}"
            )
        if match.id != f"{candidate.id}-jmdict":
            raise VocabularyAnalysisError(f"Unstable dictionary match ID: {match.id}")
        current_candidate_index = candidate_order[candidate.id]
        if current_candidate_index <= previous_candidate_index:
            raise VocabularyAnalysisError("Unordered dictionary matches")
        previous_candidate_index = current_candidate_index
        previous_sequence = -1
        entry_ids = set()
        for entry in match.entries:
            if entry.entry_id in entry_ids:
                raise VocabularyAnalysisError(
                    f"Duplicate dictionary entry match ID: {entry.entry_id}"
                )
            entry_ids.add(entry.entry_id)
            if entry.sequence <= previous_sequence:
                raise VocabularyAnalysisError(
                    f"Unordered dictionary entries: {match.id}"
                )
            previous_sequence = entry.sequence
            if entry.entry_id != f"jmdict-{entry.sequence}":
                raise VocabularyAnalysisError(
                    f"Unstable dictionary entry ID: {entry.entry_id}"
                )
            expected_forms = {
                "lemma": candidate.lemma,
                "surface": candidate.surface,
                "reading": normalize_reading(candidate.reading),
            }
            if (
                entry.matched_by not in expected_forms
                or entry.matched_form != expected_forms[entry.matched_by]
            ):
                raise VocabularyAnalysisError(
                    f"Dictionary match does not reference candidate text: {entry.entry_id}"
                )
            written_form = (
                entry.matched_form if entry.matched_by != "reading" else None
            )
            for reading in entry.readings:
                if (
                    written_form is not None
                    and reading.written_restrictions
                    and written_form not in reading.written_restrictions
                ):
                    raise VocabularyAnalysisError(
                        f"Incompatible dictionary reading restriction: {entry.entry_id}"
                    )
            if candidate.reading_source == "publisher":
                authoritative = normalize_reading(candidate.reading)
                if not entry.readings or any(
                    normalize_reading(reading.text) != authoritative
                    for reading in entry.readings
                ):
                    raise VocabularyAnalysisError(
                        f"Publisher reading mismatch: {entry.entry_id}"
                    )
            if not entry.senses:
                raise VocabularyAnalysisError(
                    f"Dictionary entry has no compatible senses: {entry.entry_id}"
                )
            sense_ids = set()
            previous_sense_index = 0
            for sense in entry.senses:
                if sense.id in sense_ids:
                    raise VocabularyAnalysisError(
                        f"Duplicate dictionary sense ID: {sense.id}"
                    )
                sense_ids.add(sense.id)
                if sense.index <= previous_sense_index:
                    raise VocabularyAnalysisError(
                        f"Unordered dictionary senses: {entry.entry_id}"
                    )
                previous_sense_index = sense.index
                if sense.id != f"jmdict-{entry.sequence}-sense-{sense.index:04d}":
                    raise VocabularyAnalysisError(
                        f"Unstable dictionary sense ID: {sense.id}"
                    )
                if not sense.glosses or any(
                    not gloss.strip() for gloss in sense.glosses
                ):
                    raise VocabularyAnalysisError(
                        f"Dictionary sense has no English gloss: {sense.id}"
                    )
                if (
                    sense.written_restrictions
                    and written_form not in sense.written_restrictions
                ):
                    raise VocabularyAnalysisError(
                        f"Incompatible sense written restriction: {sense.id}"
                    )
                if sense.reading_restrictions and not any(
                    reading.text in sense.reading_restrictions
                    for reading in entry.readings
                ):
                    raise VocabularyAnalysisError(
                        f"Incompatible sense reading restriction: {sense.id}"
                    )
                if not pos_compatible(
                    candidate.part_of_speech, sense.parts_of_speech
                ):
                    raise VocabularyAnalysisError(
                        f"Incompatible dictionary part of speech: {sense.id}"
                    )


def serialize_vocabulary_report(
    report: VocabularyReport | EnrichedVocabularyReport,
) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_vocabulary_report(
    report: VocabularyReport | EnrichedVocabularyReport,
    output_path: str | Path,
):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialize_vocabulary_report(report), encoding="utf-8")
