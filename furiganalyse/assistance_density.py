"""Deterministic per-occurrence assistance-density planning."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
POLICY_SCHEMA_VERSION = 1
DIMENSIONS = ("reading", "meaning", "grammar")
PRECEDENCE = [
    "publisher",
    "explicit_user_override",
    "input_assistance_state",
    "chapter_density_policy",
    "exposure_evidence",
    "canonical_source_order",
]
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
ALLOWED_DECISIONS = {
    "selected-within-budget",
    "suppressed-input-state",
    "suppressed-density-budget",
    "selected-explicit-override",
    "suppressed-explicit-override",
    "selected-explicit-override-over-budget",
    "publisher-ruby-preserved",
    "publisher-adjacent-protected",
    "grammar-reference-only",
    "grammar-partial-overlap-rejected",
    "not-applicable",
}


class AssistanceDensityError(ValueError):
    """Raised when density-planning inputs cannot be trusted."""


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def add_hash(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result["hash"] = stable_hash(result)
    return result


def _without_hash(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "hash"}


def _check_hash(value: dict[str, Any], label: str) -> None:
    if value.get("hash") != stable_hash(_without_hash(value)):
        raise AssistanceDensityError(f"Invalid {label} hash")


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssistanceDensityError("Expected a JSON object")
    return value


def serialize_density_report(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise AssistanceDensityError(f"Invalid {label} ID")
    return value


def _exact_fields(value: dict[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise AssistanceDensityError(f"Unsupported {label} fields")


def validate_density_policy_dataset(dataset: dict[str, Any]) -> None:
    _exact_fields(
        dataset,
        {
            "schema_version", "dataset_id", "dataset_version", "fixture_notice",
            "source_provenance", "policies", "hash",
        },
        "density-policy dataset",
    )
    if dataset["schema_version"] != POLICY_SCHEMA_VERSION:
        raise AssistanceDensityError("Unsupported density-policy schema")
    _safe_id(dataset["dataset_id"], "density-policy dataset")
    policies = dataset["policies"]
    if not isinstance(policies, list) or [value.get("preset_id") for value in policies] != [
        "phase8-preset-n5", "phase8-preset-n4", "phase8-preset-n3"
    ]:
        raise AssistanceDensityError("Unordered density policies")
    policy_ids: set[str] = set()
    previous_targets = None
    for policy in policies:
        _exact_fields(
            policy,
            {
                "id", "schema_version", "preset_id", "targets_per_1000",
                "minimum_per_chapter", "maximum_per_chapter", "rounding_policy",
                "source_order_tie_breaking", "publisher_ruby_counting_policy",
                "explicit_override_handling", "repeated_occurrence_handling",
                "rationale_codes", "source_provenance", "hash",
            },
            "density policy",
        )
        policy_id = _safe_id(policy["id"], "density policy")
        if policy_id in policy_ids:
            raise AssistanceDensityError("Duplicate density policy")
        policy_ids.add(policy_id)
        if policy["schema_version"] != POLICY_SCHEMA_VERSION:
            raise AssistanceDensityError("Unsupported density-policy schema")
        for field in ("targets_per_1000", "minimum_per_chapter", "maximum_per_chapter"):
            values = policy[field]
            if set(values) != set(DIMENSIONS) or any(
                not isinstance(values[dimension], int) or values[dimension] < 0
                for dimension in DIMENSIONS
            ):
                raise AssistanceDensityError("Invalid density target")
        if any(
            policy["minimum_per_chapter"][dimension]
            > policy["maximum_per_chapter"][dimension]
            for dimension in DIMENSIONS
        ):
            raise AssistanceDensityError("Invalid minimum or maximum")
        if policy["rounding_policy"] != "ceiling-integer":
            raise AssistanceDensityError("Invalid density rounding")
        if policy["source_order_tie_breaking"] != "canonical-source-order":
            raise AssistanceDensityError("Invalid source ordering")
        current_targets = tuple(policy["targets_per_1000"][value] for value in DIMENSIONS)
        if previous_targets is not None and any(
            current > previous for current, previous in zip(current_targets, previous_targets)
        ):
            raise AssistanceDensityError("Density policies are not monotonic")
        previous_targets = current_targets
        if not isinstance(policy["rationale_codes"], list) or any(
            not isinstance(value, str) or not SAFE_ID.fullmatch(value)
            for value in policy["rationale_codes"]
        ):
            raise AssistanceDensityError("Invalid density rationale")
        _check_hash(policy, "density policy")
    _check_hash(dataset, "density-policy dataset")


def _validate_inputs(
    book: dict[str, Any],
    annotation_plan: dict[str, Any],
    grammar_plan: dict[str, Any] | None,
    assistance: dict[str, Any],
) -> None:
    if book.get("schema_version") != 2:
        raise AssistanceDensityError("Unsupported canonical schema")
    if annotation_plan.get("schema_version") != 2:
        raise AssistanceDensityError("Unsupported annotation-plan schema")
    if grammar_plan is not None and grammar_plan.get("schema_version") != 1:
        raise AssistanceDensityError("Unsupported grammar-plan schema")
    if assistance.get("schema_version") != 1 or assistance.get("diagnostics"):
        raise AssistanceDensityError("Unsupported assistance-report schema")
    book_id = book.get("book_id")
    if not book_id or any(
        source.get("book_id") != book_id
        for source in (annotation_plan, assistance)
    ) or (grammar_plan is not None and grammar_plan.get("book_id") != book_id):
        raise AssistanceDensityError("Source book mismatch")
    if assistance.get("source_hashes", {}).get("annotation_plan") != stable_hash(annotation_plan):
        raise AssistanceDensityError("Source-hash mismatch")
    expected_grammar_hash = stable_hash(grammar_plan) if grammar_plan is not None else "none"
    if assistance.get("source_hashes", {}).get("grammar_plan") != expected_grammar_hash:
        raise AssistanceDensityError("Source-hash mismatch")
    _check_hash(assistance, "assistance report")
    for result in assistance.get("results", []):
        _check_hash(result, "assistance result")


def _canonical_maps(book: dict[str, Any]) -> tuple[
    dict[str, tuple[int, int, int]], dict[str, int], set[str],
    dict[str, str], dict[str, int]
]:
    locations: dict[str, tuple[int, int, int]] = {}
    character_counts: dict[str, int] = {}
    ruby_ids: set[str] = set()
    sentence_texts: dict[str, str] = {}
    sentence_block_starts: dict[str, int] = {}
    for chapter_index, chapter in enumerate(book.get("chapters", [])):
        chapter_id = _safe_id(chapter.get("id"), "chapter")
        count = 0
        for block_index, block in enumerate(chapter.get("blocks", [])):
            block_id = _safe_id(block.get("id"), "block")
            for ruby in block.get("publisher_ruby", []):
                ruby_ids.add(_safe_id(ruby.get("id"), "publisher ruby"))
            for sentence_index, sentence in enumerate(block.get("sentences", [])):
                sentence_id = _safe_id(sentence.get("id"), "sentence")
                text = sentence.get("text")
                if not isinstance(text, str):
                    raise AssistanceDensityError("Invalid character count")
                count += len(text)
                locations[sentence_id] = (chapter_index, block_index, sentence_index)
                sentence_texts[sentence_id] = text
                sentence_block_starts[sentence_id] = sentence.get("start")
                if sentence_id.rsplit("-s-", 1)[0] != block_id:
                    raise AssistanceDensityError("Unknown sentence reference")
        character_counts[chapter_id] = count
    if not locations or any(value < 0 for value in character_counts.values()):
        raise AssistanceDensityError("Invalid character count")
    return locations, character_counts, ruby_ids, sentence_texts, sentence_block_starts


def _source_occurrences(
    annotation_plan: dict[str, Any], grammar_plan: dict[str, Any] | None
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    occurrences: dict[str, dict[str, Any]] = {}
    item_kinds: dict[str, str] = {}
    for item in annotation_plan.get("items", []):
        item_id = _safe_id(item.get("id"), "study item")
        item_kinds[item_id] = item.get("kind")
        for occurrence in item.get("occurrences", []):
            occurrence_id = _safe_id(occurrence.get("id"), "study occurrence")
            if occurrence_id in occurrences:
                raise AssistanceDensityError("Duplicate occurrence")
            occurrences[occurrence_id] = {
                **occurrence, "source_item_id": item_id, "surface": item.get("surface")
            }
    if grammar_plan is not None:
        grammar_items = {value["id"]: value for value in grammar_plan.get("items", [])}
        occurrence_to_item = {
            occurrence_id: item_id
            for item_id, item in grammar_items.items()
            for occurrence_id in item.get("occurrence_ids", [])
        }
        for item_id in grammar_items:
            item_kinds[item_id] = "grammar"
        for occurrence in grammar_plan.get("occurrences", []):
            occurrence_id = _safe_id(occurrence.get("id"), "grammar occurrence")
            if occurrence_id in occurrences or occurrence_id not in occurrence_to_item:
                raise AssistanceDensityError("Duplicate or unknown occurrence")
            if occurrence.get("link_disposition") not in {
                "grammar-link", "separate-nonoverlapping-links",
                "grammar-note-reference-only", "rejected-ambiguous-overlap",
                "publisher-ruby-preserved", "vocabulary-link",
            }:
                raise AssistanceDensityError("Grammar-disposition conflict")
            occurrences[occurrence_id] = {
                **occurrence, "source_item_id": occurrence_to_item[occurrence_id]
            }
    return occurrences, item_kinds


def _budget(character_count: int, policy: dict[str, Any], dimension: str) -> dict[str, Any]:
    numerator = character_count * policy["targets_per_1000"][dimension]
    denominator = 1000
    rounded = (numerator + denominator - 1) // denominator
    final = max(policy["minimum_per_chapter"][dimension], rounded)
    final = min(policy["maximum_per_chapter"][dimension], final)
    return {
        "target_numerator": numerator,
        "target_denominator": denominator,
        "rounding_policy": policy["rounding_policy"],
        "minimum": policy["minimum_per_chapter"][dimension],
        "maximum": policy["maximum_per_chapter"][dimension],
        "final_budget": final,
    }


def _diagnostic(number: int, reason: str, source_id: str, **extra: Any) -> dict[str, Any]:
    return add_hash({
        "id": f"density-diagnostic-{number:04d}",
        "reason": reason,
        "source_id": source_id,
        "chapter_id": extra.get("chapter_id"),
        "dimension": extra.get("dimension"),
    })


def _empty_report(book_id: str | None, reason: str) -> dict[str, Any]:
    configuration = add_hash({"enabled": False, "policy_id": None})
    value = {
        "schema_version": SCHEMA_VERSION,
        "report_id": "per-occurrence-assistance-plan-v1",
        "book_id": book_id,
        "source_schema_versions": {
            "canonical_book": 2, "annotation_plan": 2,
            "grammar_plan": 1, "assistance_report": 1,
            "density_policy": POLICY_SCHEMA_VERSION,
        },
        "source_hashes": {},
        "policy": None,
        "precedence": PRECEDENCE,
        "configuration": configuration,
        "occurrence_plans": [],
        "chapter_summaries": [],
        "diagnostics": [_diagnostic(1, reason, "density-planning")],
    }
    value["hash"] = stable_hash(value)
    return value


def build_density_report(
    book: dict[str, Any],
    annotation_plan: dict[str, Any],
    grammar_plan: dict[str, Any] | None,
    assistance: dict[str, Any] | None,
    policy_dataset: dict[str, Any] | None,
    *,
    policy_id: str | None = None,
    enabled: bool = False,
) -> dict[str, Any]:
    if not enabled:
        return _empty_report(book.get("book_id"), "disabled")
    if assistance is None or policy_dataset is None:
        raise AssistanceDensityError("Missing density input")
    _validate_inputs(book, annotation_plan, grammar_plan, assistance)
    validate_density_policy_dataset(policy_dataset)
    policies = {value["id"]: value for value in policy_dataset["policies"]}
    selected_policy_id = policy_id or f"phase8-density-{assistance['results'][0]['preset_id'].split('-')[-1]}"
    if selected_policy_id not in policies:
        raise AssistanceDensityError("Unknown density policy")
    policy = policies[selected_policy_id]
    preset_ids = {value.get("preset_id") for value in assistance["results"]}
    preset_ids.discard(None)
    if preset_ids and preset_ids != {policy["preset_id"]}:
        raise AssistanceDensityError("Preset/policy mismatch")

    (
        locations, character_counts, ruby_ids, sentence_texts,
        sentence_block_starts,
    ) = _canonical_maps(book)
    source_occurrences, item_kinds = _source_occurrences(annotation_plan, grammar_plan)
    results = {value["source_item_id"]: value for value in assistance["results"]}
    if len(results) != len(assistance["results"]):
        raise AssistanceDensityError("Duplicate assistance result")
    claimed_occurrences = [
        occurrence_id
        for result in assistance["results"]
        for occurrence_id in result["occurrence_ids"]
    ]
    if len(claimed_occurrences) != len(set(claimed_occurrences)):
        raise AssistanceDensityError("Duplicate occurrence")
    if set(claimed_occurrences) != set(source_occurrences):
        raise AssistanceDensityError("Unknown occurrence")

    ordered_occurrences = sorted(
        source_occurrences.values(),
        key=lambda value: (*locations.get(value.get("sentence_id"), (999, 999, 999)), value.get("sentence_start", 0), value["id"]),
    )
    if any(value.get("sentence_id") not in locations for value in ordered_occurrences):
        raise AssistanceDensityError("Unknown occurrence")
    if any(value.get("chapter_id") != value.get("sentence_id", "").split("-b-")[0] for value in ordered_occurrences):
        raise AssistanceDensityError("Cross-chapter occurrence")
    for occurrence in ordered_occurrences:
        start = occurrence.get("sentence_start")
        end = occurrence.get("sentence_end")
        text = sentence_texts[occurrence["sentence_id"]]
        if (
            not isinstance(start, int) or not isinstance(end, int)
            or start < 0 or end <= start or end > len(text)
            or text[start:end] != occurrence.get("surface")
            or not isinstance(sentence_block_starts[occurrence["sentence_id"]], int)
            or occurrence.get("block_start")
            != sentence_block_starts[occurrence["sentence_id"]] + start
            or occurrence.get("block_end")
            != sentence_block_starts[occurrence["sentence_id"]] + end
        ):
            raise AssistanceDensityError("Invalid occurrence offset")

    plans: list[dict[str, Any]] = []
    for number, occurrence in enumerate(ordered_occurrences, 1):
        item_id = occurrence["source_item_id"]
        result = results.get(item_id)
        if result is None or result["item_kind"] != item_kinds[item_id]:
            raise AssistanceDensityError("Unknown occurrence")
        is_grammar = result["item_kind"] == "grammar"
        publisher_ruby_id = occurrence.get("publisher_ruby_id")
        if publisher_ruby_id is not None and publisher_ruby_id not in ruby_ids:
            raise AssistanceDensityError("Unknown publisher ruby")
        input_states = {
            "reading": result["reading_assistance"],
            "meaning": result["meaning_assistance"],
            "grammar": result["grammar_assistance"],
        }
        planned_states = {dimension: "not-applicable" for dimension in DIMENSIONS}
        decisions = {dimension: "not-applicable" for dimension in DIMENSIONS}
        sources = {dimension: None for dimension in DIMENSIONS}
        ranks = {dimension: None for dimension in DIMENSIONS}
        budgets = {dimension: None for dimension in DIMENSIONS}
        applicable = ("grammar",) if is_grammar else ("reading", "meaning")
        for dimension in applicable:
            sources[dimension] = result["effective_sources"][dimension]
            state = input_states[dimension]
            planned_states[dimension] = {
                "reading": "present-reading",
                "meaning": "present-meaning",
                "grammar": "present-grammar",
            }[dimension]
            if state.startswith("hide-"):
                planned_states[dimension] = f"suppress-{dimension}"
                decisions[dimension] = (
                    "suppressed-explicit-override"
                    if sources[dimension] == "explicit_user_override"
                    else "suppressed-input-state"
                )
        if publisher_ruby_id is not None:
            planned_states["reading"] = "publisher-ruby-preserved"
            decisions["reading"] = "publisher-ruby-preserved"
            sources["reading"] = "publisher"
        if is_grammar:
            disposition = occurrence.get("link_disposition")
            if disposition == "publisher-ruby-preserved":
                planned_states["grammar"] = "publisher-ruby-preserved"
                decisions["grammar"] = "publisher-adjacent-protected"
                sources["grammar"] = "publisher"
            elif disposition == "rejected-ambiguous-overlap":
                planned_states["grammar"] = "suppress-grammar"
                decisions["grammar"] = "grammar-partial-overlap-rejected"
            elif disposition == "grammar-note-reference-only" and decisions["grammar"] == "not-applicable":
                decisions["grammar"] = "grammar-reference-only"
        plans.append({
            "id": f"occurrence-assistance-plan-{number:04d}",
            "source_result_id": result["id"],
            "source_item_id": item_id,
            "source_occurrence_id": occurrence["id"],
            "item_kind": result["item_kind"],
            "chapter_id": occurrence["chapter_id"],
            "block_id": occurrence["block_id"],
            "sentence_id": occurrence["sentence_id"],
            "sentence_record_id": occurrence.get("sentence_record_id", occurrence["sentence_id"]),
            "sentence_start": occurrence.get("sentence_start"),
            "sentence_end": occurrence.get("sentence_end"),
            "block_start": occurrence.get("block_start"),
            "block_end": occurrence.get("block_end"),
            "canonical_source_order": number,
            "token_ids": occurrence.get("token_ids", occurrence.get("component_token_ids", [])),
            "source_anchor_id": occurrence.get("source_anchor_id"),
            "publisher_ruby_id": publisher_ruby_id,
            "publisher_ruby_interaction": occurrence.get("publisher_ruby_interaction", "none"),
            "grammar_link_disposition": occurrence.get("link_disposition") if is_grammar else None,
            "grammar_overlap_disposition": occurrence.get("overlap_disposition") if is_grammar else None,
            "input_assistance": input_states,
            "planned_assistance": planned_states,
            "effective_sources": sources,
            "density_decisions": decisions,
            "density_ranks": ranks,
            "chapter_budget_ids": budgets,
            "override_ids": result["override_ids"],
            "exposure_ids": result["exposure_ids"],
            "rationale_codes": list(result["rationale_codes"]),
        })

    diagnostics: list[dict[str, Any]] = []
    chapter_summaries: list[dict[str, Any]] = []
    for chapter_index, chapter in enumerate(book["chapters"], 1):
        chapter_id = chapter["id"]
        chapter_plans = [value for value in plans if value["chapter_id"] == chapter_id]
        budget_values = {
            dimension: add_hash({
                "id": f"density-budget-{chapter_index:04d}-{dimension}",
                "chapter_id": chapter_id,
                "dimension": dimension,
                **_budget(character_counts[chapter_id], policy, dimension),
            })
            for dimension in DIMENSIONS
        }
        selected: dict[str, list[str]] = {dimension: [] for dimension in DIMENSIONS}
        suppressed: dict[str, list[str]] = {dimension: [] for dimension in DIMENSIONS}
        eligible_counts: dict[str, int] = {}
        over_budget_counts: dict[str, int] = {}
        for dimension in DIMENSIONS:
            applicable = [
                value for value in chapter_plans
                if value["input_assistance"][dimension] is not None
            ]
            eligible = [
                value for value in applicable
                if value["planned_assistance"][dimension] == f"present-{dimension}"
            ]
            normal = [
                value for value in eligible
                if value["effective_sources"][dimension] != "explicit_user_override"
            ]
            explicit = [
                value for value in eligible
                if value["effective_sources"][dimension] == "explicit_user_override"
            ]
            budget = budget_values[dimension]["final_budget"]
            normal_selected = normal[:budget]
            normal_suppressed = normal[budget:]
            for rank, value in enumerate(eligible, 1):
                value["density_ranks"][dimension] = rank
                value["chapter_budget_ids"][dimension] = budget_values[dimension]["id"]
            for value in normal_selected:
                if value["density_decisions"][dimension] == "not-applicable":
                    value["density_decisions"][dimension] = "selected-within-budget"
                selected[dimension].append(value["id"])
            for value in normal_suppressed:
                value["planned_assistance"][dimension] = f"suppress-{dimension}"
                value["density_decisions"][dimension] = "suppressed-density-budget"
                value["rationale_codes"].append(f"{dimension}-density-budget-excluded")
                suppressed[dimension].append(value["id"])
                diagnostics.append(_diagnostic(
                    len(diagnostics) + 1, "budget-exclusion", value["source_occurrence_id"],
                    chapter_id=chapter_id, dimension=dimension,
                ))
            over_budget = 0
            for explicit_index, value in enumerate(explicit):
                if len(normal_selected) + explicit_index >= budget:
                    value["density_decisions"][dimension] = "selected-explicit-override-over-budget"
                    value["rationale_codes"].append("explicit-override-over-budget")
                    over_budget += 1
                    diagnostics.append(_diagnostic(
                        len(diagnostics) + 1, "explicit-override-over-budget",
                        value["source_occurrence_id"], chapter_id=chapter_id,
                        dimension=dimension,
                    ))
                else:
                    value["density_decisions"][dimension] = "selected-explicit-override"
                selected[dimension].append(value["id"])
            for value in applicable:
                if value["planned_assistance"][dimension] in {
                    f"suppress-{dimension}", "publisher-ruby-preserved"
                } and value["id"] not in suppressed[dimension] and value["id"] not in selected[dimension]:
                    suppressed[dimension].append(value["id"])
            eligible_counts[dimension] = len(eligible)
            over_budget_counts[dimension] = over_budget
            selected[dimension].sort(key=lambda value: int(value.rsplit("-", 1)[1]))
            suppressed[dimension].sort(key=lambda value: int(value.rsplit("-", 1)[1]))
        publisher_count = sum(
            value["publisher_ruby_id"] is not None
            or value["publisher_ruby_interaction"] != "none"
            for value in chapter_plans
        )
        summary = {
            "id": f"density-chapter-summary-{chapter_index:04d}",
            "chapter_id": chapter_id,
            "canonical_character_count": character_counts[chapter_id],
            "eligible_action_counts": eligible_counts,
            "selected_action_counts": {key: len(value) for key, value in selected.items()},
            "suppressed_action_counts": {key: len(value) for key, value in suppressed.items()},
            "normal_budgets": budget_values,
            "explicit_override_over_budget_counts": over_budget_counts,
            "publisher_protected_count": publisher_count,
            "selected_occurrence_plan_ids": selected,
            "suppressed_occurrence_plan_ids": suppressed,
        }
        chapter_summaries.append(add_hash(summary))

    occurrence_order = {
        value["source_occurrence_id"]: value["canonical_source_order"]
        for value in plans
    }
    diagnostics.sort(key=lambda value: (
        occurrence_order.get(value["source_id"], 9999),
        DIMENSIONS.index(value["dimension"]) if value["dimension"] in DIMENSIONS else 9999,
        value["reason"],
    ))
    diagnostics = [
        _diagnostic(
            number, value["reason"], value["source_id"],
            chapter_id=value["chapter_id"], dimension=value["dimension"],
        )
        for number, value in enumerate(diagnostics, 1)
    ]
    plans = [add_hash(value) for value in plans]
    configuration = add_hash({"enabled": True, "policy_id": policy["id"]})
    value = {
        "schema_version": SCHEMA_VERSION,
        "report_id": "per-occurrence-assistance-plan-v1",
        "book_id": book["book_id"],
        "source_schema_versions": {
            "canonical_book": 2, "annotation_plan": 2,
            "grammar_plan": 1 if grammar_plan is not None else None,
            "assistance_report": 1, "density_policy": POLICY_SCHEMA_VERSION,
        },
        "source_hashes": {
            "canonical_book": stable_hash(book),
            "annotation_plan": stable_hash(annotation_plan),
            "grammar_plan": stable_hash(grammar_plan) if grammar_plan is not None else "none",
            "assistance_report": assistance["hash"],
            "density_policy_dataset": policy_dataset["hash"],
        },
        "policy": {
            "dataset_id": policy_dataset["dataset_id"],
            "dataset_version": policy_dataset["dataset_version"],
            "policy_id": policy["id"],
            "preset_id": policy["preset_id"],
            "policy_hash": policy["hash"],
        },
        "precedence": PRECEDENCE,
        "configuration": configuration,
        "occurrence_plans": plans,
        "chapter_summaries": chapter_summaries,
        "diagnostics": diagnostics,
    }
    value["hash"] = stable_hash(value)
    return value


def safe_build_density_report(
    book: dict[str, Any],
    annotation_plan: dict[str, Any],
    grammar_plan: dict[str, Any] | None,
    assistance: dict[str, Any] | None,
    policy_dataset: dict[str, Any] | None,
    *,
    policy_id: str | None = None,
    enabled: bool = False,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    if not enabled:
        return _empty_report(book.get("book_id"), "disabled")
    if failure_reason:
        return _empty_report(book.get("book_id"), failure_reason)
    try:
        return build_density_report(
            book, annotation_plan, grammar_plan, assistance, policy_dataset,
            policy_id=policy_id, enabled=True,
        )
    except AssistanceDensityError as error:
        message = str(error).lower()
        mapping = (
            ("unknown density policy", "unknown-density-policy"),
            ("preset/policy mismatch", "preset-policy-mismatch"),
            ("source-hash", "source-hash-mismatch"),
            ("invalid character", "invalid-character-count"),
            ("invalid density target", "invalid-density-target"),
            ("minimum or maximum", "invalid-minimum-maximum"),
            ("unknown occurrence", "unknown-occurrence"),
            ("duplicate occurrence", "duplicate-occurrence"),
            ("occurrence offset", "invalid-occurrence-offset"),
            ("unordered", "unordered-occurrence"),
            ("cross-chapter", "cross-chapter-occurrence"),
            ("publisher ruby", "publisher-ruby-suppression-attempt"),
            ("grammar", "grammar-disposition-conflict"),
            ("unsupported", "unsupported-schema-or-field"),
        )
        reason = next((code for text, code in mapping if text in message), "invalid-configuration")
        return _empty_report(book.get("book_id"), reason)


def validate_density_report(
    book: dict[str, Any],
    annotation_plan: dict[str, Any],
    grammar_plan: dict[str, Any] | None,
    assistance: dict[str, Any],
    policy_dataset: dict[str, Any],
    report: dict[str, Any],
    *,
    policy_id: str | None = None,
) -> None:
    expected = build_density_report(
        book, annotation_plan, grammar_plan, assistance, policy_dataset,
        policy_id=policy_id, enabled=True,
    )
    if report != expected:
        raise AssistanceDensityError("Density report is not deterministic or valid")
    if any(
        decision not in ALLOWED_DECISIONS
        for occurrence in report["occurrence_plans"]
        for decision in occurrence["density_decisions"].values()
    ):
        raise AssistanceDensityError("Invalid density decision")
