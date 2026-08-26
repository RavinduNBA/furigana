"""Deterministic Phase 6 book-context indexing and bounded retrieval."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

INDEX_SCHEMA_VERSION = 1
RETRIEVAL_SCHEMA_VERSION = 1
DEFAULT_SENTENCE_BUDGET = 3
DEFAULT_CHARACTER_BUDGET = 500
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
PRECEDENCE = ["publisher", "user", "dictionary", "book_context", "model"]


class BookContextError(ValueError):
    """Raised when Phase 6 context cannot be built or retrieved safely."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def serialize(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BookContextError("Input JSON must be an object")
    return value


def _unique_index(values: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result = {}
    for value in values:
        identifier = value.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in result:
            raise BookContextError(f"Duplicate or missing {label} ID")
        result[identifier] = value
    return result


def _validate_inputs(book: dict[str, Any], vocabulary: dict[str, Any], plan: dict[str, Any]):
    if book.get("schema_version") != 2:
        raise BookContextError("Canonical book schema version must be 2")
    if vocabulary.get("schema_version") != 4:
        raise BookContextError("Vocabulary report schema version must be 4")
    if (
        plan.get("schema_version") != 2
        or plan.get("source_annotation_plan_schema_version") != 1
    ):
        raise BookContextError("Enriched annotation plan schema version must be 2")
    book_ids = {book.get("book_id"), vocabulary.get("book_id"), plan.get("book_id")}
    if len(book_ids) != 1 or None in book_ids:
        raise BookContextError("Source book identity mismatch")
    if vocabulary.get("source_book_schema_version") != book["schema_version"]:
        raise BookContextError("Vocabulary/canonical schema mismatch")
    for key in ("tokenizer", "dictionary", "name_dictionary"):
        if vocabulary.get(key) != plan.get(key):
            raise BookContextError(f"Plan/vocabulary {key} provenance mismatch")


def _source_sets(vocabulary: dict[str, Any]) -> dict[str, set[str]]:
    return {
        "token": set(_unique_index(vocabulary.get("tokens", []), "token")),
        "candidate": set(_unique_index(vocabulary.get("candidates", []), "candidate")),
        "expression": set(_unique_index(vocabulary.get("expressions", []), "expression")),
        "name": set(_unique_index(vocabulary.get("name_occurrences", []), "name")),
        "entry": {
            entry["entry_id"]
            for key in (
                "dictionary_matches",
                "expression_dictionary_matches",
                "name_dictionary_matches",
            )
            for match in vocabulary.get(key, [])
            for entry in match.get("entries", [])
        },
        "sense": {
            sense["id"]
            for key in ("dictionary_matches", "expression_dictionary_matches")
            for match in vocabulary.get(key, [])
            for entry in match.get("entries", [])
            for sense in entry.get("senses", [])
        },
        "translation": {
            translation["id"]
            for match in vocabulary.get("name_dictionary_matches", [])
            for entry in match.get("entries", [])
            for translation in entry.get("translations", [])
        },
    }


def build_context_index(
    book: dict[str, Any], vocabulary: dict[str, Any], plan: dict[str, Any]
) -> dict[str, Any]:
    """Build a versioned sentence index without altering any source model."""
    _validate_inputs(book, vocabulary, plan)
    sources = _source_sets(vocabulary)
    source_surfaces = {
        "candidate": {
            value["id"]: value["surface"]
            for value in vocabulary.get("candidates", [])
        },
        "expression": {
            value["id"]: value["surface"]
            for value in vocabulary.get("expressions", [])
        },
        "name": {
            value["id"]: value["surface"]
            for value in vocabulary.get("name_occurrences", [])
        },
    }
    occurrences = {}
    occurrences_by_sentence: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for item in plan.get("items", []):
        expected_kind = "jmnedict" if item["kind"] == "name" else "jmdict"
        entry_ids = item.get("source_entry_ids", [])
        sense_ids = item.get("source_sense_ids", [])
        translation_ids = item.get("source_translation_ids", [])
        if (
            any(value not in sources["entry"] for value in entry_ids)
            or any(value not in sources["sense"] for value in sense_ids)
            or any(value not in sources["translation"] for value in translation_ids)
        ):
            raise BookContextError("Unknown dictionary reference in study item")
        if (expected_kind == "jmnedict") != bool(translation_ids):
            raise BookContextError("JMdict/JMnedict item reference mismatch")
        for occurrence in item.get("occurrences", []):
            occurrence_id = occurrence.get("id")
            if not occurrence_id or occurrence_id in occurrences:
                raise BookContextError("Duplicate or missing occurrence ID")
            occurrences[occurrence_id] = occurrence
            for key, singular in (
                ("token_ids", "token"),
                ("candidate_ids", "candidate"),
            ):
                if any(value not in sources[singular] for value in occurrence.get(key, [])):
                    raise BookContextError(f"Unknown {singular} reference")
            for key, singular in (("expression_id", "expression"), ("name_id", "name")):
                value = occurrence.get(key)
                if value is not None and value not in sources[singular]:
                    raise BookContextError(f"Unknown {singular} reference")
            occurrences_by_sentence.setdefault(occurrence["sentence_id"], []).append(
                (item, occurrence)
            )

    records = []
    chapter_ids, block_ids, sentence_ids, ruby_ids = set(), set(), set(), set()
    record_number = 0
    for chapter in book.get("chapters", []):
        chapter_id = chapter.get("id")
        if chapter_id in chapter_ids:
            raise BookContextError("Duplicate chapter ID")
        chapter_ids.add(chapter_id)
        for block in chapter.get("blocks", []):
            block_id = block.get("id")
            if block_id in block_ids:
                raise BookContextError("Duplicate block ID")
            block_ids.add(block_id)
            ruby_by_id = {}
            for ruby in block.get("publisher_ruby", []):
                ruby_id = ruby.get("id")
                if ruby_id in ruby_ids:
                    raise BookContextError("Duplicate publisher-ruby ID")
                ruby_ids.add(ruby_id)
                ruby_by_id[ruby_id] = ruby
                if block["text"][ruby["start"] : ruby["end"]] != ruby["surface"]:
                    raise BookContextError("Publisher-ruby text mismatch")
            for sentence in block.get("sentences", []):
                sentence_id = sentence.get("id")
                if sentence_id in sentence_ids:
                    raise BookContextError("Duplicate sentence ID")
                sentence_ids.add(sentence_id)
                if block["text"][sentence["start"] : sentence["end"]] != sentence["text"]:
                    raise BookContextError("Canonical sentence text mismatch")
                attached = []
                for item, occurrence in occurrences_by_sentence.get(sentence_id, []):
                    occurrence_surface = sentence["text"][
                        occurrence["sentence_start"] : occurrence["sentence_end"]
                    ]
                    if item["kind"] == "expression":
                        expected_surface = source_surfaces["expression"].get(
                            occurrence.get("expression_id")
                        )
                    elif item["kind"] == "name":
                        expected_surface = source_surfaces["name"].get(
                            occurrence.get("name_id")
                        )
                    else:
                        candidate_ids = occurrence.get("candidate_ids", [])
                        expected_surface = (
                            source_surfaces["candidate"].get(candidate_ids[0])
                            if len(candidate_ids) == 1
                            else None
                        )
                    if (
                        occurrence["chapter_id"] != chapter_id
                        or occurrence["block_id"] != block_id
                        or occurrence_surface != expected_surface
                    ):
                        raise BookContextError("Occurrence source or offset mismatch")
                    ruby_id = occurrence.get("publisher_ruby_id")
                    if ruby_id is not None:
                        ruby = ruby_by_id.get(ruby_id)
                        if (
                            ruby is None
                            or item["reading_source"] != "publisher"
                            or item["reading"] != ruby.get("reading")
                            or occurrence_surface != ruby.get("surface")
                        ):
                            raise BookContextError("Publisher-reading precedence violation")
                    attached.append(
                        {
                            "item_id": item["id"],
                            "occurrence_id": occurrence["id"],
                            "item_kind": item["kind"],
                            "surface": occurrence_surface,
                            "authoritative_reading": item["reading"],
                            "reading_source": item["reading_source"],
                            "token_ids": occurrence["token_ids"],
                            "candidate_ids": occurrence["candidate_ids"],
                            "expression_id": occurrence.get("expression_id"),
                            "name_id": occurrence.get("name_id"),
                            "publisher_ruby_id": ruby_id,
                            "sentence_start": occurrence["sentence_start"],
                            "sentence_end": occurrence["sentence_end"],
                            "block_start": occurrence["block_start"],
                            "block_end": occurrence["block_end"],
                            "dictionary_kind": (
                                "jmnedict" if item["kind"] == "name" else "jmdict"
                            ),
                            "entry_ids": item["source_entry_ids"],
                            "sense_ids": item["source_sense_ids"],
                            "translation_ids": item["source_translation_ids"],
                        }
                    )
                record_number += 1
                records.append(
                    {
                        "id": f"book-context-record-{record_number:04d}",
                        "chapter_id": chapter_id,
                        "block_id": block_id,
                        "sentence_id": sentence_id,
                        "source_path": chapter["source_path"],
                        "source_anchor": block.get("source_anchor"),
                        "text": sentence["text"],
                        "block_start": sentence["start"],
                        "block_end": sentence["end"],
                        "publisher_ruby": [
                            {
                                "id": ruby_id,
                                "surface": ruby_by_id[ruby_id]["surface"],
                                "reading": ruby_by_id[ruby_id].get("reading"),
                                "source": ruby_by_id[ruby_id]["source"],
                                "source_anchor": ruby_by_id[ruby_id].get("source_anchor"),
                            }
                            for ruby_id in sentence.get("publisher_ruby", [])
                        ],
                        "study_occurrences": attached,
                    }
                )
    if set(occurrences_by_sentence) - sentence_ids:
        raise BookContextError("Unknown occurrence sentence reference")
    result = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "book_id": book["book_id"],
        "source_schemas": {
            "canonical_book": book["schema_version"],
            "vocabulary_report": vocabulary["schema_version"],
            "enriched_annotation_plan": plan["schema_version"],
        },
        "source_input_hash": _hash(
            {"book": book, "vocabulary": vocabulary, "annotation_plan": plan}
        ),
        "tokenizer": plan["tokenizer"],
        "dictionary": plan["dictionary"],
        "name_dictionary": plan["name_dictionary"],
        "precedence": PRECEDENCE,
        "records": records,
    }
    validate_context_index(result)
    return result


