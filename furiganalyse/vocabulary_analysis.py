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
class VocabularyExpression:
    id: str
    surface: str
    normalized_form: str
    token_ids: list[str]
    candidate_ids: list[str]
    chapter_id: str
    block_id: str
    sentence_id: str
    sentence_start: int
    sentence_end: int
    block_start: int
    block_end: int


@dataclass(frozen=True)
class ExpressionDictionaryMatches:
    id: str
    expression_id: str
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


@dataclass(frozen=True)
class ExpressionEnrichedVocabularyReport:
    schema_version: int
    book_id: str
    source_book_schema_version: int
    tokenizer: TokenizerProvenance
    tokens: list[VocabularyToken]
    candidates: list[VocabularyCandidate]
    dictionary: JmdictProvenance
    dictionary_matches: list[CandidateDictionaryMatches]
    expressions: list[VocabularyExpression]
    expression_dictionary_matches: list[ExpressionDictionaryMatches]


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


def _expression_lookup_form(
    tokens: list[VocabularyToken],
) -> tuple[str, str | None, int]:
    content_end = len(tokens) - 1
    while content_end > 0 and (
        tokens[content_end].part_of_speech or ""
    ).startswith("助動詞"):
        content_end -= 1
    content = tokens[: content_end + 1]
    normalized = "".join(
        token.lemma if index == len(content) - 1 else token.surface
        for index, token in enumerate(content)
    )
    return normalized, content[-1].part_of_speech, len(content)


def _expression_runs(
    report: VocabularyReport,
) -> list[list[VocabularyToken]]:
    candidate_by_token = {candidate.token_id for candidate in report.candidates}
    runs = []
    current = []
    for token in report.tokens:
        eligible = (
            token.id in candidate_by_token
            and token.publisher_ruby_id is None
            and bool(JAPANESE_PATTERN.search(token.surface))
        )
        contiguous = (
            current
            and token.sentence_id == current[-1].sentence_id
            and token.sentence_start == current[-1].sentence_end
        )
        if not eligible or (current and not contiguous):
            if current:
                runs.append(current)
            current = []
        if eligible:
            current.append(token)
    if current:
        runs.append(current)
    return runs


def _find_expressions(
    report: VocabularyReport,
    provider: JmdictProvider,
    max_tokens: int = 8,
) -> tuple[list[VocabularyExpression], list[ExpressionDictionaryMatches]]:
    candidate_by_token = {
        candidate.token_id: candidate for candidate in report.candidates
    }
    discovered = []
    for run in _expression_runs(report):
        for start in range(len(run)):
            for end in range(start + 2, min(len(run), start + max_tokens) + 1):
                tokens = run[start:end]
                normalized, part_of_speech, content_count = (
                    _expression_lookup_form(tokens)
                )
                if content_count < 2:
                    continue
                surface = "".join(token.surface for token in tokens)
                entries = provider.lookup(
                    JmdictQuery(
                        surface=surface,
                        lemma=normalized,
                        reading=None,
                        part_of_speech=part_of_speech,
                    )
                )
                if entries:
                    discovered.append((tokens, surface, normalized, entries))

    selected = []
    occupied = set()
    for item in sorted(
        discovered,
        key=lambda value: (
            -len(value[0]),
            value[0][0].sentence_id,
            value[0][0].sentence_start,
            value[0][-1].sentence_end,
        ),
    ):
        token_ids = {token.id for token in item[0]}
        if token_ids & occupied:
            continue
        selected.append(item)
        occupied.update(token_ids)

    selected.sort(
        key=lambda value: (
            value[0][0].chapter_id,
            value[0][0].block_id,
            value[0][0].sentence_id,
            value[0][0].sentence_start,
        )
    )
    expressions = []
    matches = []
    index_by_sentence = {}
    for tokens, surface, normalized, entries in selected:
        first, last = tokens[0], tokens[-1]
        index = index_by_sentence.get(first.sentence_id, 0) + 1
        index_by_sentence[first.sentence_id] = index
        expression_id = f"{first.sentence_id}-expr-{index:04d}"
        expression = VocabularyExpression(
            id=expression_id,
            surface=surface,
            normalized_form=normalized,
            token_ids=[token.id for token in tokens],
            candidate_ids=[candidate_by_token[token.id].id for token in tokens],
            chapter_id=first.chapter_id,
            block_id=first.block_id,
            sentence_id=first.sentence_id,
            sentence_start=first.sentence_start,
            sentence_end=last.sentence_end,
            block_start=first.block_start,
            block_end=last.block_end,
        )
        expressions.append(expression)
        matches.append(
            ExpressionDictionaryMatches(
                id=f"{expression_id}-jmdict",
                expression_id=expression_id,
                entries=entries,
            )
        )
    return expressions, matches


