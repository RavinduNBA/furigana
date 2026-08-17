"""Deterministic dictionary-only study-item selection over a schema-v4 report."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = 1
DISPLAY_MEANING_MAX_CHARS = 120
ITEM_KINDS = {"vocabulary", "expression", "name"}


class StudyPlanError(ValueError):
    """Raised when an annotation plan or its schema-v4 source is invalid."""


@dataclass(frozen=True)
class StudyPlanConfig:
    per_chapter_item_limit: int = 10


@dataclass(frozen=True)
class StudyOccurrence:
    id: str
    occurrence_number: int
    chapter_id: str
    block_id: str
    sentence_id: str
    sentence_start: int
    sentence_end: int
    block_start: int
    block_end: int
    token_ids: list[str]
    candidate_ids: list[str]
    expression_id: Optional[str]
    name_id: Optional[str]
    publisher_ruby_id: Optional[str]
    annotation_target: str
    source_anchor_id: str


@dataclass(frozen=True)
class StudyItem:
    id: str
    kind: str
    surface: str
    lemma: Optional[str]
    normalized_form: Optional[str]
    reading: Optional[str]
    reading_source: Optional[str]
    chapter_id: str
    block_id: str
    sentence_id: str
    token_ids: list[str]
    candidate_ids: list[str]
    expression_id: Optional[str]
    name_id: Optional[str]
    publisher_ruby_id: Optional[str]
    source_entry_ids: list[str]
    source_sense_ids: list[str]
    source_translation_ids: list[str]
    selected_entry_id: str
    selected_sense_id: Optional[str]
    selected_translation_id: Optional[str]
    dictionary_dataset_id: str
    dictionary_dataset_version: str
    display_meaning: str
    selection_reason: str
    note_anchor_id: str
    occurrences: list[StudyOccurrence]


@dataclass(frozen=True)
class StudyPlanDiagnostic:
    id: str
    chapter_id: str
    source_id: str
    reason: str


@dataclass(frozen=True)
class AnnotationPlan:
    schema_version: int
    source_report_schema_version: int
    book_id: str
    config: StudyPlanConfig
    tokenizer: dict[str, Any]
    dictionary: dict[str, Any]
    name_dictionary: dict[str, Any]
    items: list[StudyItem]
    diagnostics: list[StudyPlanDiagnostic]


@dataclass(frozen=True)
class _Proposal:
    kind: str
    source_id: str
    surface: str
    lemma: Optional[str]
    normalized_form: Optional[str]
    reading: Optional[str]
    reading_source: Optional[str]
    chapter_id: str
    block_id: str
    sentence_id: str
    sentence_start: int
    sentence_end: int
    block_start: int
    block_end: int
    token_ids: list[str]
    candidate_ids: list[str]
    expression_id: Optional[str]
    name_id: Optional[str]
    publisher_ruby_id: Optional[str]
    source_entry_ids: list[str]
    source_sense_ids: list[str]
    source_translation_ids: list[str]
    selected_entry_id: str
    selected_sense_id: Optional[str]
    selected_translation_id: Optional[str]
    dictionary_dataset_id: str
    dictionary_dataset_version: str
    display_meaning: str
    selection_reason: str


def _required_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StudyPlanError(f"Expected object: {name}")
    return value


def _required_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise StudyPlanError(f"Expected list: {name}")
    return value


def _indexed(values: list[dict[str, Any]], name: str) -> dict[str, dict[str, Any]]:
    result = {}
    for value in values:
        identifier = value.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise StudyPlanError(f"Missing {name} ID")
        if identifier in result:
            raise StudyPlanError(f"Duplicate {name} ID: {identifier}")
        result[identifier] = value
    return result


def _short_meaning(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise StudyPlanError("Dictionary display meaning is empty")
    if len(value) <= DISPLAY_MEANING_MAX_CHARS:
        return value
    return value[: DISPLAY_MEANING_MAX_CHARS - 3].rstrip() + "..."


def _source_key(value: _Proposal):
    priority = {"expression": 0, "name": 1, "vocabulary": 2}[value.kind]
    return (
        value.chapter_id,
        value.block_id,
        value.sentence_id,
        value.sentence_start,
        priority,
        -value.sentence_end,
        value.source_id,
    )


def _entry_references(entries):
    return [entry["entry_id"] for entry in entries]


def _sense_references(entries):
    return [
        sense["id"]
        for entry in entries
        for sense in _required_list(entry.get("senses"), "JMdict senses")
    ]


def _translation_references(entries):
    return [
        translation["id"]
        for entry in entries
        for translation in _required_list(
            entry.get("translations"), "JMnedict translations"
        )
    ]


def _validate_source_report(report: dict[str, Any]):
    if report.get("schema_version") != 4:
        raise StudyPlanError("Annotation planning requires vocabulary schema v4")
    for key in ("book_id", "tokenizer", "dictionary", "name_dictionary"):
        if not report.get(key):
            raise StudyPlanError(f"Schema-v4 report lacks {key}")
    for key in (
        "tokens",
        "candidates",
        "dictionary_matches",
        "expressions",
        "expression_dictionary_matches",
        "name_occurrences",
        "name_dictionary_matches",
        "name_diagnostics",
    ):
        _required_list(report.get(key), key)


def _proposals(report: dict[str, Any]):
    tokens = _indexed(report["tokens"], "token")
    candidates = _indexed(report["candidates"], "candidate")
    expressions = _indexed(report["expressions"], "expression")
    names = _indexed(report["name_occurrences"], "name")
    dictionary = _required_mapping(report["dictionary"], "dictionary")
    name_dictionary = _required_mapping(report["name_dictionary"], "name_dictionary")
    proposals = []

    for match in report["dictionary_matches"]:
        candidate = candidates.get(match.get("candidate_id"))
        if candidate is None:
            raise StudyPlanError(
                f"Unknown dictionary-match candidate: {match.get('candidate_id')}"
            )
        token = tokens.get(candidate.get("token_id"))
        if token is None:
            raise StudyPlanError(
                f"Unknown candidate token: {candidate.get('token_id')}"
            )
        entries = _required_list(match.get("entries"), "JMdict entries")
        if not entries or not entries[0].get("senses"):
            raise StudyPlanError(f"JMdict match has no senses: {match.get('id')}")
        selected_entry = entries[0]
        selected_sense = selected_entry["senses"][0]
        glosses = _required_list(selected_sense.get("glosses"), "JMdict glosses")
        if not glosses:
            raise StudyPlanError(
                f"JMdict sense has no gloss: {selected_sense.get('id')}"
            )
        publisher = candidate.get("reading_source") == "publisher"
        readings = _required_list(selected_entry.get("readings"), "JMdict readings")
        reading = (
            candidate.get("reading")
            if publisher
            else (readings[0].get("text") if readings else candidate.get("reading"))
        )
        proposals.append(
            _Proposal(
                kind="vocabulary",
                source_id=match["id"],
                surface=candidate["surface"],
                lemma=candidate.get("lemma"),
                normalized_form=None,
                reading=reading,
                reading_source="publisher" if publisher else "JMdict",
                chapter_id=candidate["chapter_id"],
                block_id=candidate["block_id"],
                sentence_id=candidate["sentence_id"],
                sentence_start=candidate["sentence_start"],
                sentence_end=candidate["sentence_end"],
                block_start=candidate["block_start"],
                block_end=candidate["block_end"],
                token_ids=[candidate["token_id"]],
                candidate_ids=[candidate["id"]],
                expression_id=None,
                name_id=None,
                publisher_ruby_id=candidate.get("publisher_ruby_id"),
                source_entry_ids=_entry_references(entries),
                source_sense_ids=_sense_references(entries),
                source_translation_ids=[],
                selected_entry_id=selected_entry["entry_id"],
                selected_sense_id=selected_sense["id"],
                selected_translation_id=None,
                dictionary_dataset_id=dictionary["dataset_id"],
                dictionary_dataset_version=dictionary["dataset_version"],
                display_meaning=_short_meaning(glosses[0]),
                selection_reason="first-compatible-jmdict-entry-and-sense",
            )
        )

    for match in report["expression_dictionary_matches"]:
        expression = expressions.get(match.get("expression_id"))
        if expression is None:
            raise StudyPlanError(
                f"Unknown expression match: {match.get('expression_id')}"
            )
        entries = _required_list(match.get("entries"), "expression entries")
        if not entries or not entries[0].get("senses"):
            raise StudyPlanError(f"Expression match has no senses: {match.get('id')}")
        selected_entry = entries[0]
        selected_sense = selected_entry["senses"][0]
        glosses = _required_list(selected_sense.get("glosses"), "expression glosses")
        readings = _required_list(selected_entry.get("readings"), "expression readings")
        proposals.append(
            _Proposal(
                kind="expression",
                source_id=match["id"],
                surface=expression["surface"],
                lemma=None,
                normalized_form=expression["normalized_form"],
                reading=readings[0].get("text") if readings else None,
                reading_source="JMdict",
                chapter_id=expression["chapter_id"],
                block_id=expression["block_id"],
                sentence_id=expression["sentence_id"],
                sentence_start=expression["sentence_start"],
                sentence_end=expression["sentence_end"],
                block_start=expression["block_start"],
                block_end=expression["block_end"],
                token_ids=expression["token_ids"],
                candidate_ids=expression["candidate_ids"],
                expression_id=expression["id"],
                name_id=None,
                publisher_ruby_id=None,
                source_entry_ids=_entry_references(entries),
                source_sense_ids=_sense_references(entries),
                source_translation_ids=[],
                selected_entry_id=selected_entry["entry_id"],
                selected_sense_id=selected_sense["id"],
                selected_translation_id=None,
                dictionary_dataset_id=dictionary["dataset_id"],
                dictionary_dataset_version=dictionary["dataset_version"],
                display_meaning=_short_meaning(glosses[0]),
                selection_reason="longest-expression-first-compatible-sense",
            )
        )

    for match in report["name_dictionary_matches"]:
        name = names.get(match.get("name_id"))
        if name is None:
            raise StudyPlanError(f"Unknown name match: {match.get('name_id')}")
        entries = _required_list(match.get("entries"), "JMnedict entries")
        if not entries or not entries[0].get("translations"):
            raise StudyPlanError(f"Name match has no translations: {match.get('id')}")
        selected_entry = entries[0]
        selected_translation = selected_entry["translations"][0]
        translations = _required_list(
            selected_translation.get("translations"), "name translations"
        )
        name_types = _required_list(
            selected_translation.get("name_types"), "name types"
        )
        if not translations or not name_types:
            raise StudyPlanError(
                f"Incomplete JMnedict translation: {selected_translation.get('id')}"
            )
        meaning = f"{translations[0]} ({'; '.join(name_types)})"
        proposals.append(
            _Proposal(
                kind="name",
                source_id=match["id"],
                surface=name["surface"],
                lemma=None,
                normalized_form=None,
                reading=name.get("reading")
                or selected_entry["readings"][0].get("text"),
                reading_source=(
                    "publisher"
                    if name.get("classification_evidence") == "publisher_ruby"
                    else "JMnedict"
                ),
                chapter_id=name["chapter_id"],
                block_id=name["block_id"],
                sentence_id=name["sentence_id"],
                sentence_start=name["sentence_start"],
                sentence_end=name["sentence_end"],
                block_start=name["block_start"],
                block_end=name["block_end"],
                token_ids=[name["token_id"]],
                candidate_ids=[name["candidate_id"]],
                expression_id=None,
                name_id=name["id"],
                publisher_ruby_id=name.get("publisher_ruby_id"),
                source_entry_ids=_entry_references(entries),
                source_sense_ids=[],
                source_translation_ids=_translation_references(entries),
                selected_entry_id=selected_entry["entry_id"],
                selected_sense_id=None,
                selected_translation_id=selected_translation["id"],
                dictionary_dataset_id=name_dictionary["dataset_id"],
                dictionary_dataset_version=name_dictionary["dataset_version"],
                display_meaning=_short_meaning(meaning),
                selection_reason="first-compatible-jmnedict-entry-and-translation",
            )
        )
    return proposals, tokens, candidates, expressions, names


def _lexical_key(proposal: _Proposal):
    return (
        proposal.kind,
        proposal.selected_entry_id,
        proposal.selected_sense_id,
        proposal.selected_translation_id,
    )


def create_annotation_plan(
    report: dict[str, Any],
    config: StudyPlanConfig | None = None,
) -> AnnotationPlan:
    """Select deterministic dictionary-backed study items from schema v4."""
    _validate_source_report(report)
    config = config or StudyPlanConfig()
    if config.per_chapter_item_limit < 1:
        raise StudyPlanError("per_chapter_item_limit must be positive")
    proposals, _, candidates, expressions, names = _proposals(report)
    proposals.sort(key=_source_key)
    diagnostics_pending = []

    accepted = []
    occupied = {}
    for proposal in proposals:
        sentence_key = (proposal.chapter_id, proposal.sentence_id)
        intervals = occupied.setdefault(sentence_key, [])
        overlap = any(
            proposal.sentence_start < end and start < proposal.sentence_end
            for start, end in intervals
        )
        if overlap:
            diagnostics_pending.append(
                (proposal.chapter_id, proposal.source_id, "overlapping-selected-item")
            )
            continue
        accepted.append(proposal)
        intervals.append((proposal.sentence_start, proposal.sentence_end))

    grouped = {}
    for proposal in accepted:
        grouped.setdefault(_lexical_key(proposal), []).append(proposal)
    groups = sorted(grouped.values(), key=lambda values: _source_key(values[0]))

    selected_groups = []
    chapter_counts = {}
    for occurrences in groups:
        chapter_id = occurrences[0].chapter_id
        count = chapter_counts.get(chapter_id, 0)
        if count >= config.per_chapter_item_limit:
            diagnostics_pending.extend(
                (value.chapter_id, value.source_id, "chapter-item-limit")
                for value in occurrences
            )
            continue
        chapter_counts[chapter_id] = count + 1
        selected_groups.append(occurrences)

    selected_candidate_ids = {
        candidate_id
        for occurrences in selected_groups
        for value in occurrences
        for candidate_id in value.candidate_ids
    }
    expression_candidate_ids = {
        candidate_id
        for expression in expressions.values()
        for candidate_id in expression.get("candidate_ids", [])
    }
    name_candidate_ids = {name["candidate_id"] for name in names.values()}
    diagnostic_candidate_ids = {
        value["candidate_id"] for value in report["name_diagnostics"]
    }
    matched_candidate_ids = {
        value["candidate_id"] for value in report["dictionary_matches"]
    }
    for candidate in report["candidates"]:
        candidate_id = candidate["id"]
        if candidate_id in selected_candidate_ids:
            continue
        if candidate_id in diagnostic_candidate_ids:
            diagnostic = next(
                value
                for value in report["name_diagnostics"]
                if value["candidate_id"] == candidate_id
            )
            diagnostics_pending.append(
                (
                    candidate["chapter_id"],
                    candidate_id,
                    f"phase3-name-{diagnostic['reason']}",
                )
            )
        elif (
            candidate_id not in matched_candidate_ids
            and candidate_id not in expression_candidate_ids
            and candidate_id not in name_candidate_ids
        ):
            diagnostics_pending.append(
                (
                    candidate["chapter_id"],
                    candidate_id,
                    "no-compatible-dictionary-match",
                )
            )

    items = []
    for item_index, occurrences in enumerate(selected_groups, start=1):
        primary = occurrences[0]
        item_id = f"study-item-{item_index:04d}"
        occurrence_records = []
        for occurrence_number, value in enumerate(occurrences, start=1):
            occurrence_id = f"{item_id}-occ-{occurrence_number:04d}"
            occurrence_records.append(
                StudyOccurrence(
                    id=occurrence_id,
                    occurrence_number=occurrence_number,
                    chapter_id=value.chapter_id,
                    block_id=value.block_id,
                    sentence_id=value.sentence_id,
                    sentence_start=value.sentence_start,
                    sentence_end=value.sentence_end,
                    block_start=value.block_start,
                    block_end=value.block_end,
                    token_ids=value.token_ids,
                    candidate_ids=value.candidate_ids,
                    expression_id=value.expression_id,
                    name_id=value.name_id,
                    publisher_ruby_id=value.publisher_ruby_id,
                    annotation_target=(
                        "preserved_publisher_ruby"
                        if value.publisher_ruby_id
                        else "text"
                    ),
                    source_anchor_id=f"src-{occurrence_id}",
                )
            )
        items.append(
            StudyItem(
                id=item_id,
                kind=primary.kind,
                surface=primary.surface,
                lemma=primary.lemma,
                normalized_form=primary.normalized_form,
                reading=primary.reading,
                reading_source=primary.reading_source,
                chapter_id=primary.chapter_id,
                block_id=primary.block_id,
                sentence_id=primary.sentence_id,
                token_ids=primary.token_ids,
                candidate_ids=primary.candidate_ids,
                expression_id=primary.expression_id,
                name_id=primary.name_id,
                publisher_ruby_id=primary.publisher_ruby_id,
                source_entry_ids=primary.source_entry_ids,
                source_sense_ids=primary.source_sense_ids,
                source_translation_ids=primary.source_translation_ids,
                selected_entry_id=primary.selected_entry_id,
                selected_sense_id=primary.selected_sense_id,
                selected_translation_id=primary.selected_translation_id,
                dictionary_dataset_id=primary.dictionary_dataset_id,
                dictionary_dataset_version=primary.dictionary_dataset_version,
                display_meaning=primary.display_meaning,
                selection_reason=primary.selection_reason,
                note_anchor_id=f"note-{item_id}",
                occurrences=occurrence_records,
            )
        )

    diagnostics_pending.sort()
    diagnostics = [
        StudyPlanDiagnostic(
            id=f"plan-diagnostic-{index:04d}",
            chapter_id=chapter_id,
            source_id=source_id,
            reason=reason,
        )
        for index, (chapter_id, source_id, reason) in enumerate(
            diagnostics_pending, start=1
        )
    ]
    plan = AnnotationPlan(
        schema_version=SCHEMA_VERSION,
        source_report_schema_version=report["schema_version"],
        book_id=report["book_id"],
        config=config,
        tokenizer=report["tokenizer"],
        dictionary=report["dictionary"],
        name_dictionary=report["name_dictionary"],
        items=items,
        diagnostics=diagnostics,
    )
    validate_annotation_plan(report, plan)
    return plan


def _source_records(report):
    candidates = _indexed(report["candidates"], "candidate")
    expressions = _indexed(report["expressions"], "expression")
    names = _indexed(report["name_occurrences"], "name")
    matches = {
        value["id"]: value
        for key in (
            "dictionary_matches",
            "expression_dictionary_matches",
            "name_dictionary_matches",
        )
        for value in report[key]
    }
    return candidates, expressions, names, matches


def validate_annotation_plan(report: dict[str, Any], plan: AnnotationPlan):
    _validate_source_report(report)
    if plan.schema_version != SCHEMA_VERSION:
        raise StudyPlanError("Unsupported annotation-plan schema")
    if (
        plan.source_report_schema_version != report["schema_version"]
        or plan.book_id != report["book_id"]
        or plan.dictionary != report["dictionary"]
        or plan.name_dictionary != report["name_dictionary"]
        or plan.tokenizer != report["tokenizer"]
    ):
        raise StudyPlanError("Annotation-plan provenance mismatch")
    candidates, expressions, names, matches = _source_records(report)
    identifiers = set()
    previous_item_key = None
    occupied = {}
    chapter_counts = {}
    for item_index, item in enumerate(plan.items, start=1):
        if item.id in identifiers:
            raise StudyPlanError(f"Duplicate study ID: {item.id}")
        identifiers.add(item.id)
        if item.id != f"study-item-{item_index:04d}" or item.kind not in ITEM_KINDS:
            raise StudyPlanError(f"Unstable study item ID or kind: {item.id}")
        if (
            not item.display_meaning.strip()
            or len(item.display_meaning) > DISPLAY_MEANING_MAX_CHARS
            or not item.source_entry_ids
            or not item.selected_entry_id
            or not item.dictionary_dataset_id
            or not item.dictionary_dataset_version
        ):
            raise StudyPlanError(f"Incomplete study item: {item.id}")
        if item.selected_entry_id not in item.source_entry_ids:
            raise StudyPlanError(f"Invalid selected entry: {item.id}")
        if item.kind in {"vocabulary", "expression"}:
            if (
                not item.source_sense_ids
                or item.selected_sense_id not in item.source_sense_ids
                or item.source_translation_ids
                or item.selected_translation_id is not None
            ):
                raise StudyPlanError(f"Invalid JMdict references: {item.id}")
        elif (
            not item.source_translation_ids
            or item.selected_translation_id not in item.source_translation_ids
            or item.source_sense_ids
            or item.selected_sense_id is not None
        ):
            raise StudyPlanError(f"Invalid JMnedict references: {item.id}")
        if not item.occurrences:
            raise StudyPlanError(f"Study item has no occurrences: {item.id}")
        primary = item.occurrences[0]
        item_key = (
            primary.chapter_id,
            primary.block_id,
            primary.sentence_id,
            primary.sentence_start,
            item.id,
        )
        if previous_item_key is not None and item_key <= previous_item_key:
            raise StudyPlanError("Unordered study items")
        previous_item_key = item_key
        chapter_counts[item.chapter_id] = chapter_counts.get(item.chapter_id, 0) + 1
        if chapter_counts[item.chapter_id] > plan.config.per_chapter_item_limit:
            raise StudyPlanError(f"Chapter item limit exceeded: {item.chapter_id}")
        if (
            item.chapter_id,
            item.block_id,
            item.sentence_id,
            item.token_ids,
            item.candidate_ids,
            item.expression_id,
            item.name_id,
            item.publisher_ruby_id,
        ) != (
            primary.chapter_id,
            primary.block_id,
            primary.sentence_id,
            primary.token_ids,
            primary.candidate_ids,
            primary.expression_id,
            primary.name_id,
            primary.publisher_ruby_id,
        ):
            raise StudyPlanError(f"Item/primary occurrence mismatch: {item.id}")

        previous_occurrence_key = None
        source_match_id = None
        for occurrence_index, occurrence in enumerate(item.occurrences, start=1):
            if occurrence.id in identifiers:
                raise StudyPlanError(f"Duplicate study ID: {occurrence.id}")
            identifiers.add(occurrence.id)
            expected_id = f"{item.id}-occ-{occurrence_index:04d}"
            if (
                occurrence.id != expected_id
                or occurrence.occurrence_number != occurrence_index
                or occurrence.source_anchor_id != f"src-{expected_id}"
                or item.note_anchor_id != f"note-{item.id}"
            ):
                raise StudyPlanError(
                    f"Unstable occurrence anchor or ID: {occurrence.id}"
                )
            key = (
                occurrence.chapter_id,
                occurrence.block_id,
                occurrence.sentence_id,
                occurrence.sentence_start,
            )
            if previous_occurrence_key is not None and key <= previous_occurrence_key:
                raise StudyPlanError(f"Unordered item occurrences: {item.id}")
            previous_occurrence_key = key
            if not (
                0 <= occurrence.sentence_start < occurrence.sentence_end
                and 0 <= occurrence.block_start < occurrence.block_end
            ):
                raise StudyPlanError(f"Invalid occurrence offsets: {occurrence.id}")
            sentence_key = (occurrence.chapter_id, occurrence.sentence_id)
            intervals = occupied.setdefault(sentence_key, [])
            if any(
                occurrence.sentence_start < end and start < occurrence.sentence_end
                for start, end in intervals
            ):
                raise StudyPlanError(
                    f"Overlapping selected occurrences: {sentence_key}"
                )
            intervals.append((occurrence.sentence_start, occurrence.sentence_end))
            if occurrence.publisher_ruby_id:
                if (
                    occurrence.annotation_target != "preserved_publisher_ruby"
                    or item.reading_source != "publisher"
                ):
                    raise StudyPlanError(
                        f"Publisher-ruby policy violation: {occurrence.id}"
                    )
            elif occurrence.annotation_target != "text":
                raise StudyPlanError(f"Invalid annotation target: {occurrence.id}")

            if item.kind == "vocabulary":
                if (
                    len(occurrence.candidate_ids) != 1
                    or len(occurrence.token_ids) != 1
                    or occurrence.expression_id
                    or occurrence.name_id
                ):
                    raise StudyPlanError(f"Invalid vocabulary source: {occurrence.id}")
                source = candidates.get(occurrence.candidate_ids[0])
                source_match_id = f"{occurrence.candidate_ids[0]}-jmdict"
            elif item.kind == "expression":
                source = expressions.get(occurrence.expression_id)
                source_match_id = f"{occurrence.expression_id}-jmdict"
            else:
                source = names.get(occurrence.name_id)
                source_match_id = f"{occurrence.name_id}-jmnedict"
            if source is None or source_match_id not in matches:
                raise StudyPlanError(f"Unknown occurrence source: {occurrence.id}")
            if (
                source["chapter_id"],
                source["block_id"],
                source["sentence_id"],
                source["sentence_start"],
                source["sentence_end"],
                source["block_start"],
                source["block_end"],
            ) != (
                occurrence.chapter_id,
                occurrence.block_id,
                occurrence.sentence_id,
                occurrence.sentence_start,
                occurrence.sentence_end,
                occurrence.block_start,
                occurrence.block_end,
            ):
                raise StudyPlanError(f"Occurrence/source mismatch: {occurrence.id}")
            match = matches[source_match_id]
            entry_ids = _entry_references(match["entries"])
            if item.source_entry_ids != entry_ids:
                raise StudyPlanError(f"Invalid source entries: {item.id}")
            if item.kind == "name":
                references = _translation_references(match["entries"])
                if item.source_translation_ids != references:
                    raise StudyPlanError(f"Invalid name translations: {item.id}")
            else:
                references = _sense_references(match["entries"])
                if item.source_sense_ids != references:
                    raise StudyPlanError(f"Invalid dictionary senses: {item.id}")
        if source_match_id is None:
            raise StudyPlanError(f"Missing source match: {item.id}")

    previous_diagnostic = None
    diagnostic_ids = set()
    valid_source_ids = set(candidates) | set(expressions) | set(names) | set(matches)
    for index, diagnostic in enumerate(plan.diagnostics, start=1):
        if diagnostic.id in diagnostic_ids:
            raise StudyPlanError(f"Duplicate diagnostic ID: {diagnostic.id}")
        diagnostic_ids.add(diagnostic.id)
        if diagnostic.id != f"plan-diagnostic-{index:04d}":
            raise StudyPlanError(f"Unstable diagnostic ID: {diagnostic.id}")
        key = (diagnostic.chapter_id, diagnostic.source_id, diagnostic.reason)
        if previous_diagnostic is not None and key < previous_diagnostic:
            raise StudyPlanError("Unordered diagnostics")
        previous_diagnostic = key
        if diagnostic.source_id not in valid_source_ids:
            raise StudyPlanError(f"Unknown diagnostic source: {diagnostic.source_id}")
        if not diagnostic.reason:
            raise StudyPlanError(f"Missing diagnostic reason: {diagnostic.id}")


def serialize_annotation_plan(plan: AnnotationPlan) -> str:
    return json.dumps(asdict(plan), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_annotation_plan(plan: AnnotationPlan, output_path: str | Path):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialize_annotation_plan(plan), encoding="utf-8")


def load_vocabulary_report(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return _required_mapping(value, "vocabulary report")