def validate_context_index(index: dict[str, Any]):
    required = {
        "schema_version",
        "book_id",
        "source_schemas",
        "source_input_hash",
        "tokenizer",
        "dictionary",
        "name_dictionary",
        "precedence",
        "records",
    }
    if set(index) != required or index.get("schema_version") != INDEX_SCHEMA_VERSION:
        raise BookContextError("Invalid context-index schema")
    if not HEX_SHA256.fullmatch(index.get("source_input_hash", "")):
        raise BookContextError("Invalid source-input hash")
    if index.get("precedence") != PRECEDENCE:
        raise BookContextError("Invalid provenance precedence")
    seen, previous_location = set(), None
    for number, record in enumerate(index.get("records", []), 1):
        if set(record) != {
            "id",
            "chapter_id",
            "block_id",
            "sentence_id",
            "source_path",
            "source_anchor",
            "text",
            "block_start",
            "block_end",
            "publisher_ruby",
            "study_occurrences",
        }:
            raise BookContextError("Unsupported context-record fields")
        if record["id"] != f"book-context-record-{number:04d}" or record["id"] in seen:
            raise BookContextError("Unstable or duplicate context-record ID")
        seen.add(record["id"])
        location = (record["chapter_id"], record["block_id"], record["block_start"])
        if previous_location is not None and location < previous_location:
            raise BookContextError("Noncanonical context-record ordering")
        previous_location = location
        if not isinstance(record["text"], str) or not record["text"]:
            raise BookContextError("Missing canonical sentence text")
        for ruby in record["publisher_ruby"]:
            if set(ruby) != {
                "id",
                "surface",
                "reading",
                "source",
                "source_anchor",
            }:
                raise BookContextError("Unsupported publisher-ruby fields")
        for occurrence in record["study_occurrences"]:
            if set(occurrence) != {
                "item_id",
                "occurrence_id",
                "item_kind",
                "surface",
                "authoritative_reading",
                "reading_source",
                "token_ids",
                "candidate_ids",
                "expression_id",
                "name_id",
                "publisher_ruby_id",
                "sentence_start",
                "sentence_end",
                "block_start",
                "block_end",
                "dictionary_kind",
                "entry_ids",
                "sense_ids",
                "translation_ids",
            }:
                raise BookContextError("Unsupported study-occurrence fields")
            expected_dictionary = (
                "jmnedict" if occurrence["item_kind"] == "name" else "jmdict"
            )
            if occurrence["dictionary_kind"] != expected_dictionary:
                raise BookContextError("JMdict/JMnedict occurrence mismatch")
            if occurrence["reading_source"] == "publisher":
                ruby = {
                    value["id"]: value for value in record["publisher_ruby"]
                }.get(occurrence["publisher_ruby_id"])
                if (
                    ruby is None
                    or ruby["reading"] != occurrence["authoritative_reading"]
                    or ruby["surface"] != occurrence["surface"]
                ):
                    raise BookContextError("Publisher reading was not preserved")


