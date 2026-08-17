"""Apply validated Phase 5 meanings to a Phase 4 annotation plan."""

from __future__ import annotations

import copy
import re

from .enrichment import (
    MAX_AMBIGUITY,
    MAX_MEANING,
    UNSAFE_TEXT,
    EnrichmentError,
    validate_request_report,
)

SCHEMA_VERSION = 2
ALLOWED_PROVIDERS = {"openai-compatible", "scripted-local"}
HEX_SHA256 = re.compile(r"[0-9a-f]{64}")
SAFE_REASON = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")


class EnrichedPlanError(EnrichmentError):
    """Raised when plan application inputs or output are inconsistent."""


def _index(values, label, key="id"):
    result = {}
    for value in values:
        identifier = value.get(key)
        if not isinstance(identifier, str) or not identifier or identifier in result:
            raise EnrichedPlanError(f"Duplicate or missing {label} ID")
        result[identifier] = value
    return result


def _validate_plan_request(item, request):
    primary = item["occurrences"][0]
    expected = {
        "item_id": item["id"],
        "item_kind": item["kind"],
        "surface": item["surface"],
        "lemma": item["lemma"],
        "normalized_form": item["normalized_form"],
        "authoritative_reading": item["reading"],
        "reading_source": item["reading_source"],
        "chapter_id": primary["chapter_id"],
        "block_id": primary["block_id"],
        "sentence_id": primary["sentence_id"],
        "occurrence_ids": [x["id"] for x in item["occurrences"]],
        "token_ids": primary["token_ids"],
        "candidate_ids": primary["candidate_ids"],
        "expression_id": primary["expression_id"],
        "name_id": primary["name_id"],
        "publisher_ruby_id": primary["publisher_ruby_id"],
        "dictionary_only_meaning": item["display_meaning"],
    }
    if any(request.get(key) != value for key, value in expected.items()):
        raise EnrichedPlanError("Plan/request item metadata mismatch")
    expected_dictionary = "jmnedict" if item["kind"] == "name" else "jmdict"
    if request["dictionary_kind"] != expected_dictionary:
        raise EnrichedPlanError("Plan/request dictionary kind mismatch")
    provenance = (
        request["dictionary_provenance"]["dataset_id"],
        request["dictionary_provenance"]["dataset_version"],
    )
    if provenance != (
        item["dictionary_dataset_id"],
        item["dictionary_dataset_version"],
    ):
        raise EnrichedPlanError("Plan/request dictionary provenance mismatch")


def _valid_selected_references(request, result):
    entries = {entry["entry_id"]: entry for entry in request["dictionary_entries"]}
    entry = entries.get(result["selected_entry_id"])
    if entry is None:
        return False
    if request["dictionary_kind"] == "jmnedict":
        return (
            result["selected_sense_id"] is None
            and result["selected_translation_id"]
            in {value["id"] for value in entry.get("translations", [])}
        )
    return (
        result["selected_translation_id"] is None
        and result["selected_sense_id"]
        in {value["id"] for value in entry.get("senses", [])}
    )


def _validate_meaning(value, limit, required):
    if required and (not isinstance(value, str) or not value.strip()):
        raise EnrichedPlanError("Missing enriched meaning")
    if value is not None and (
        not isinstance(value, str) or len(value) > limit or UNSAFE_TEXT.search(value)
    ):
        raise EnrichedPlanError("Unsafe or overlong enriched text")


