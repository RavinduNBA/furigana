"""Deterministic recurring-term and entity evidence over validated Phase 6 data."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

from .book_context import PRECEDENCE, _hash, serialize, validate_context_index

SCHEMA_VERSION = 1
DEFAULT_MINIMUM_OCCURRENCES = 2
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
EVIDENCE_KINDS = {
    "jmdict_vocabulary",
    "jmdict_expression",
    "jmnedict_name",
    "publisher_ruby_vocabulary",
    "publisher_ruby_name",
}
SAFE_REASONS = {
    "insufficient-recurrence",
    "ambiguous-name-candidates",
    "unmatched-source-reference",
    "incompatible-reading",
    "jmdict-jmnedict-conflict",
    "publisher-reading-conflict",
    "missing-dictionary-provenance",
    "unsupported-evidence-kind",
    "invalid-offset-or-source-text",
    "duplicate-or-overlapping-occurrence",
    "invalid-input",
    "schema-mismatch",
    "source-mismatch",
    "corrupt-input",
    "unsupported-version",
}


class ContextEvidenceError(ValueError):
    """Raised when evidence cannot be produced without guessing."""


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContextEvidenceError("Input JSON must be an object")
    return value


def _unique(values: list[dict[str, Any]], label: str, key: str = "id"):
    result = {}
    for value in values:
        identifier = value.get(key)
        if not isinstance(identifier, str) or not identifier or identifier in result:
            raise ContextEvidenceError(f"Duplicate or missing {label} ID")
        result[identifier] = value
    return result


def _validate_sources(
    index: dict[str, Any], vocabulary: dict[str, Any], plan: dict[str, Any]
):
    validate_context_index(index)
    if vocabulary.get("schema_version") != 4:
        raise ContextEvidenceError("Vocabulary report schema version must be 4")
    if (
        plan.get("schema_version") != 2
        or plan.get("source_annotation_plan_schema_version") != 1
    ):
        raise ContextEvidenceError("Enriched annotation plan schema version must be 2")
    if len({index.get("book_id"), vocabulary.get("book_id"), plan.get("book_id")}) != 1:
        raise ContextEvidenceError("Source book identity mismatch")
    if index.get("source_schemas") != {
        "canonical_book": 2,
        "vocabulary_report": 4,
        "enriched_annotation_plan": 2,
    }:
        raise ContextEvidenceError("Context-index source schema mismatch")
    for key in ("tokenizer", "dictionary", "name_dictionary"):
        if index.get(key) != vocabulary.get(key) or index.get(key) != plan.get(key):
            raise ContextEvidenceError(f"Source {key} provenance mismatch")


def _evidence_kind(item: dict[str, Any]) -> str:
    publisher = any(x.get("publisher_ruby_id") for x in item["occurrences"])
    if item["kind"] == "name":
        return "publisher_ruby_name" if publisher else "jmnedict_name"
    if item["kind"] == "expression":
        if publisher:
            raise ContextEvidenceError("Unsupported publisher-ruby expression")
        return "jmdict_expression"
    if item["kind"] == "vocabulary":
        return "publisher_ruby_vocabulary" if publisher else "jmdict_vocabulary"
    raise ContextEvidenceError("Unsupported evidence kind")


def _identity(item: dict[str, Any], kind: str):
    if kind == "jmdict_expression":
        lexical = item.get("normalized_form")
    elif kind in {"publisher_ruby_vocabulary", "publisher_ruby_name"}:
        lexical = item["surface"]
    elif kind == "jmnedict_name":
        lexical = tuple(item["source_entry_ids"])
    else:
        lexical = item.get("lemma")
    if not lexical:
        raise ContextEvidenceError("Missing grouping identity")
    return (
        kind,
        tuple(lexical) if isinstance(lexical, list) else lexical,
        item.get("reading"),
        item.get("reading_source"),
        tuple(item.get("source_entry_ids", [])),
    )


def _source_maps(index: dict[str, Any], vocabulary: dict[str, Any]):
    records = _unique(index["records"], "context record")
    occurrence_records = {}
    for record in index["records"]:
        for occurrence in record["study_occurrences"]:
            occurrence_id = occurrence["occurrence_id"]
            if occurrence_id in occurrence_records:
                raise ContextEvidenceError("Duplicate context occurrence ID")
            occurrence_records[occurrence_id] = (record, occurrence)
    return {
        "records": records,
        "occurrences": occurrence_records,
        "tokens": _unique(vocabulary.get("tokens", []), "token"),
        "candidates": _unique(vocabulary.get("candidates", []), "candidate"),
        "expressions": _unique(vocabulary.get("expressions", []), "expression"),
        "names": _unique(vocabulary.get("name_occurrences", []), "name"),
        "name_matches": _unique(
            vocabulary.get("name_dictionary_matches", []), "name match", "name_id"
        ),
    }


def _classification(item: dict[str, Any], kind: str, maps):
    if kind == "jmdict_expression":
        return "jmdict-expression-normalized-form"
    if kind == "publisher_ruby_vocabulary":
        return "publisher-ruby-authoritative-vocabulary"
    if kind == "publisher_ruby_name":
        name = maps["names"].get(item["name_id"])
        if name is None or name.get("classification_evidence") != "publisher_ruby":
            raise ContextEvidenceError("Missing publisher-backed name evidence")
        return "publisher-ruby-authoritative-name"
    if kind == "jmnedict_name":
        return "jmnedict-exact-name"
    return "jmdict-lemma"


def _location(record: dict[str, Any], occurrence: dict[str, Any]):
    return {
        "record_id": record["id"],
        "chapter_id": record["chapter_id"],
        "block_id": record["block_id"],
        "sentence_id": record["sentence_id"],
        "source_path": record["source_path"],
        "source_anchor": record["source_anchor"],
        "sentence_start": occurrence["sentence_start"],
        "sentence_end": occurrence["sentence_end"],
        "block_start": occurrence["block_start"],
        "block_end": occurrence["block_end"],
    }


def build_evidence_report(
    index: dict[str, Any],
    vocabulary: dict[str, Any],
    plan: dict[str, Any],
    *,
    minimum_occurrences: int = DEFAULT_MINIMUM_OCCURRENCES,
) -> dict[str, Any]:
    """Build exact recurring lexical/name evidence without selecting terminology."""
    _validate_sources(index, vocabulary, plan)
    if not isinstance(minimum_occurrences, int) or minimum_occurrences < 1:
        raise ContextEvidenceError("Minimum occurrences must be a positive integer")
    maps = _source_maps(index, vocabulary)
    items = _unique(plan.get("items", []), "study item")
    groups: OrderedDict[tuple, list[dict[str, Any]]] = OrderedDict()
    kinds = {}
    for item in plan["items"]:
        kind = _evidence_kind(item)
        key = _identity(item, kind)
        groups.setdefault(key, []).append(item)
        kinds[key] = kind

    output_groups = []
    diagnostics = []
    enrichment_by_item = {
        value["item_id"]: value for value in plan.get("enrichments", [])
    }
    global_occurrence_number = 0
    seen_occurrences = set()
    for group_number, (key, grouped_items) in enumerate(groups.items(), 1):
        kind = kinds[key]
        ordered_occurrences = []
        surface_forms = []
        item_ids = []
        for item in grouped_items:
            item_ids.append(item["id"])
            if item["surface"] not in surface_forms:
                surface_forms.append(item["surface"])
            for source_occurrence in item["occurrences"]:
                occurrence_id = source_occurrence["id"]
                if occurrence_id in seen_occurrences:
                    raise ContextEvidenceError("Duplicate evidence occurrence")
                seen_occurrences.add(occurrence_id)
                context_pair = maps["occurrences"].get(occurrence_id)
                if context_pair is None:
                    raise ContextEvidenceError("Unmatched context occurrence")
                record, indexed = context_pair
                fields = (
                    "token_ids",
                    "candidate_ids",
                    "expression_id",
                    "name_id",
                    "publisher_ruby_id",
                    "sentence_start",
                    "sentence_end",
                    "block_start",
                    "block_end",
                )
                if (
                    indexed["item_id"] != item["id"]
                    or any(indexed.get(field) != source_occurrence.get(field) for field in fields)
                    or record["text"][
                        source_occurrence["sentence_start"] :
                        source_occurrence["sentence_end"]
                    ]
                    != item["surface"]
                ):
                    raise ContextEvidenceError("Occurrence source or offset mismatch")
                if any(value not in maps["tokens"] for value in indexed["token_ids"]):
                    raise ContextEvidenceError("Unknown token reference")
                if any(
                    value not in maps["candidates"] for value in indexed["candidate_ids"]
                ):
                    raise ContextEvidenceError("Unknown candidate reference")
                if indexed["expression_id"] is not None and indexed[
                    "expression_id"
                ] not in maps["expressions"]:
                    raise ContextEvidenceError("Unknown expression reference")
                if indexed["name_id"] is not None and indexed["name_id"] not in maps["names"]:
                    raise ContextEvidenceError("Unknown name reference")
                if indexed.get("publisher_ruby_id"):
                    ruby = {
                        value["id"]: value for value in record["publisher_ruby"]
                    }.get(indexed["publisher_ruby_id"])
                    if (
                        ruby is None
                        or ruby["surface"] != item["surface"]
                        or ruby["reading"] != item["reading"]
                        or item["reading_source"] != "publisher"
                    ):
                        raise ContextEvidenceError("Publisher-reading conflict")
                global_occurrence_number += 1
                ordered_occurrences.append(
                    {
                        "id": f"evidence-occurrence-{global_occurrence_number:04d}",
                        "source_occurrence_id": occurrence_id,
                        "item_id": item["id"],
                        "record_id": record["id"],
                        "chapter_id": record["chapter_id"],
                        "block_id": record["block_id"],
                        "sentence_id": record["sentence_id"],
                        "token_ids": indexed["token_ids"],
                        "candidate_ids": indexed["candidate_ids"],
                        "expression_id": indexed["expression_id"],
                        "name_id": indexed["name_id"],
                        "publisher_ruby_id": indexed["publisher_ruby_id"],
                        "entry_ids": indexed["entry_ids"],
                        "sense_ids": indexed["sense_ids"],
                        "translation_ids": indexed["translation_ids"],
                        "sentence_start": indexed["sentence_start"],
                        "sentence_end": indexed["sentence_end"],
                        "block_start": indexed["block_start"],
                        "block_end": indexed["block_end"],
                    }
                )
        if len({item["reading"] for item in grouped_items}) != 1:
            raise ContextEvidenceError("Incompatible grouped readings")
        if len({item["reading_source"] for item in grouped_items}) != 1:
            raise ContextEvidenceError("Incompatible grouped reading sources")
        chapters = OrderedDict()
        for occurrence in ordered_occurrences:
            chapters[occurrence["chapter_id"]] = chapters.get(
                occurrence["chapter_id"], 0
            ) + 1
        count = len(ordered_occurrences)
        eligible = count >= minimum_occurrences
        eligibility_reason = (
            "meets-minimum-occurrences" if eligible else "insufficient-recurrence"
        )
        first_item = grouped_items[0]
        provenance = {
            "context_index_hash": _hash(index),
            "context_index_source_input_hash": index["source_input_hash"],
            "tokenizer": index["tokenizer"],
            "dictionary": (
                index["name_dictionary"]
                if kind in {"jmnedict_name", "publisher_ruby_name"}
                else index["dictionary"]
            ),
            "enriched_annotation_plan_schema_version": plan["schema_version"],
            "enrichment_ids": [
                enrichment_by_item[item["id"]]["id"]
                for item in grouped_items
                if item["id"] in enrichment_by_item
            ],
        }
        identity_payload = {
            "kind": kind,
            "surface_forms": surface_forms,
            "lemma": first_item.get("lemma"),
            "normalized_form": first_item.get("normalized_form"),
            "authoritative_reading": first_item["reading"],
            "reading_source": first_item["reading_source"],
            "item_ids": item_ids,
            "occurrences": ordered_occurrences,
            "provenance": provenance,
        }
        group = {
            "id": f"evidence-group-{group_number:04d}",
            "evidence_kind": kind,
            "surface_forms": surface_forms,
            "lemma": first_item.get("lemma"),
            "normalized_form": first_item.get("normalized_form"),
            "authoritative_reading": first_item["reading"],
            "reading_source": first_item["reading_source"],
            "item_ids": item_ids,
            "entry_ids": first_item["source_entry_ids"],
            "sense_ids": first_item["source_sense_ids"],
            "translation_ids": first_item["source_translation_ids"],
            "classification_evidence": _classification(first_item, kind, maps),
            "provenance": provenance,
            "occurrences": ordered_occurrences,
            "first_location": _location(
                maps["occurrences"][ordered_occurrences[0]["source_occurrence_id"]][0],
                maps["occurrences"][ordered_occurrences[0]["source_occurrence_id"]][1],
            ),
            "last_location": _location(
                maps["occurrences"][ordered_occurrences[-1]["source_occurrence_id"]][0],
                maps["occurrences"][ordered_occurrences[-1]["source_occurrence_id"]][1],
            ),
            "chapter_occurrence_counts": [
                {"chapter_id": chapter_id, "count": chapter_count}
                for chapter_id, chapter_count in chapters.items()
            ],
            "book_occurrence_count": count,
            "eligible_for_terminology_review": eligible,
            "eligibility_reason": eligibility_reason,
            "evidence_hash": _hash(identity_payload),
        }
        output_groups.append(group)
        if not eligible:
            diagnostics.append(
                {
                    "id": f"evidence-diagnostic-{len(diagnostics)+1:04d}",
                    "group_id": group["id"],
                    "item_id": first_item["id"],
                    "reason": "insufficient-recurrence",
                }
            )
        if kind in {"jmnedict_name", "publisher_ruby_name"}:
            match = maps["name_matches"].get(first_item["name_id"])
            if match is None:
                raise ContextEvidenceError("Missing JMnedict match")
            if len(match.get("entries", [])) > 1:
                diagnostics.append(
                    {
                        "id": f"evidence-diagnostic-{len(diagnostics)+1:04d}",
                        "group_id": group["id"],
                        "item_id": first_item["id"],
                        "reason": "ambiguous-name-candidates",
                    }
                )

    result = {
        "schema_version": SCHEMA_VERSION,
        "book_id": index["book_id"],
        "source_schemas": {
            "context_index": index["schema_version"],
            "vocabulary_report": vocabulary["schema_version"],
            "enriched_annotation_plan": plan["schema_version"],
        },
        "source_hashes": {
            "context_index_source_input": index["source_input_hash"],
            "context_index": _hash(index),
            "vocabulary_report": _hash(vocabulary),
            "enriched_annotation_plan": _hash(plan),
        },
        "configuration": {"minimum_occurrences": minimum_occurrences},
        "tokenizer": index["tokenizer"],
        "dictionary": index["dictionary"],
        "name_dictionary": index["name_dictionary"],
        "enrichment_provenance": {
            "schema_version": plan["schema_version"],
            "enrichment_ids": [value["id"] for value in plan.get("enrichments", [])],
            "meaning_provenance": [
                value["meaning_provenance"] for value in plan.get("enrichments", [])
            ],
        },
        "precedence": PRECEDENCE,
        "groups": output_groups,
        "diagnostics": diagnostics,
    }
    validate_evidence_report(result)
    return result


def validate_evidence_report(report: dict[str, Any]):
    required = {
        "schema_version",
        "book_id",
        "source_schemas",
        "source_hashes",
        "configuration",
        "tokenizer",
        "dictionary",
        "name_dictionary",
        "enrichment_provenance",
        "precedence",
        "groups",
        "diagnostics",
    }
    if set(report) != required or report.get("schema_version") != SCHEMA_VERSION:
        raise ContextEvidenceError("Invalid evidence-report schema")
    if report.get("source_schemas") != {
        "context_index": 1,
        "vocabulary_report": 4,
        "enriched_annotation_plan": 2,
    }:
        raise ContextEvidenceError("Invalid evidence source schemas")
    minimum = report.get("configuration", {}).get("minimum_occurrences")
    if not isinstance(minimum, int) or minimum < 1:
        raise ContextEvidenceError("Invalid evidence configuration")
    if report.get("precedence") != PRECEDENCE:
        raise ContextEvidenceError("Invalid evidence precedence")
    if any(not HEX_SHA256.fullmatch(value) for value in report["source_hashes"].values()):
        raise ContextEvidenceError("Invalid source hash")
    occurrence_ids = set()
    occurrence_id_order = []
    group_ids = set()
    item_ids = set()
    previous_location = None
    for number, group in enumerate(report["groups"], 1):
        if set(group) != {
            "id",
            "evidence_kind",
            "surface_forms",
            "lemma",
            "normalized_form",
            "authoritative_reading",
            "reading_source",
            "item_ids",
            "entry_ids",
            "sense_ids",
            "translation_ids",
            "classification_evidence",
            "provenance",
            "occurrences",
            "first_location",
            "last_location",
            "chapter_occurrence_counts",
            "book_occurrence_count",
            "eligible_for_terminology_review",
            "eligibility_reason",
            "evidence_hash",
        }:
            raise ContextEvidenceError("Unsupported evidence-group fields")
        if (
            group["id"] != f"evidence-group-{number:04d}"
            or group["id"] in group_ids
            or group["evidence_kind"] not in EVIDENCE_KINDS
            or not group["occurrences"]
        ):
            raise ContextEvidenceError("Unstable or invalid evidence group")
        group_ids.add(group["id"])
        item_ids.update(group["item_ids"])
        provenance = group["provenance"]
        if (
            set(provenance)
            != {
                "context_index_hash",
                "context_index_source_input_hash",
                "tokenizer",
                "dictionary",
                "enriched_annotation_plan_schema_version",
                "enrichment_ids",
            }
            or provenance["enriched_annotation_plan_schema_version"] != 2
            or not HEX_SHA256.fullmatch(provenance["context_index_hash"])
            or not HEX_SHA256.fullmatch(provenance["context_index_source_input_hash"])
            or not provenance["tokenizer"]
            or not provenance["dictionary"]
            or len(provenance["enrichment_ids"])
            != len(set(provenance["enrichment_ids"]))
        ):
            raise ContextEvidenceError("Invalid group provenance")
        first = group["occurrences"][0]
        last = group["occurrences"][-1]
        if (
            group["first_location"]["record_id"] != first["record_id"]
            or group["last_location"]["record_id"] != last["record_id"]
            or group["book_occurrence_count"] != len(group["occurrences"])
        ):
            raise ContextEvidenceError("Incorrect evidence locations or count")
        expected_eligible = len(group["occurrences"]) >= minimum
        if (
            group["eligible_for_terminology_review"] != expected_eligible
            or group["eligibility_reason"]
            != (
                "meets-minimum-occurrences"
                if expected_eligible
                else "insufficient-recurrence"
            )
        ):
            raise ContextEvidenceError("Incorrect evidence eligibility")
        chapter_counts = OrderedDict()
        for occurrence in group["occurrences"]:
            occurrence_id = occurrence["id"]
            if set(occurrence) != {
                "id",
                "source_occurrence_id",
                "item_id",
                "record_id",
                "chapter_id",
                "block_id",
                "sentence_id",
                "token_ids",
                "candidate_ids",
                "expression_id",
                "name_id",
                "publisher_ruby_id",
                "entry_ids",
                "sense_ids",
                "translation_ids",
                "sentence_start",
                "sentence_end",
                "block_start",
                "block_end",
            }:
                raise ContextEvidenceError("Unsupported evidence-occurrence fields")
            if occurrence_id in occurrence_ids:
                raise ContextEvidenceError("Duplicate evidence-occurrence ID")
            occurrence_ids.add(occurrence_id)
            occurrence_id_order.append(occurrence_id)
            location = (
                occurrence["chapter_id"],
                occurrence["block_id"],
                occurrence["sentence_id"],
                occurrence["sentence_start"],
            )
            if previous_location is not None and location < previous_location:
                raise ContextEvidenceError("Unordered evidence occurrences")
            previous_location = location
            chapter_counts[occurrence["chapter_id"]] = chapter_counts.get(
                occurrence["chapter_id"], 0
            ) + 1
        for location, occurrence in (
            (group["first_location"], first),
            (group["last_location"], last),
        ):
            if any(
                location[key] != occurrence[key]
                for key in (
                    "record_id",
                    "chapter_id",
                    "block_id",
                    "sentence_id",
                    "sentence_start",
                    "sentence_end",
                    "block_start",
                    "block_end",
                )
            ):
                raise ContextEvidenceError("Incorrect evidence location details")
        if group["chapter_occurrence_counts"] != [
            {"chapter_id": key, "count": value} for key, value in chapter_counts.items()
        ]:
            raise ContextEvidenceError("Incorrect chapter occurrence counts")
        payload = {
            "kind": group["evidence_kind"],
            "surface_forms": group["surface_forms"],
            "lemma": group["lemma"],
            "normalized_form": group["normalized_form"],
            "authoritative_reading": group["authoritative_reading"],
            "reading_source": group["reading_source"],
            "item_ids": group["item_ids"],
            "occurrences": group["occurrences"],
            "provenance": group["provenance"],
        }
        if group["evidence_hash"] != _hash(payload):
            raise ContextEvidenceError("Invalid evidence hash")
        if group["evidence_kind"] in {"jmnedict_name", "publisher_ruby_name"}:
            if group["sense_ids"] or not group["translation_ids"]:
                raise ContextEvidenceError("JMdict/JMnedict evidence conflict")
        elif group["translation_ids"] or not group["sense_ids"]:
            raise ContextEvidenceError("JMdict/JMnedict evidence conflict")
        if group["evidence_kind"].startswith("publisher_ruby") and group[
            "reading_source"
        ] != "publisher":
            raise ContextEvidenceError("Publisher-reading precedence violation")
    expected_occurrence_ids = [
        f"evidence-occurrence-{number:04d}"
        for number in range(1, len(occurrence_ids) + 1)
    ]
    if occurrence_id_order != expected_occurrence_ids:
        raise ContextEvidenceError("Unstable evidence-occurrence IDs")
    diagnostic_ids = set()
    for number, diagnostic in enumerate(report["diagnostics"], 1):
        if (
            set(diagnostic) != {"id", "group_id", "item_id", "reason"}
            or diagnostic["id"] != f"evidence-diagnostic-{number:04d}"
            or diagnostic["id"] in diagnostic_ids
            or diagnostic["group_id"] not in group_ids
            or diagnostic["item_id"] not in item_ids
            or diagnostic["reason"] not in SAFE_REASONS
        ):
            raise ContextEvidenceError("Invalid evidence diagnostic")
        diagnostic_ids.add(diagnostic["id"])


def disabled_evidence(plan: dict[str, Any]):
    return (
        {
            "schema_version": SCHEMA_VERSION,
            "status": "disabled",
            "groups": [],
            "diagnostics": [],
        },
        plan,
    )


def safe_failure(plan: dict[str, Any], reason: str):
    if reason not in SAFE_REASONS:
        reason = "invalid-input"
    return (
        {
            "schema_version": SCHEMA_VERSION,
            "status": "fallback",
            "groups": [],
            "diagnostics": [
                {
                    "id": "evidence-diagnostic-0001",
                    "reason": reason,
                }
            ],
        },
        plan,
    )
