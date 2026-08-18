"""Editable Phase 6 book-context manifest and bounded request augmentation."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .book_context import PRECEDENCE, _hash, serialize
from .chapter_summaries import _valid_date, _valid_text

SCHEMA_VERSION = 1
AUGMENTATION_SCHEMA_VERSION = 1


class ContextManifestError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContextManifestError("JSON input must be an object")
    return value


def _without(value, key):
    return {name: item for name, item in value.items() if name != key}


def _hash_record(value):
    result = dict(value)
    result["record_hash"] = _hash(value)
    return result


def build_manifest(index, evidence, terminology, packets, summaries):
    if len({index.get("book_id"), evidence.get("book_id"), terminology.get("book_id"),
            packets.get("book_id"), summaries.get("book_id")}) != 1:
        raise ContextManifestError("Source book mismatch")
    expected = {
        "context_index": _hash(index), "evidence_report": _hash(evidence),
        "terminology_report": _hash(terminology), "chapter_packets": _hash(packets),
        "summary_report": _hash(summaries),
    }
    if packets["source_hashes"]["context_index"] != expected["context_index"]:
        raise ContextManifestError("Stale packet source")
    if summaries["source_hashes"]["chapter_packets"] != expected["chapter_packets"]:
        raise ContextManifestError("Stale summary source")
    summary_by_packet = {value["packet_id"]: value for value in summaries["results"]}
    chapters = []
    for packet in packets["packets"]:
        summary = summary_by_packet[packet["id"]]
        chapter = {
            "id": f"book-context-chapter-{packet['chapter_order']:04d}",
            "chapter_id": packet["chapter_id"], "packet_id": packet["id"],
            "chapter_order": packet["chapter_order"], "source_path": packet["source_path"],
            "sentence_record_ids": packet["sentence_record_ids"],
            "sentence_count": packet["sentence_count"],
            "study_item_ids": packet["study_item_ids"],
            "study_occurrence_ids": packet["study_occurrence_ids"],
            "evidence_group_ids": packet["evidence_group_ids"],
            "terminology_result_ids": packet["terminology_result_ids"],
            "publisher_ruby": packet["publisher_ruby"],
            "summary_decision_id": summary["decision_id"],
            "summary_status": summary["decision_status"],
            "effective_summary": summary["effective_summary"],
            "effective_summary_source": summary["effective_summary_source"],
            "packet_hash": packet["packet_hash"],
        }
        chapters.append(_hash_record(chapter))
    terminology_by_group = {value["evidence_group_id"]: value for value in terminology["results"]}
    lexical, names = [], []
    for group in evidence["groups"]:
        result = terminology_by_group[group["id"]]
        record = {
            "id": f"book-context-lexical-{len(lexical)+len(names)+1:04d}",
            "evidence_group_id": group["id"], "evidence_kind": group["evidence_kind"],
            "surface_forms": group["surface_forms"], "lemma": group["lemma"],
            "normalized_form": group["normalized_form"],
            "authoritative_reading": group["authoritative_reading"],
            "reading_source": group["reading_source"], "item_ids": group["item_ids"],
            "occurrences": group["occurrences"], "entry_ids": group["entry_ids"],
            "sense_ids": group["sense_ids"], "translation_ids": group["translation_ids"],
            "chapter_occurrence_counts": group["chapter_occurrence_counts"],
            "book_occurrence_count": group["book_occurrence_count"],
            "decision_id": result["decision_id"], "decision_status": result["decision_status"],
            "effective_term": result["approved_term"],
            "effective_term_source": result["effective_terminology_source"],
            "evidence_hash": group["evidence_hash"], "provenance": group["provenance"],
        }
        target = names if group["evidence_kind"] in {"jmnedict_name", "publisher_ruby_name"} else lexical
        target.append(_hash_record(record))
    terminology_decisions = [
        _hash_record({
            "id": value["decision_id"], "evidence_group_id": value["evidence_group_id"],
            "status": value["decision_status"], "approved_term": value["approved_term"],
            "reviewer": None, "review_date": None, "reviewer_note": None,
            "provenance": "source-report",
        })
        for value in terminology["results"] if value["decision_id"]
    ]
    summary_decisions = [
        _hash_record({
            "id": value["decision_id"], "packet_id": value["packet_id"],
            "chapter_id": value["chapter_id"], "status": value["decision_status"],
            "summary": value["effective_summary"], "reviewer": None, "review_date": None,
            "reviewer_note": None, "provenance": "source-report",
            "evidence_group_ids": value["supporting_evidence_group_ids"],
            "terminology_decision_ids": value["supporting_terminology_decision_ids"],
        })
        for value in summaries["results"] if value["decision_id"]
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION, "manifest_id": "furiganalyse-book-context-v1",
        "book_id": index["book_id"],
        "source_schemas": {
            "context_index": index["schema_version"], "evidence_report": evidence["schema_version"],
            "terminology_report": terminology["schema_version"],
            "chapter_packets": packets["schema_version"], "summary_report": summaries["schema_version"],
        },
        "source_hashes": expected, "precedence": PRECEDENCE,
        "dictionary_provenance": {"jmdict": index["dictionary"], "jmnedict": index["name_dictionary"]},
        "chapters": chapters, "recurring_terms": lexical, "proper_names": names,
        "terminology_decisions": terminology_decisions,
        "summary_decisions": summary_decisions, "diagnostics": [],
    }
    manifest["manifest_hash"] = _hash(manifest)
    return manifest


def validate_edited_manifest(original, edited):
    if original.get("schema_version") != SCHEMA_VERSION or edited.get("schema_version") != SCHEMA_VERSION:
        raise ContextManifestError("Unsupported manifest schema")
    protected = {
        key: value for key, value in original.items()
        if key not in {"terminology_decisions", "summary_decisions", "manifest_hash"}
    }
    edited_protected = {
        key: value for key, value in edited.items()
        if key not in {"terminology_decisions", "summary_decisions", "manifest_hash"}
    }
    if protected != edited_protected:
        raise ContextManifestError("Protected manifest field changed")
    for key, text_key in (("terminology_decisions", "approved_term"), ("summary_decisions", "summary")):
        old = {value["id"]: value for value in original[key]}
        if [value["id"] for value in edited[key]] != list(old):
            raise ContextManifestError("Unknown, duplicate, or unordered decision")
        for value in edited[key]:
            if value["record_hash"] != _hash(_without(value, "record_hash")):
                raise ContextManifestError("Invalid decision hash")
            if value["provenance"] == "user":
                if not _valid_text(value["reviewer"], 100, required=True) or not _valid_date(value["review_date"]):
                    raise ContextManifestError("Missing reviewer or date")
                if not _valid_text(value["reviewer_note"], 240, required=False):
                    raise ContextManifestError("Unsafe reviewer note")
                if value["status"] == "approved":
                    if not _valid_text(value[text_key], 240, required=True):
                        raise ContextManifestError("Unsafe approved text")
                elif value[text_key] is not None:
                    raise ContextManifestError("Text supplied for non-approved decision")
            elif value != old[value["id"]]:
                raise ContextManifestError("Edit is not user provenanced")
    approved_terms = {
        value["evidence_group_id"]: value["approved_term"]
        for value in edited["terminology_decisions"]
        if value["status"] == "approved"
    }
    summaries = {value["packet_id"]: value for value in edited["summary_decisions"]}
    for chapter in edited["chapters"]:
        decision = summaries.get(chapter["packet_id"])
        if not decision or decision["status"] != "approved":
            continue
        for group_id in chapter["evidence_group_ids"]:
            term = approved_terms.get(group_id)
            if term and term not in decision["summary"]:
                raise ContextManifestError("Approved terminology conflicts with summary")
    if edited["manifest_hash"] != _hash(_without(edited, "manifest_hash")):
        raise ContextManifestError("Invalid edited manifest hash")


def rehash_manifest(value):
    result = copy.deepcopy(value)
    for key in ("terminology_decisions", "summary_decisions"):
        for decision in result[key]:
            decision["record_hash"] = _hash(_without(decision, "record_hash"))
    result["manifest_hash"] = _hash(_without(result, "manifest_hash"))
    return result


def export_registries(original, edited, evidence, packets):
    validate_edited_manifest(original, edited)
    groups = {value["id"]: value for value in evidence["groups"]}
    packet_by_id = {value["id"]: value for value in packets["packets"]}
    terminology = {"schema_version": 1, "registry_id": "phase6-exported-terminology-v1",
                   "book_id": edited["book_id"], "decisions": []}
    for number, edit in enumerate(edited["terminology_decisions"], 1):
        group = groups[edit["evidence_group_id"]]
        decision = {
            "id": f"terminology-decision-{number:04d}", "evidence_group_id": group["id"],
            "evidence_kind": group["evidence_kind"], "status": edit["status"],
            "approved_term": edit["approved_term"], "reviewer_note": edit["reviewer_note"],
            "reviewer": edit["reviewer"], "approval_date": edit["review_date"],
            "source_evidence_hash": group["evidence_hash"], "source_item_ids": group["item_ids"],
            "source_entry_ids": group["entry_ids"], "source_sense_ids": group["sense_ids"],
            "source_translation_ids": group["translation_ids"],
            "authoritative_reading": group["authoritative_reading"],
            "reading_source": group["reading_source"], "provenance": "user",
            "registry_schema_version": 1,
        }
        decision["decision_hash"] = _hash(decision)
        terminology["decisions"].append(decision)
    summaries = {"schema_version": 1, "registry_id": "phase6-exported-summaries-v1",
                 "book_id": edited["book_id"],
                 "fixture_notice": "Synthetic edited test fixture; not real user approval.",
                 "decisions": []}
    for number, edit in enumerate(edited["summary_decisions"], 1):
        packet = packet_by_id[edit["packet_id"]]
        decision = {
            "id": f"chapter-summary-decision-{number:04d}", "packet_id": packet["id"],
            "chapter_id": packet["chapter_id"], "status": edit["status"],
            "summary": edit["summary"], "reviewer": edit["reviewer"],
            "review_date": edit["review_date"], "reviewer_note": edit["reviewer_note"],
            "source_packet_hash": packet["packet_hash"],
            "evidence_group_ids": edit["evidence_group_ids"],
            "terminology_decision_ids": edit["terminology_decision_ids"],
            "provenance": "user", "summary_schema_version": 1,
        }
        decision["decision_hash"] = _hash(decision)
        summaries["decisions"].append(decision)
    return terminology, summaries


def build_augmentation(requests, manifest, *, include_previous=False, record_budget=2, character_budget=500):
    if requests.get("book_id") != manifest.get("book_id"):
        raise ContextManifestError("Request/manifest book mismatch")
    terms = manifest["recurring_terms"] + manifest["proper_names"]
    chapter_by_id = {value["chapter_id"]: value for value in manifest["chapters"]}
    terminology_edits = {value["id"]: value for value in manifest["terminology_decisions"]}
    summary_edits = {value["id"]: value for value in manifest["summary_decisions"]}
    results, diagnostics = [], []
    for number, request in enumerate(requests["requests"], 1):
        matches = [value for value in terms if request["item_id"] in value["item_ids"]]
        if len(matches) != 1:
            raise ContextManifestError("Missing or ambiguous item context")
        record = matches[0]
        chapter = chapter_by_id[request["chapter_id"]]
        summaries = []
        candidates = []
        if include_previous and chapter["chapter_order"] > 1:
            candidates.append(("previous", manifest["chapters"][chapter["chapter_order"] - 2]))
        candidates.append(("target", chapter))
        used = 0
        for reason, candidate in candidates:
            summary_edit = summary_edits.get(candidate["summary_decision_id"])
            text = (
                summary_edit["summary"]
                if summary_edit and summary_edit["status"] == "approved"
                else None
            )
            if text is None:
                continue
            if len(summaries) >= record_budget or used + len(text) > character_budget:
                diagnostics.append({"id": f"context-augmentation-diagnostic-{len(diagnostics)+1:04d}",
                                    "request_id": request["id"], "reason": "budget-exclusion"})
                continue
            summaries.append({"chapter_id": candidate["chapter_id"], "summary": text,
                              "source": "user",
                              "decision_id": candidate["summary_decision_id"],
                              "inclusion_reason": reason})
            used += len(text)
        terminology_edit = terminology_edits.get(record["decision_id"])
        effective_term = (
            terminology_edit["approved_term"]
            if terminology_edit and terminology_edit["status"] == "approved"
            else None
        )
        result = {
            "id": f"context-augmentation-{number:04d}", "request_id": request["id"],
            "item_id": request["item_id"], "chapter_id": request["chapter_id"],
            "occurrence_ids": request["occurrence_ids"], "context_record_id": record["id"],
            "evidence_group_id": record["evidence_group_id"],
            "evidence_kind": record["evidence_kind"],
            "authoritative_reading": record["authoritative_reading"],
            "reading_source": record["reading_source"],
            "effective_terminology": effective_term,
            "terminology_source": "user" if effective_term is not None else None,
            "decision_id": record["decision_id"], "summaries": summaries,
            "precedence": manifest["precedence"], "manifest_hash": manifest["manifest_hash"],
        }
        result["result_hash"] = _hash(result)
        results.append(result)
    report = {"schema_version": AUGMENTATION_SCHEMA_VERSION, "book_id": manifest["book_id"],
              "source_hashes": {"requests": _hash(requests), "manifest": _hash(manifest)},
              "include_previous": include_previous, "record_budget": record_budget,
              "character_budget": character_budget, "results": results, "diagnostics": diagnostics}
    report["report_hash"] = _hash(report)
    return report


def disabled_context(requests, plan, reason=None):
    report = {"schema_version": 1, "status": "disabled" if reason is None else "fallback",
              "results": [], "diagnostics": [] if reason is None else [
                  {"id": "context-augmentation-diagnostic-0001", "reason": reason}
              ]}
    return report, requests, plan