def apply_enrichment(plan, requests, report):
    """Return ``(enriched_plan_or_none, deterministic_diagnostics)``."""
    if plan.get("schema_version") != 1:
        raise EnrichedPlanError("Enrichment requires annotation-plan schema v1")
    validate_request_report(requests)
    if (
        set(report) != {"schema_version", "book_id", "results", "diagnostics"}
        or report.get("schema_version") != 1
        or len({plan.get("book_id"), requests.get("book_id"), report.get("book_id")})
        != 1
    ):
        raise EnrichedPlanError("Invalid enrichment report or book identity")
    if not isinstance(report["results"], list) or not isinstance(
        report["diagnostics"], list
    ):
        raise EnrichedPlanError("Enrichment results and diagnostics must be lists")
    diagnostic_ids = set()
    for diagnostic in report["diagnostics"]:
        if (
            set(diagnostic) != {"id", "request_id", "reason"}
            or not isinstance(diagnostic["id"], str)
            or diagnostic["id"] in diagnostic_ids
            or not isinstance(diagnostic["request_id"], str)
            or not isinstance(diagnostic["reason"], str)
            or not SAFE_REASON.fullmatch(diagnostic["reason"])
        ):
            raise EnrichedPlanError("Unsafe or invalid source diagnostic")
        diagnostic_ids.add(diagnostic["id"])
    items = _index(plan.get("items", []), "study item")
    request_by_item = _index(requests["requests"], "request item", "item_id")
    request_ids = {request["id"] for request in requests["requests"]}
    if any(x["request_id"] not in request_ids for x in report["diagnostics"]):
        raise EnrichedPlanError("Unknown source diagnostic request")
    results = _index(report.get("results", []), "result item", "item_id")
    if set(request_by_item) != set(items):
        raise EnrichedPlanError("Plan/request item set mismatch")
    unknown = set(results) - set(items)
    if unknown:
        raise EnrichedPlanError("Unknown enrichment result item")
    for item_id, item in items.items():
        _validate_plan_request(item, request_by_item[item_id])

    output = copy.deepcopy(plan)
    output["schema_version"] = SCHEMA_VERSION
    output["source_annotation_plan_schema_version"] = 1
    output["enrichments"] = []
    output["enrichment_diagnostics"] = []
    output_items = {item["id"]: item for item in output["items"]}
    for item in plan["items"]:
        request = request_by_item[item["id"]]
        result = results.get(item["id"])
        if result is None:
            reason = "missing-result"
        elif result.get("request_id") != request["id"]:
            raise EnrichedPlanError("Result request/item mismatch")
        elif result.get("source") == "dictionary":
            fallback_allowed = {
                "request_id",
                "item_id",
                "display_meaning",
                "source",
                "cache",
                "selected_entry_id",
                "selected_sense_id",
                "selected_translation_id",
            }
            if (
                set(result) != fallback_allowed
                or result["cache"] not in {"disabled", "error"}
                or result["display_meaning"] != item["display_meaning"]
                or any(
                    result[key] is not None
                    for key in (
                        "selected_entry_id",
                        "selected_sense_id",
                        "selected_translation_id",
                    )
                )
            ):
                raise EnrichedPlanError("Invalid dictionary fallback result")
            reason = f"dictionary-{result['cache']}"
        else:
            accepted_allowed = {
                "request_id",
                "item_id",
                "display_meaning",
                "source",
                "cache",
                "cache_key",
                "selected_entry_id",
                "selected_sense_id",
                "selected_translation_id",
                "ambiguity_note",
                "provider_id",
                "model_id",
            }
            if set(result) != accepted_allowed:
                raise EnrichedPlanError("Unsupported accepted-result fields")
            if (result["source"], result["cache"]) not in {
                ("model", "miss"),
                ("cache", "hit"),
            }:
                raise EnrichedPlanError("Invalid accepted cache provenance")
            if (
                result["provider_id"] not in ALLOWED_PROVIDERS
                or not isinstance(result["model_id"], str)
                or not result["model_id"]
                or not isinstance(result["cache_key"], str)
                or not HEX_SHA256.fullmatch(result["cache_key"])
            ):
                raise EnrichedPlanError("Unsupported provider or cache identity")
            if not _valid_selected_references(request, result):
                raise EnrichedPlanError("Unsupplied dictionary reference")
            if (
                result["selected_entry_id"] not in item["source_entry_ids"]
                or (
                    result["selected_sense_id"] is not None
                    and result["selected_sense_id"] not in item["source_sense_ids"]
                )
                or (
                    result["selected_translation_id"] is not None
                    and result["selected_translation_id"]
                    not in item["source_translation_ids"]
                )
            ):
                raise EnrichedPlanError("Result conflicts with selected plan references")
            _validate_meaning(result["display_meaning"], MAX_MEANING, True)
            _validate_meaning(result["ambiguity_note"], MAX_AMBIGUITY, False)
            number = len(output["enrichments"]) + 1
            enrichment_id = f"plan-enrichment-{number:04d}"
            output["enrichments"].append(
                {
                    "id": enrichment_id,
                    "item_id": item["id"],
                    "request_id": request["id"],
                    "dictionary_only_display_meaning": item["display_meaning"],
                    "display_meaning": result["display_meaning"],
                    "ambiguity_note": result["ambiguity_note"],
                    "selected_entry_id": result["selected_entry_id"],
                    "selected_sense_id": result["selected_sense_id"],
                    "selected_translation_id": result["selected_translation_id"],
                    "prompt_version": request["prompt_version"],
                    "response_schema_version": request["response_schema_version"],
                    "context_hash": request["context_hash"],
                    "provider_id": result["provider_id"],
                    "model_id": result["model_id"],
                    "cache_key": result["cache_key"],
                    "cache_status": result["cache"],
                    "meaning_provenance": (
                        "validated-model" if result["source"] == "model" else "validated-cache"
                    ),
                    "precedence": request["precedence"],
                }
            )
            output_items[item["id"]]["display_meaning"] = result["display_meaning"]
            reason = None
        if reason is not None:
            output["enrichment_diagnostics"].append(
                {
                    "id": f"plan-enrichment-diagnostic-{len(output['enrichment_diagnostics'])+1:04d}",
                    "item_id": item["id"],
                    "request_id": request["id"],
                    "reason": reason,
                }
            )
    if not output["enrichments"]:
        return None, output["enrichment_diagnostics"]
    validate_enriched_plan(output, plan)
    return output, output["enrichment_diagnostics"]


def validate_enriched_plan(value, source_plan):
    required = set(source_plan) | {
        "source_annotation_plan_schema_version",
        "enrichments",
        "enrichment_diagnostics",
    }
    if set(value) != required or value.get("schema_version") != 2:
        raise EnrichedPlanError("Invalid enriched-plan schema")
    source_without_meanings = copy.deepcopy(source_plan)
    value_without_additions = copy.deepcopy(value)
    value_without_additions["schema_version"] = 1
    value_without_additions.pop("source_annotation_plan_schema_version")
    value_without_additions.pop("enrichments")
    value_without_additions.pop("enrichment_diagnostics")
    for source_item, enriched_item in zip(
        source_without_meanings["items"], value_without_additions["items"]
    ):
        enriched_item["display_meaning"] = source_item["display_meaning"]
    if value_without_additions != source_without_meanings:
        raise EnrichedPlanError("Enrichment changed protected annotation-plan data")
    ids = [x["id"] for x in value["enrichments"]]
    if ids != [f"plan-enrichment-{i:04d}" for i in range(1, len(ids) + 1)]:
        raise EnrichedPlanError("Unstable enrichment IDs or ordering")
    diagnostic_ids = [x["id"] for x in value["enrichment_diagnostics"]]
    if diagnostic_ids != [
        f"plan-enrichment-diagnostic-{i:04d}"
        for i in range(1, len(diagnostic_ids) + 1)
    ]:
        raise EnrichedPlanError("Unstable enrichment diagnostic IDs or ordering")
