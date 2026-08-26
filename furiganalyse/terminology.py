"""Explicit user terminology decisions and deterministic consistency reporting."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from .book_context import PRECEDENCE, _hash, validate_context_index
from .context_evidence import validate_evidence_report

REGISTRY_SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = 1
MAX_TERM_LENGTH = 80
MAX_NOTE_LENGTH = 240
STATUSES = {"approved", "rejected", "deferred"}
CONSISTENCY_STATUSES = {
    "consistent-user-approved",
    "unapproved-recurring-evidence",
    "single-occurrence-observation",
    "rejected-by-user",
    "deferred-by-user",
}
SAFE_TEXT = re.compile(
    r"[<>]|https?://|www\.|(?:^|\s)(?:/|~[/\\])|[A-Za-z]:\\|"
    r"(?:api[_-]?key|password|secret|token)\s*[:=]|"
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]",
    re.IGNORECASE,
)
SAFE_REASONS = {
    "missing-recurring-decision",
    "stale-evidence-hash",
    "unknown-evidence-group",
    "duplicate-decision",
    "invalid-decision-status",
    "unsafe-or-missing-approved-term",
    "term-for-non-approved-status",
    "jmdict-jmnedict-mismatch",
    "publisher-reading-mismatch",
    "source-reference-mismatch",
    "approved-term-differs-current-meaning",
    "unused-decision",
    "unsupported-schema-or-fields",
    "invalid-registry",
    "corrupt-registry",
    "disabled",
}


class TerminologyError(ValueError):
    """Raised when a terminology decision cannot be trusted."""


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TerminologyError("Input JSON must be an object")
    return value


def decision_payload(decision: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in decision.items() if key != "decision_hash"}


def with_decision_hash(decision: dict[str, Any]) -> dict[str, Any]:
    value = dict(decision)
    value["decision_hash"] = _hash(decision_payload(value))
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


def validate_registry(registry: dict[str, Any], evidence: dict[str, Any]):
    if set(registry) != {
        "schema_version",
        "registry_id",
        "book_id",
        "decisions",
    } or registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise TerminologyError("Unsupported registry schema or fields")
    if (
        not isinstance(registry.get("registry_id"), str)
        or not registry["registry_id"]
        or registry.get("book_id") != evidence.get("book_id")
        or not isinstance(registry.get("decisions"), list)
    ):
        raise TerminologyError("Invalid registry identity")
    groups = {group["id"]: group for group in evidence["groups"]}
    seen = set()
    previous_group_number = 0
    for number, decision in enumerate(registry["decisions"], 1):
        if set(decision) != {
            "id",
            "evidence_group_id",
            "evidence_kind",
            "status",
            "approved_term",
            "reviewer_note",
            "reviewer",
            "approval_date",
            "source_evidence_hash",
            "source_item_ids",
            "source_entry_ids",
            "source_sense_ids",
            "source_translation_ids",
            "authoritative_reading",
            "reading_source",
            "provenance",
            "registry_schema_version",
            "decision_hash",
        }:
            raise TerminologyError("Unsupported decision fields")
        if decision["id"] != f"terminology-decision-{number:04d}" or decision["id"] in seen:
            raise TerminologyError("Unstable or duplicate decision ID")
        seen.add(decision["id"])
        group = groups.get(decision["evidence_group_id"])
        if group is None:
            raise TerminologyError("Unknown evidence group")
        group_number = int(group["id"].rsplit("-", 1)[1])
        if group_number <= previous_group_number:
            raise TerminologyError("Unordered terminology decisions")
        previous_group_number = group_number
        if decision["status"] not in STATUSES:
            raise TerminologyError("Invalid decision status")
        if decision["status"] == "approved":
            if not _valid_text(decision["approved_term"], MAX_TERM_LENGTH, required=True):
                raise TerminologyError("Unsafe or missing approved term")
        elif decision["approved_term"] is not None:
            raise TerminologyError("Term supplied for rejected or deferred decision")
        if not _valid_text(decision["reviewer"], 100, required=True) or not _valid_date(
            decision["approval_date"]
        ):
            raise TerminologyError("Missing reviewer or approval date")
        if not _valid_text(decision["reviewer_note"], MAX_NOTE_LENGTH, required=False):
            raise TerminologyError("Unsafe reviewer note")
        expected = {
            "evidence_kind": group["evidence_kind"],
            "source_evidence_hash": group["evidence_hash"],
            "source_item_ids": group["item_ids"],
            "source_entry_ids": group["entry_ids"],
            "source_sense_ids": group["sense_ids"],
            "source_translation_ids": group["translation_ids"],
            "authoritative_reading": group["authoritative_reading"],
            "reading_source": group["reading_source"],
            "provenance": "user",
            "registry_schema_version": REGISTRY_SCHEMA_VERSION,
        }
        if any(decision.get(key) != value for key, value in expected.items()):
            raise TerminologyError("Stale evidence or source-reference mismatch")
        is_name = group["evidence_kind"] in {"jmnedict_name", "publisher_ruby_name"}
        if is_name != bool(decision["source_translation_ids"]):
            raise TerminologyError("JMdict/JMnedict decision mismatch")
        if group["evidence_kind"].startswith("publisher_ruby") and decision[
            "reading_source"
        ] != "publisher":
            raise TerminologyError("Publisher-reading mismatch")
        if decision["decision_hash"] != _hash(decision_payload(decision)):
            raise TerminologyError("Invalid decision hash")


def _validate_sources(
    evidence: dict[str, Any],
    index: dict[str, Any],
    plan: dict[str, Any],
    registry: dict[str, Any],
):
    validate_evidence_report(evidence)
    validate_context_index(index)
    if (
        plan.get("schema_version") != 2
        or plan.get("source_annotation_plan_schema_version") != 1
    ):
        raise TerminologyError("Enriched annotation-plan schema must be 2")
    if len({evidence.get("book_id"), index.get("book_id"), plan.get("book_id")}) != 1:
        raise TerminologyError("Source book identity mismatch")
    if evidence["source_hashes"]["context_index"] != _hash(index):
        raise TerminologyError("Evidence/context-index hash mismatch")
    if evidence["source_hashes"]["enriched_annotation_plan"] != _hash(plan):
        raise TerminologyError("Evidence/annotation-plan hash mismatch")
    validate_registry(registry, evidence)


def _result_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "result_hash"}


def build_consistency_report(
    evidence: dict[str, Any],
    index: dict[str, Any],
    plan: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    """Apply only exact explicit user decisions to an evidence consistency report."""
    _validate_sources(evidence, index, plan, registry)
    decisions = {value["evidence_group_id"]: value for value in registry["decisions"]}
    if len(decisions) != len(registry["decisions"]):
        raise TerminologyError("Duplicate decision for evidence group")
    items = {item["id"]: item for item in plan["items"]}
    diagnostics = []
    results = []
    for number, group in enumerate(evidence["groups"], 1):
        decision = decisions.get(group["id"])
        if decision is None:
            status = (
                "unapproved-recurring-evidence"
                if group["eligible_for_terminology_review"]
                else "single-occurrence-observation"
            )
            approved_term = None
            term_source = None
            decision_id = None
            decision_status = None
            if status == "unapproved-recurring-evidence":
                diagnostics.append(
                    {
                        "id": f"terminology-diagnostic-{len(diagnostics)+1:04d}",
                        "group_id": group["id"],
                        "decision_id": None,
                        "reason": "missing-recurring-decision",
                    }
                )
        elif decision["status"] == "approved":
            status = "consistent-user-approved"
            approved_term = decision["approved_term"]
            term_source = "user"
            decision_id = decision["id"]
            decision_status = "approved"
            current_meanings = {
                items[item_id]["display_meaning"] for item_id in group["item_ids"]
            }
            if current_meanings != {approved_term}:
                diagnostics.append(
                    {
                        "id": f"terminology-diagnostic-{len(diagnostics)+1:04d}",
                        "group_id": group["id"],
                        "decision_id": decision["id"],
                        "reason": "approved-term-differs-current-meaning",
                    }
                )
        else:
            status = (
                "rejected-by-user"
                if decision["status"] == "rejected"
                else "deferred-by-user"
            )
            approved_term = None
            term_source = None
            decision_id = decision["id"]
            decision_status = decision["status"]
        result = {
            "id": f"terminology-result-{number:04d}",
            "evidence_group_id": group["id"],
            "decision_id": decision_id,
            "decision_status": decision_status,
            "evidence_kind": group["evidence_kind"],
            "surface_forms": group["surface_forms"],
            "lemma": group["lemma"],
            "normalized_form": group["normalized_form"],
            "authoritative_reading": group["authoritative_reading"],
            "reading_source": group["reading_source"],
            "item_ids": group["item_ids"],
            "entry_ids": group["entry_ids"],
            "sense_ids": group["sense_ids"],
            "translation_ids": group["translation_ids"],
            "occurrences": group["occurrences"],
            "first_location": group["first_location"],
            "last_location": group["last_location"],
            "chapter_occurrence_counts": group["chapter_occurrence_counts"],
            "book_occurrence_count": group["book_occurrence_count"],
            "evidence_hash": group["evidence_hash"],
            "evidence_provenance": group["provenance"],
            "approved_term": approved_term,
            "effective_terminology_source": term_source,
            "consistency_status": status,
        }
        result["result_hash"] = _hash(_result_payload(result))
        results.append(result)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "book_id": evidence["book_id"],
        "source_schemas": {
            "evidence_report": evidence["schema_version"],
            "context_index": index["schema_version"],
            "enriched_annotation_plan": plan["schema_version"],
            "terminology_registry": registry["schema_version"],
        },
        "source_hashes": {
            "evidence_report": _hash(evidence),
            "context_index": _hash(index),
            "enriched_annotation_plan": _hash(plan),
            "terminology_registry": _hash(registry),
        },
        "registry_id": registry["registry_id"],
        "precedence": PRECEDENCE,
        "results": results,
        "diagnostics": diagnostics,
    }
    validate_consistency_report(report, evidence, registry)
    return report


def validate_consistency_report(
    report: dict[str, Any], evidence: dict[str, Any], registry: dict[str, Any]
):
    if set(report) != {
        "schema_version",
        "book_id",
        "source_schemas",
        "source_hashes",
        "registry_id",
        "precedence",
        "results",
        "diagnostics",
    } or report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise TerminologyError("Unsupported consistency-report schema or fields")
    if report.get("source_schemas") != {
        "evidence_report": 1,
        "context_index": 1,
        "enriched_annotation_plan": 2,
        "terminology_registry": 1,
    } or any(
        not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in report.get("source_hashes", {}).values()
    ):
        raise TerminologyError("Invalid consistency-report source schemas or hashes")
    if (
        report["book_id"] != evidence["book_id"]
        or report["registry_id"] != registry["registry_id"]
        or report["precedence"] != PRECEDENCE
        or report["source_hashes"]["evidence_report"] != _hash(evidence)
        or report["source_hashes"]["terminology_registry"] != _hash(registry)
    ):
        raise TerminologyError("Consistency-report source mismatch")
    groups = {group["id"]: group for group in evidence["groups"]}
    decisions = {value["id"]: value for value in registry["decisions"]}
    occurrence_ids = set()
    for number, result in enumerate(report["results"], 1):
        required = {
            "id",
            "evidence_group_id",
            "decision_id",
            "decision_status",
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
            "occurrences",
            "first_location",
            "last_location",
            "chapter_occurrence_counts",
            "book_occurrence_count",
            "evidence_hash",
            "evidence_provenance",
            "approved_term",
            "effective_terminology_source",
            "consistency_status",
            "result_hash",
        }
        if set(result) != required or result["id"] != f"terminology-result-{number:04d}":
            raise TerminologyError("Unstable result ID or unsupported fields")
        group = groups.get(result["evidence_group_id"])
        if group is None:
            raise TerminologyError("Unknown result evidence group")
        protected = {
            "evidence_kind": "evidence_kind",
            "surface_forms": "surface_forms",
            "lemma": "lemma",
            "normalized_form": "normalized_form",
            "authoritative_reading": "authoritative_reading",
            "reading_source": "reading_source",
            "item_ids": "item_ids",
            "entry_ids": "entry_ids",
            "sense_ids": "sense_ids",
            "translation_ids": "translation_ids",
            "occurrences": "occurrences",
            "first_location": "first_location",
            "last_location": "last_location",
            "chapter_occurrence_counts": "chapter_occurrence_counts",
            "book_occurrence_count": "book_occurrence_count",
            "evidence_hash": "evidence_hash",
            "evidence_provenance": "provenance",
        }
        if any(result[key] != group[value] for key, value in protected.items()):
            raise TerminologyError("Consistency result changed evidence")
        for occurrence in result["occurrences"]:
            if occurrence["id"] in occurrence_ids:
                raise TerminologyError("Duplicate result occurrence")
            occurrence_ids.add(occurrence["id"])
        if result["consistency_status"] not in CONSISTENCY_STATUSES:
            raise TerminologyError("Invalid consistency status")
        if result["decision_id"] is None:
            if (
                result["approved_term"] is not None
                or result["effective_terminology_source"] is not None
            ):
                raise TerminologyError("Terminology without explicit decision")
        else:
            decision = decisions.get(result["decision_id"])
            if decision is None or decision["evidence_group_id"] != group["id"]:
                raise TerminologyError("Unknown or mismatched result decision")
            if decision["status"] == "approved":
                if (
                    result["approved_term"] != decision["approved_term"]
                    or result["effective_terminology_source"] != "user"
                    or result["consistency_status"] != "consistent-user-approved"
                ):
                    raise TerminologyError("Approved terminology application mismatch")
            elif result["approved_term"] is not None:
                raise TerminologyError("Non-approved result contains terminology")
        if result["result_hash"] != _hash(_result_payload(result)):
            raise TerminologyError("Invalid consistency result hash")
    diagnostic_ids = set()
    result_groups = {value["evidence_group_id"] for value in report["results"]}
    for number, diagnostic in enumerate(report["diagnostics"], 1):
        if (
            set(diagnostic) != {"id", "group_id", "decision_id", "reason"}
            or diagnostic["id"] != f"terminology-diagnostic-{number:04d}"
            or diagnostic["id"] in diagnostic_ids
            or diagnostic["group_id"] not in result_groups
            or diagnostic["reason"] not in SAFE_REASONS
            or (
                diagnostic["decision_id"] is not None
                and diagnostic["decision_id"] not in decisions
            )
        ):
            raise TerminologyError("Invalid terminology diagnostic")
        diagnostic_ids.add(diagnostic["id"])


def disabled_terminology(plan: dict[str, Any]):
    return (
        {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "disabled",
            "results": [],
            "diagnostics": [],
        },
        plan,
    )


def safe_failure(plan: dict[str, Any], reason: str):
    if reason not in SAFE_REASONS:
        reason = "invalid-registry"
    return (
        {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "fallback",
            "results": [],
            "diagnostics": [
                {"id": "terminology-diagnostic-0001", "reason": reason}
            ],
        },
        plan,
    )
