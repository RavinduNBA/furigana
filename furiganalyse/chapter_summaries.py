"""Deterministic chapter packets and explicitly approved summary retrieval."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from .book_context import PRECEDENCE, _hash, validate_context_index
from .context_evidence import validate_evidence_report

PACKET_SCHEMA_VERSION = 1
REGISTRY_SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = 1
RETRIEVAL_SCHEMA_VERSION = 1
MAX_SUMMARY_LENGTH = 240
MAX_NOTE_LENGTH = 240
DEFAULT_SUMMARY_BUDGET = 2
DEFAULT_CHARACTER_BUDGET = 500
STATUSES = {"approved", "rejected", "deferred"}
CONSISTENCY_STATUSES = {
    "approved-user-summary",
    "rejected-by-user",
    "deferred-by-user",
    "missing-summary-decision",
}
SAFE_REASONS = {
    "missing-summary-decision",
    "stale-packet-hash",
    "unknown-chapter-or-packet",
    "duplicate-decision",
    "invalid-status",
    "unsafe-or-missing-approved-summary",
    "summary-for-non-approved-status",
    "unsupported-evidence-or-terminology-reference",
    "publisher-reading-or-terminology-conflict",
    "approved-terminology-missing-from-summary",
    "unused-decision",
    "budget-exclusion",
    "unsupported-schema-or-fields",
    "invalid-registry",
    "corrupt-registry",
}
SAFE_TEXT = re.compile(
    r"[<>]|https?://|www\.|(?:^|\s)(?:/|~[/\\])|[A-Za-z]:\\|"
    r"(?:api[_-]?key|password|secret|token)\s*[:=]|"
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]",
    re.IGNORECASE,
)


class ChapterSummaryError(ValueError):
    """Raised when chapter summary data cannot be trusted."""


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ChapterSummaryError("Input JSON must be an object")
    return value


def _valid_text(value: Any, maximum: int, *, required: bool) -> bool:
    if value is None:
        return not required
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= maximum
        and SAFE_TEXT.search(value) is None
    )


def _valid_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _without(value: dict[str, Any], key: str) -> dict[str, Any]:
    return {name: item for name, item in value.items() if name != key}


def with_decision_hash(decision: dict[str, Any]) -> dict[str, Any]:
    value = dict(decision)
    value["decision_hash"] = _hash(_without(value, "decision_hash"))
    return value


def _deduplicate(values):
    return list(dict.fromkeys(values))


def _validate_sources(index, evidence, terminology):
    validate_context_index(index)
    validate_evidence_report(evidence)
    if terminology.get("schema_version") != 1:
        raise ChapterSummaryError("Terminology report schema must be 1")
    if len({index.get("book_id"), evidence.get("book_id"), terminology.get("book_id")}) != 1:
        raise ChapterSummaryError("Source book identity mismatch")
    if evidence["source_hashes"]["context_index"] != _hash(index):
        raise ChapterSummaryError("Evidence/context-index hash mismatch")
    if terminology["source_hashes"]["context_index"] != _hash(index):
        raise ChapterSummaryError("Terminology/context-index hash mismatch")
    if terminology["source_hashes"]["evidence_report"] != _hash(evidence):
        raise ChapterSummaryError("Terminology/evidence hash mismatch")


def build_chapter_packets(index, evidence, terminology):
    """Build reference-only chapter packets in canonical chapter order."""
    _validate_sources(index, evidence, terminology)
    groups = {value["id"]: value for value in evidence["groups"]}
    results = {value["evidence_group_id"]: value for value in terminology["results"]}
    chapter_order = _deduplicate(record["chapter_id"] for record in index["records"])
    packets = []
    for number, chapter_id in enumerate(chapter_order, 1):
        records = [value for value in index["records"] if value["chapter_id"] == chapter_id]
        source_paths = _deduplicate(value["source_path"] for value in records)
        if len(source_paths) != 1:
            raise ChapterSummaryError("Chapter has ambiguous source paths")
        chapter_group_ids = [
            group["id"]
            for group in evidence["groups"]
            if any(count["chapter_id"] == chapter_id for count in group["chapter_occurrence_counts"])
        ]
        chapter_results = [results[value] for value in chapter_group_ids]
        item_ids = _deduplicate(
            occurrence["item_id"]
            for record in records
            for occurrence in record["study_occurrences"]
        )
        ruby = []
        for record in records:
            ruby.extend(record["publisher_ruby"])
        jmdict_groups = [
            groups[value] for value in chapter_group_ids
            if groups[value]["evidence_kind"] not in {"jmnedict_name", "publisher_ruby_name"}
        ]
        jmnedict_groups = [
            groups[value] for value in chapter_group_ids
            if groups[value]["evidence_kind"] in {"jmnedict_name", "publisher_ruby_name"}
        ]
        effective = [
            {
                "evidence_group_id": value["evidence_group_id"],
                "terminology_result_id": value["id"],
                "decision_id": value["decision_id"],
                "term": value["approved_term"],
                "source": value["effective_terminology_source"],
            }
            for value in chapter_results
            if value["consistency_status"] == "consistent-user-approved"
        ]
        packet = {
            "id": f"chapter-context-packet-{number:04d}",
            "chapter_id": chapter_id,
            "chapter_order": number,
            "source_path": source_paths[0],
            "sentence_record_ids": [value["id"] for value in records],
            "sentence_count": len(records),
            "character_count": sum(len(value["text"]) for value in records),
            "study_item_ids": item_ids,
            "study_occurrence_ids": _deduplicate(
                occurrence["occurrence_id"]
                for record in records
                for occurrence in record["study_occurrences"]
            ),
            "evidence_group_ids": chapter_group_ids,
            "terminology_result_ids": [value["id"] for value in chapter_results],
            "terminology_decision_ids": _deduplicate(
                value["decision_id"] for value in chapter_results if value["decision_id"] is not None
            ),
            "recurring_term_group_ids": [
                value for value in chapter_group_ids
                if groups[value]["eligible_for_terminology_review"]
            ],
            "proper_name_group_ids": [value["id"] for value in jmnedict_groups],
            "publisher_ruby": ruby,
            "jmdict_references": {
                "entry_ids": _deduplicate(
                    entry for group in jmdict_groups for entry in group["entry_ids"]
                ),
                "sense_ids": _deduplicate(
                    sense for group in jmdict_groups for sense in group["sense_ids"]
                ),
            },
            "jmnedict_references": {
                "entry_ids": _deduplicate(
                    entry for group in jmnedict_groups for entry in group["entry_ids"]
                ),
                "translation_ids": _deduplicate(
                    translation
                    for group in jmnedict_groups
                    for translation in group["translation_ids"]
                ),
            },
            "effective_terminology": effective,
            "dictionary_provenance": {
                "jmdict": index["dictionary"],
                "jmnedict": index["name_dictionary"],
            },
            "source_hashes": {
                "context_index": _hash(index),
                "context_index_source_input": index["source_input_hash"],
                "evidence_report": _hash(evidence),
                "terminology_report": _hash(terminology),
            },
            "precedence": PRECEDENCE,
        }
        packet["packet_hash"] = _hash(packet)
        packets.append(packet)
    report = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "book_id": index["book_id"],
        "source_schemas": {
            "context_index": index["schema_version"],
            "evidence_report": evidence["schema_version"],
            "terminology_report": terminology["schema_version"],
        },
        "source_hashes": {
            "context_index": _hash(index),
            "evidence_report": _hash(evidence),
            "terminology_report": _hash(terminology),
        },
        "precedence": PRECEDENCE,
        "packets": packets,
    }
    validate_packet_report(report, index, evidence, terminology)
    return report


def validate_packet_report(report, index, evidence, terminology):
    required = {
        "schema_version", "book_id", "source_schemas", "source_hashes",
        "precedence", "packets",
    }
    if set(report) != required or report.get("schema_version") != PACKET_SCHEMA_VERSION:
        raise ChapterSummaryError("Unsupported packet-report schema or fields")
    if report["book_id"] != index["book_id"] or report["precedence"] != PRECEDENCE:
        raise ChapterSummaryError("Packet-report identity mismatch")
    if report["source_hashes"] != {
        "context_index": _hash(index),
        "evidence_report": _hash(evidence),
        "terminology_report": _hash(terminology),
    }:
        raise ChapterSummaryError("Packet-report source hash mismatch")
    chapter_records = {}
    for record in index["records"]:
        chapter_records.setdefault(record["chapter_id"], []).append(record)
    groups = {value["id"]: value for value in evidence["groups"]}
    results = {value["id"]: value for value in terminology["results"]}
    seen = set()
    for number, packet in enumerate(report["packets"], 1):
        packet_fields = {
            "id", "chapter_id", "chapter_order", "source_path",
            "sentence_record_ids", "sentence_count", "character_count",
            "study_item_ids", "study_occurrence_ids", "evidence_group_ids",
            "terminology_result_ids", "terminology_decision_ids",
            "recurring_term_group_ids", "proper_name_group_ids",
            "publisher_ruby", "jmdict_references", "jmnedict_references",
            "effective_terminology", "dictionary_provenance", "source_hashes",
            "precedence", "packet_hash",
        }
        if set(packet) != packet_fields:
            raise ChapterSummaryError("Unsupported packet fields")
        if packet["id"] != f"chapter-context-packet-{number:04d}" or packet["id"] in seen:
            raise ChapterSummaryError("Unstable or duplicate packet ID")
        seen.add(packet["id"])
        records = chapter_records.get(packet["chapter_id"])
        if not records or packet["chapter_order"] != number:
            raise ChapterSummaryError("Unknown or unordered packet chapter")
        if packet["sentence_record_ids"] != [value["id"] for value in records]:
            raise ChapterSummaryError("Unordered or unknown sentence records")
        expected_occurrences = _deduplicate(
            occurrence["occurrence_id"]
            for record in records
            for occurrence in record["study_occurrences"]
        )
        if packet["study_occurrence_ids"] != expected_occurrences:
            raise ChapterSummaryError("Unordered or unknown study occurrences")
        if packet["sentence_count"] != len(records) or packet["character_count"] != sum(
            len(value["text"]) for value in records
        ):
            raise ChapterSummaryError("Invalid packet sentence or character counts")
        if any(value not in groups for value in packet["evidence_group_ids"]):
            raise ChapterSummaryError("Unknown packet evidence group")
        if any(value not in results for value in packet["terminology_result_ids"]):
            raise ChapterSummaryError("Unknown packet terminology result")
        if any(
            ruby.get("source") != "publisher"
            for ruby in packet["publisher_ruby"]
        ):
            raise ChapterSummaryError("Publisher-reading precedence violation")
        if packet["packet_hash"] != _hash(_without(packet, "packet_hash")):
            raise ChapterSummaryError("Invalid packet hash")


def validate_summary_registry(registry, packets):
    if set(registry) != {"schema_version", "registry_id", "book_id", "fixture_notice", "decisions"}:
        raise ChapterSummaryError("Unsupported summary registry fields")
    if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ChapterSummaryError("Unsupported summary registry schema")
    if registry.get("book_id") != packets.get("book_id") or not _valid_text(
        registry.get("fixture_notice"), 160, required=True
    ):
        raise ChapterSummaryError("Invalid summary registry identity")
    packet_by_id = {value["id"]: value for value in packets["packets"]}
    chapter_order = {value["chapter_id"]: value["chapter_order"] for value in packets["packets"]}
    seen, previous = set(), 0
    for number, decision in enumerate(registry.get("decisions", []), 1):
        required = {
            "id", "packet_id", "chapter_id", "status", "summary", "reviewer",
            "review_date", "reviewer_note", "source_packet_hash",
            "evidence_group_ids", "terminology_decision_ids", "provenance",
            "summary_schema_version", "decision_hash",
        }
        if set(decision) != required:
            raise ChapterSummaryError("Unsupported summary decision fields")
        if decision["id"] != f"chapter-summary-decision-{number:04d}" or decision["id"] in seen:
            raise ChapterSummaryError("Unstable or duplicate summary decision ID")
        seen.add(decision["id"])
        packet = packet_by_id.get(decision["packet_id"])
        if packet is None or packet["chapter_id"] != decision["chapter_id"]:
            raise ChapterSummaryError("Unknown chapter or packet")
        order = chapter_order[decision["chapter_id"]]
        if order <= previous:
            raise ChapterSummaryError("Unordered summary decisions")
        previous = order
        if decision["status"] not in STATUSES:
            raise ChapterSummaryError("Invalid summary decision status")
        if decision["status"] == "approved":
            if not _valid_text(decision["summary"], MAX_SUMMARY_LENGTH, required=True):
                raise ChapterSummaryError("Unsafe or missing approved summary")
        elif decision["summary"] is not None:
            raise ChapterSummaryError("Summary supplied for rejected or deferred status")
        if not _valid_text(decision["reviewer"], 100, required=True) or not _valid_date(
            decision["review_date"]
        ) or not _valid_text(decision["reviewer_note"], MAX_NOTE_LENGTH, required=False):
            raise ChapterSummaryError("Missing or unsafe reviewer metadata")
        if (
            decision["source_packet_hash"] != packet["packet_hash"]
            or decision["provenance"] != "user"
            or decision["summary_schema_version"] != REGISTRY_SCHEMA_VERSION
            or any(value not in packet["evidence_group_ids"] for value in decision["evidence_group_ids"])
            or any(value not in packet["terminology_decision_ids"] for value in decision["terminology_decision_ids"])
        ):
            raise ChapterSummaryError("Stale packet or unsupported source reference")
        if decision["decision_hash"] != _hash(_without(decision, "decision_hash")):
            raise ChapterSummaryError("Invalid summary decision hash")


def build_summary_report(packets, registry):
    validate_summary_registry(registry, packets)
    decisions = {value["chapter_id"]: value for value in registry["decisions"]}
    if len(decisions) != len(registry["decisions"]):
        raise ChapterSummaryError("Duplicate summary decision")
    results, diagnostics = [], []
    for number, packet in enumerate(packets["packets"], 1):
        decision = decisions.get(packet["chapter_id"])
        if decision is None:
            status, summary, source, decision_id = "missing-summary-decision", None, None, None
            diagnostics.append({
                "id": f"chapter-summary-diagnostic-{len(diagnostics)+1:04d}",
                "chapter_id": packet["chapter_id"],
                "decision_id": None,
                "reason": "missing-summary-decision",
            })
        elif decision["status"] == "approved":
            status, summary, source, decision_id = (
                "approved-user-summary", decision["summary"], "user", decision["id"]
            )
        elif decision["status"] == "rejected":
            status, summary, source, decision_id = "rejected-by-user", None, None, decision["id"]
        else:
            status, summary, source, decision_id = "deferred-by-user", None, None, decision["id"]
        result = {
            "id": f"chapter-summary-result-{number:04d}",
            "packet_id": packet["id"],
            "chapter_id": packet["chapter_id"],
            "chapter_order": packet["chapter_order"],
            "decision_id": decision_id,
            "decision_status": decision["status"] if decision else None,
            "effective_summary": summary,
            "effective_summary_source": source,
            "supporting_evidence_group_ids": decision["evidence_group_ids"] if decision else [],
            "supporting_terminology_decision_ids": decision["terminology_decision_ids"] if decision else [],
            "sentence_count": packet["sentence_count"],
            "character_count": packet["character_count"],
            "packet_hash": packet["packet_hash"],
            "consistency_status": status,
        }
        result["result_hash"] = _hash(result)
        results.append(result)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "book_id": packets["book_id"],
        "source_schemas": {
            "chapter_packets": packets["schema_version"],
            "summary_registry": registry["schema_version"],
        },
        "source_hashes": {
            "chapter_packets": _hash(packets),
            "summary_registry": _hash(registry),
        },
        "registry_id": registry["registry_id"],
        "precedence": PRECEDENCE,
        "results": results,
        "diagnostics": diagnostics,
    }
    validate_summary_report(report, packets, registry)
    return report


def validate_summary_report(report, packets, registry):
    required = {
        "schema_version", "book_id", "source_schemas", "source_hashes",
        "registry_id", "precedence", "results", "diagnostics",
    }
    if set(report) != required or report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ChapterSummaryError("Unsupported summary report schema or fields")
    if report["source_hashes"] != {
        "chapter_packets": _hash(packets), "summary_registry": _hash(registry)
    } or report["precedence"] != PRECEDENCE:
        raise ChapterSummaryError("Summary report source mismatch")
    packet_by_id = {value["id"]: value for value in packets["packets"]}
    decisions = {value["id"]: value for value in registry["decisions"]}
    seen = set()
    for number, result in enumerate(report["results"], 1):
        result_fields = {
            "id", "packet_id", "chapter_id", "chapter_order", "decision_id",
            "decision_status", "effective_summary", "effective_summary_source",
            "supporting_evidence_group_ids", "supporting_terminology_decision_ids",
            "sentence_count", "character_count", "packet_hash",
            "consistency_status", "result_hash",
        }
        if (
            set(result) != result_fields
            or result["id"] != f"chapter-summary-result-{number:04d}"
            or result["id"] in seen
        ):
            raise ChapterSummaryError("Unstable summary result ID")
        seen.add(result["id"])
        packet = packet_by_id.get(result["packet_id"])
        if packet is None or result["chapter_id"] != packet["chapter_id"]:
            raise ChapterSummaryError("Unknown result packet")
        if result["consistency_status"] not in CONSISTENCY_STATUSES:
            raise ChapterSummaryError("Invalid summary consistency status")
        if result["decision_id"] is None:
            if result["effective_summary"] is not None or result["effective_summary_source"] is not None:
                raise ChapterSummaryError("Summary without explicit decision")
        else:
            decision = decisions.get(result["decision_id"])
            if decision is None or decision["packet_id"] != packet["id"]:
                raise ChapterSummaryError("Unknown result decision")
        if result["result_hash"] != _hash(_without(result, "result_hash")):
            raise ChapterSummaryError("Invalid summary result hash")
    for number, diagnostic in enumerate(report["diagnostics"], 1):
        if (
            diagnostic.get("id") != f"chapter-summary-diagnostic-{number:04d}"
            or diagnostic.get("reason") not in SAFE_REASONS
        ):
            raise ChapterSummaryError("Invalid summary diagnostic")


def retrieve_summaries(packets, report, queries):
    validate_summary_report_source = report.get("source_hashes", {}).get("chapter_packets")
    if validate_summary_report_source != _hash(packets):
        raise ChapterSummaryError("Retrieval source mismatch")
    if queries.get("schema_version") != 1 or set(queries) != {"schema_version", "queries"}:
        raise ChapterSummaryError("Unsupported retrieval-query schema or fields")
    packet_by_chapter = {value["chapter_id"]: value for value in packets["packets"]}
    result_by_chapter = {value["chapter_id"]: value for value in report["results"]}
    item_chapter = {}
    occurrence_chapter = {}
    for packet in packets["packets"]:
        for item_id in packet["study_item_ids"]:
            item_chapter[item_id] = packet["chapter_id"]
    for packet in packets["packets"]:
        for occurrence_id in packet["study_occurrence_ids"]:
            occurrence_chapter[occurrence_id] = packet["chapter_id"]
    results, diagnostics = [], []
    for number, query in enumerate(queries["queries"], 1):
        required = {
            "id", "target_type", "target_id", "include_previous",
            "summary_budget", "character_budget",
        }
        if set(query) != required or query["id"] != f"summary-query-{number:04d}":
            raise ChapterSummaryError("Invalid or unordered summary query")
        if query["target_type"] == "chapter":
            chapter_id = query["target_id"]
        elif query["target_type"] == "item":
            chapter_id = item_chapter.get(query["target_id"])
        elif query["target_type"] == "occurrence":
            chapter_id = occurrence_chapter.get(query["target_id"])
        else:
            raise ChapterSummaryError("Unsupported summary query target")
        packet = packet_by_chapter.get(chapter_id)
        if packet is None:
            raise ChapterSummaryError("Unknown summary query target")
        budget = query["summary_budget"]
        chars = query["character_budget"]
        if not isinstance(budget, int) or budget < 1 or not isinstance(chars, int) or chars < 1:
            raise ChapterSummaryError("Invalid summary retrieval budget")
        candidates = []
        if query["include_previous"] and packet["chapter_order"] > 1:
            previous = packets["packets"][packet["chapter_order"] - 2]
            candidates.append(("previous", result_by_chapter[previous["chapter_id"]]))
        candidates.append(("target", result_by_chapter[chapter_id]))
        selected, used = [], 0
        for reason, value in candidates:
            summary = value["effective_summary"]
            if summary is None:
                continue
            if len(selected) >= budget or used + len(summary) > chars:
                diagnostics.append({
                    "id": f"chapter-summary-diagnostic-{len(diagnostics)+1:04d}",
                    "chapter_id": value["chapter_id"],
                    "decision_id": value["decision_id"],
                    "reason": "budget-exclusion",
                    "query_id": query["id"],
                })
                continue
            selected.append({
                "chapter_id": value["chapter_id"],
                "packet_id": value["packet_id"],
                "summary_result_id": value["id"],
                "decision_id": value["decision_id"],
                "summary": summary,
                "source": value["effective_summary_source"],
                "inclusion_reason": reason,
            })
            used += len(summary)
        result = {
            "id": f"summary-retrieval-result-{number:04d}",
            "query_id": query["id"],
            "target_type": query["target_type"],
            "target_id": query["target_id"],
            "target_chapter_id": chapter_id,
            "include_previous": query["include_previous"],
            "summary_budget": budget,
            "character_budget": chars,
            "summaries": selected,
            "query_hash": _hash(query),
        }
        result["result_hash"] = _hash(result)
        results.append(result)
    value = {
        "schema_version": RETRIEVAL_SCHEMA_VERSION,
        "book_id": packets["book_id"],
        "source_hashes": {
            "chapter_packets": _hash(packets),
            "summary_report": _hash(report),
        },
        "results": results,
        "diagnostics": diagnostics,
    }
    validate_retrieval_report(value, packets, report)
    return value


def validate_retrieval_report(value, packets, report):
    if set(value) != {"schema_version", "book_id", "source_hashes", "results", "diagnostics"}:
        raise ChapterSummaryError("Unsupported retrieval report fields")
    if value.get("schema_version") != RETRIEVAL_SCHEMA_VERSION or value.get("source_hashes") != {
        "chapter_packets": _hash(packets), "summary_report": _hash(report)
    }:
        raise ChapterSummaryError("Invalid retrieval report identity")
    chapter_order = {value["chapter_id"]: value["chapter_order"] for value in packets["packets"]}
    for number, result in enumerate(value["results"], 1):
        result_fields = {
            "id", "query_id", "target_type", "target_id", "target_chapter_id",
            "include_previous", "summary_budget", "character_budget", "summaries",
            "query_hash", "result_hash",
        }
        if set(result) != result_fields or result["id"] != f"summary-retrieval-result-{number:04d}":
            raise ChapterSummaryError("Unstable retrieval result ID")
        orders = [chapter_order[item["chapter_id"]] for item in result["summaries"]]
        if orders != sorted(set(orders)) or any(
            item["source"] != "user" for item in result["summaries"]
        ):
            raise ChapterSummaryError("Invalid summary retrieval ordering or source")
        target_order = chapter_order[result["target_chapter_id"]]
        if any(order > target_order or order < target_order - 1 for order in orders):
            raise ChapterSummaryError("Summary retrieval crossed allowed boundaries")
        if len(result["summaries"]) > result["summary_budget"] or sum(
            len(item["summary"]) for item in result["summaries"]
        ) > result["character_budget"]:
            raise ChapterSummaryError("Summary retrieval budget violation")
        if result["result_hash"] != _hash(_without(result, "result_hash")):
            raise ChapterSummaryError("Invalid retrieval result hash")
    for number, diagnostic in enumerate(value["diagnostics"], 1):
        if (
            set(diagnostic) != {"id", "chapter_id", "decision_id", "reason", "query_id"}
            or diagnostic["id"] != f"chapter-summary-diagnostic-{number:04d}"
            or diagnostic["reason"] != "budget-exclusion"
        ):
            raise ChapterSummaryError("Invalid retrieval diagnostic")


def disabled_summaries(plan):
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": "disabled",
        "results": [],
        "diagnostics": [],
    }, plan


def safe_failure(plan, reason):
    if reason not in SAFE_REASONS:
        reason = "invalid-registry"
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": "fallback",
        "results": [],
        "diagnostics": [{"id": "chapter-summary-diagnostic-0001", "reason": reason}],
    }, plan