def _query_target(
    index: dict[str, Any], item_id: str | None, occurrence_id: str | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    matches = []
    for record in index["records"]:
        for occurrence in record["study_occurrences"]:
            if occurrence_id is not None and occurrence["occurrence_id"] == occurrence_id:
                matches.append((record, occurrence))
            elif occurrence_id is None and occurrence["item_id"] == item_id:
                matches.append((record, occurrence))
    if occurrence_id is not None:
        if len(matches) != 1:
            raise BookContextError("Unknown or duplicate occurrence query")
        return matches[0]
    if item_id is None or not matches:
        raise BookContextError("Unknown study-item query")
    return matches[0]


def retrieve_context(
    index: dict[str, Any],
    *,
    item_id: str | None = None,
    occurrence_id: str | None = None,
    previous: int = 1,
    following: int = 1,
    scope: str = "block",
    sentence_budget: int = DEFAULT_SENTENCE_BUDGET,
    character_budget: int = DEFAULT_CHARACTER_BUDGET,
) -> dict[str, Any]:
    validate_context_index(index)
    if (item_id is None) == (occurrence_id is None):
        raise BookContextError("Specify exactly one item or occurrence")
    if (
        not isinstance(previous, int)
        or not isinstance(following, int)
        or previous < 0
        or following < 0
        or scope not in {"block", "chapter"}
        or not isinstance(sentence_budget, int)
        or sentence_budget < 1
        or not isinstance(character_budget, int)
        or character_budget < 1
    ):
        raise BookContextError("Invalid retrieval configuration")
    containing, occurrence = _query_target(index, item_id, occurrence_id)
    eligible = [
        record
        for record in index["records"]
        if record["chapter_id"] == containing["chapter_id"]
        and (scope == "chapter" or record["block_id"] == containing["block_id"])
    ]
    target_position = eligible.index(containing)
    before = eligible[max(0, target_position - previous) : target_position]
    after = eligible[target_position + 1 : target_position + 1 + following]
    candidates = [
        *[(record, "previous") for record in before],
        (containing, "containing"),
        *[(record, "following") for record in after],
    ]
    selected = [(containing, "containing")]
    used_characters = len(containing["text"])
    if used_characters > character_budget:
        raise BookContextError("Containing sentence exceeds character budget")
    for record, reason in candidates:
        if reason == "containing":
            continue
        if (
            len(selected) >= sentence_budget
            or used_characters + len(record["text"]) > character_budget
        ):
            continue
        selected.append((record, reason))
        used_characters += len(record["text"])
    order = {record["id"]: number for number, record in enumerate(index["records"])}
    selected.sort(key=lambda value: order[value[0]["id"]])
    query = {
        "item_id": occurrence["item_id"],
        "occurrence_id": occurrence_id,
        "resolved_occurrence_id": occurrence["occurrence_id"],
        "previous": previous,
        "following": following,
        "scope": scope,
        "sentence_budget": sentence_budget,
        "character_budget": character_budget,
    }
    contexts = [
        {
            "record_id": record["id"],
            "chapter_id": record["chapter_id"],
            "block_id": record["block_id"],
            "sentence_id": record["sentence_id"],
            "source_path": record["source_path"],
            "source_anchor": record["source_anchor"],
            "text": record["text"],
            "reason": reason,
        }
        for record, reason in selected
    ]
    result = {
        "schema_version": RETRIEVAL_SCHEMA_VERSION,
        "book_id": index["book_id"],
        "index_source_input_hash": index["source_input_hash"],
        "query": query,
        "query_hash": _hash(query),
        "contexts": contexts,
        "result_hash": _hash(contexts),
        "character_count": sum(len(value["text"]) for value in contexts),
        "precedence": index["precedence"],
        "target": occurrence,
    }
    validate_retrieval(result, index)
    return result


def validate_retrieval(result: dict[str, Any], index: dict[str, Any]):
    required = {
        "schema_version",
        "book_id",
        "index_source_input_hash",
        "query",
        "query_hash",
        "contexts",
        "result_hash",
        "character_count",
        "precedence",
        "target",
    }
    if set(result) != required or result.get("schema_version") != 1:
        raise BookContextError("Invalid retrieval schema")
    if (
        result["book_id"] != index["book_id"]
        or result["index_source_input_hash"] != index["source_input_hash"]
        or result["precedence"] != index["precedence"]
        or result["query_hash"] != _hash(result["query"])
        or result["result_hash"] != _hash(result["contexts"])
    ):
        raise BookContextError("Retrieval identity or hash mismatch")
    if set(result["query"]) != {
        "item_id",
        "occurrence_id",
        "resolved_occurrence_id",
        "previous",
        "following",
        "scope",
        "sentence_budget",
        "character_budget",
    }:
        raise BookContextError("Unsupported retrieval-query fields")
    records = {record["id"]: record for record in index["records"]}
    positions = {record["id"]: number for number, record in enumerate(index["records"])}
    context_ids = [value["record_id"] for value in result["contexts"]]
    if (
        not context_ids
        or len(context_ids) != len(set(context_ids))
        or context_ids != sorted(context_ids, key=positions.get)
        or len(context_ids) > result["query"]["sentence_budget"]
        or result["character_count"] > result["query"]["character_budget"]
        or result["character_count"]
        != sum(len(value["text"]) for value in result["contexts"])
    ):
        raise BookContextError("Invalid retrieval ordering or budget")
    containing = [value for value in result["contexts"] if value["reason"] == "containing"]
    if len(containing) != 1 or containing[0]["sentence_id"] != result["target"].get(
        "sentence_id", containing[0]["sentence_id"]
    ):
        # target occurrence does not duplicate sentence_id; its source is checked below.
        if len(containing) != 1:
            raise BookContextError("Missing containing sentence")
    containing_record = records.get(containing[0]["record_id"])
    if containing_record is None or not any(
        occurrence["occurrence_id"] == result["target"]["occurrence_id"]
        for occurrence in containing_record["study_occurrences"]
    ):
        raise BookContextError("Containing sentence/target mismatch")
    eligible = [
        record
        for record in index["records"]
        if record["chapter_id"] == containing_record["chapter_id"]
        and (
            result["query"]["scope"] == "chapter"
            or record["block_id"] == containing_record["block_id"]
        )
    ]
    target_position = eligible.index(containing_record)
    allowed = {
        record["id"]
        for record in eligible[
            max(0, target_position - result["query"]["previous"]) :
            target_position + result["query"]["following"] + 1
        ]
    }
    if any(record_id not in allowed for record_id in context_ids):
        raise BookContextError("Retrieval exceeded configured adjacency window")
    for context in result["contexts"]:
        record = records.get(context["record_id"])
        if record is None or any(
            context[key] != record[key]
            for key in (
                "chapter_id",
                "block_id",
                "sentence_id",
                "source_path",
                "source_anchor",
                "text",
            )
        ):
            raise BookContextError("Retrieval context mismatch")
        if context["chapter_id"] != containing_record["chapter_id"]:
            raise BookContextError("Retrieval crossed chapter boundary")
        if (
            result["query"]["scope"] == "block"
            and context["block_id"] != containing_record["block_id"]
        ):
            raise BookContextError("Retrieval crossed block boundary")


def build_retrieval_report(
    index: dict[str, Any],
    queries: list[dict[str, Any]],
) -> dict[str, Any]:
    results = [retrieve_context(index, **query) for query in queries]
    return {
        "schema_version": RETRIEVAL_SCHEMA_VERSION,
        "book_id": index["book_id"],
        "index_source_input_hash": index["source_input_hash"],
        "results": results,
    }


def disabled_context(plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return an empty augmentation and the original plan object unchanged."""
    return (
        {
            "schema_version": RETRIEVAL_SCHEMA_VERSION,
            "status": "disabled",
            "results": [],
            "diagnostics": [],
        },
        plan,
    )


def safe_failure(plan: dict[str, Any], reason: str) -> tuple[dict[str, Any], dict[str, Any]]:
    safe_reasons = {
        "invalid-input",
        "schema-mismatch",
        "source-mismatch",
        "corrupt-input",
        "unsupported-version",
    }
    if reason not in safe_reasons:
        reason = "invalid-input"
    return (
        {
            "schema_version": RETRIEVAL_SCHEMA_VERSION,
            "status": "fallback",
            "results": [],
            "diagnostics": [
                {
                    "id": "book-context-diagnostic-0001",
                    "reason": reason,
                }
            ],
        },
        plan,
    )