def enrich_vocabulary_report(
    report: VocabularyReport,
    provider: JmdictProvider,
    include_expressions: bool = False,
) -> EnrichedVocabularyReport | ExpressionEnrichedVocabularyReport:
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
    values = dict(
        book_id=report.book_id,
        source_book_schema_version=report.source_book_schema_version,
        tokenizer=report.tokenizer,
        tokens=report.tokens,
        candidates=report.candidates,
        dictionary=provider.provenance,
        dictionary_matches=matches,
    )
    if include_expressions:
        expressions, expression_matches = _find_expressions(report, provider)
        enriched = ExpressionEnrichedVocabularyReport(
            schema_version=3,
            expressions=expressions,
            expression_dictionary_matches=expression_matches,
            **values,
        )
    else:
        enriched = EnrichedVocabularyReport(schema_version=2, **values)
    validate_enriched_report(enriched)
    return enriched


def validate_enriched_report(
    report: EnrichedVocabularyReport | ExpressionEnrichedVocabularyReport,
):
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

    if isinstance(report, ExpressionEnrichedVocabularyReport):
        token_by_id = {token.id: token for token in report.tokens}
        candidate_by_id = {candidate.id: candidate for candidate in report.candidates}
        expression_by_id = {}
        previous_key = None
        occupied_by_sentence = {}
        for expression in report.expressions:
            if expression.id in expression_by_id:
                raise VocabularyAnalysisError(
                    f"Duplicate expression ID: {expression.id}"
                )
            expression_by_id[expression.id] = expression
            if expression.id != (
                f"{expression.sentence_id}-expr-"
                f"{len([value for value in expression_by_id.values() if value.sentence_id == expression.sentence_id]):04d}"
            ):
                raise VocabularyAnalysisError(f"Unstable expression ID: {expression.id}")
            tokens = [token_by_id.get(token_id) for token_id in expression.token_ids]
            if len(tokens) < 2 or any(token is None for token in tokens):
                raise VocabularyAnalysisError(
                    f"Invalid expression token references: {expression.id}"
                )
            if any(token.publisher_ruby_id for token in tokens):
                raise VocabularyAnalysisError(
                    f"Expression crosses publisher ruby: {expression.id}"
                )
            if expression.candidate_ids != [
                f"{token.id}-cand" for token in tokens
            ] or any(
                candidate_id not in candidate_by_id
                for candidate_id in expression.candidate_ids
            ):
                raise VocabularyAnalysisError(
                    f"Invalid expression candidate references: {expression.id}"
                )
            if any(
                left.sentence_id != right.sentence_id
                or left.sentence_end != right.sentence_start
                for left, right in zip(tokens, tokens[1:])
            ):
                raise VocabularyAnalysisError(
                    f"Non-contiguous expression tokens: {expression.id}"
                )
            first, last = tokens[0], tokens[-1]
            expected_context = (
                first.chapter_id,
                first.block_id,
                first.sentence_id,
                first.sentence_start,
                last.sentence_end,
                first.block_start,
                last.block_end,
            )
            actual_context = (
                expression.chapter_id,
                expression.block_id,
                expression.sentence_id,
                expression.sentence_start,
                expression.sentence_end,
                expression.block_start,
                expression.block_end,
            )
            if actual_context != expected_context:
                raise VocabularyAnalysisError(
                    f"Invalid expression context: {expression.id}"
                )
            if expression.surface != "".join(token.surface for token in tokens):
                raise VocabularyAnalysisError(
                    f"Expression text mismatch: {expression.id}"
                )
            normalized, _, content_count = _expression_lookup_form(tokens)
            if content_count < 2:
                raise VocabularyAnalysisError(
                    f"Expression has fewer than two lexical components: {expression.id}"
                )
            if expression.normalized_form != normalized:
                raise VocabularyAnalysisError(
                    f"Expression normalization mismatch: {expression.id}"
                )
            key = (
                expression.chapter_id,
                expression.block_id,
                expression.sentence_id,
                expression.sentence_start,
            )
            if previous_key is not None and key <= previous_key:
                raise VocabularyAnalysisError("Unordered expressions")
            previous_key = key
            occupied = occupied_by_sentence.setdefault(expression.sentence_id, set())
            if occupied.intersection(expression.token_ids):
                raise VocabularyAnalysisError(
                    f"Overlapping expressions: {expression.sentence_id}"
                )
            occupied.update(expression.token_ids)

        if len(report.expression_dictionary_matches) != len(report.expressions):
            raise VocabularyAnalysisError("Expression/match count mismatch")
        for expression, match in zip(
            report.expressions, report.expression_dictionary_matches
        ):
            if (
                match.expression_id != expression.id
                or match.id != f"{expression.id}-jmdict"
                or not match.entries
            ):
                raise VocabularyAnalysisError(
                    f"Invalid expression dictionary match: {match.id}"
                )
            previous_sequence = -1
            entry_ids = set()
            expression_tokens = [
                token_by_id[token_id] for token_id in expression.token_ids
            ]
            _, expression_pos, _ = _expression_lookup_form(expression_tokens)
            for entry in match.entries:
                if entry.entry_id in entry_ids:
                    raise VocabularyAnalysisError(
                        f"Duplicate expression entry ID: {entry.entry_id}"
                    )
                entry_ids.add(entry.entry_id)
                if entry.sequence <= previous_sequence:
                    raise VocabularyAnalysisError(
                        f"Unordered expression entries: {match.id}"
                    )
                previous_sequence = entry.sequence
                if entry.entry_id != f"jmdict-{entry.sequence}":
                    raise VocabularyAnalysisError(
                        f"Unstable expression entry ID: {entry.entry_id}"
                    )
                if entry.matched_form not in {
                    expression.surface,
                    expression.normalized_form,
                }:
                    raise VocabularyAnalysisError(
                        f"Expression dictionary text mismatch: {entry.entry_id}"
                    )
                written_form = (
                    entry.matched_form if entry.matched_by != "reading" else None
                )
                if any(
                    written_form is not None
                    and reading.written_restrictions
                    and written_form not in reading.written_restrictions
                    for reading in entry.readings
                ):
                    raise VocabularyAnalysisError(
                        f"Incompatible expression reading: {entry.entry_id}"
                    )
                previous_sense_index = 0
                sense_ids = set()
                for sense in entry.senses:
                    if (
                        sense.id in sense_ids
                        or sense.index <= previous_sense_index
                        or sense.id
                        != f"jmdict-{entry.sequence}-sense-{sense.index:04d}"
                    ):
                        raise VocabularyAnalysisError(
                            f"Invalid expression sense order or ID: {sense.id}"
                        )
                    sense_ids.add(sense.id)
                    previous_sense_index = sense.index
                    if not sense.glosses or any(
                        not gloss.strip() for gloss in sense.glosses
                    ):
                        raise VocabularyAnalysisError(
                            f"Expression sense has no English gloss: {sense.id}"
                        )
                    if (
                        sense.written_restrictions
                        and written_form not in sense.written_restrictions
                    ):
                        raise VocabularyAnalysisError(
                            f"Incompatible expression written restriction: {sense.id}"
                        )
                    if sense.reading_restrictions and not any(
                        reading.text in sense.reading_restrictions
                        for reading in entry.readings
                    ):
                        raise VocabularyAnalysisError(
                            f"Incompatible expression reading restriction: {sense.id}"
                        )
                    if not pos_compatible(
                        expression_pos, sense.parts_of_speech
                    ):
                        raise VocabularyAnalysisError(
                            f"Incompatible expression part of speech: {sense.id}"
                        )


def serialize_vocabulary_report(
    report: (
        VocabularyReport
        | EnrichedVocabularyReport
        | ExpressionEnrichedVocabularyReport
    ),
) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_vocabulary_report(
    report: (
        VocabularyReport
        | EnrichedVocabularyReport
        | ExpressionEnrichedVocabularyReport
    ),
    output_path: str | Path,
):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialize_vocabulary_report(report), encoding="utf-8")
