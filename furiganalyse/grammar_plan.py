"""Deterministic grammar study-item and vocabulary-overlap planning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from furiganalyse.grammar_analysis import (
    GrammarAnalysisError,
    load_json,
    stable_hash,
    validate_dataset,
    validate_grammar_report,
)

SCHEMA_VERSION = 1
SYNTHETIC_MECHANICS_RULE_ID = "grammar-rule-0006"
OVERLAP_RELATIONS = {
    "contains-vocabulary",
    "contained-by-vocabulary",
    "exact-span",
    "partial-overlap",
    "no-overlap",
    "publisher-ruby-protected",
}
LINK_DISPOSITIONS = {
    "grammar-link",
    "vocabulary-link",
    "separate-nonoverlapping-links",
    "grammar-note-reference-only",
    "publisher-ruby-preserved",
    "rejected-ambiguous-overlap",
}


class GrammarPlanError(ValueError):
    """Raised when a grammar plan or overlap disposition is invalid."""


def serialize_grammar_plan(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _source_maps(book, vocabulary, annotation_plan):
    sentences = {
        sentence["id"]: (chapter, block, sentence)
        for chapter in book.get("chapters", [])
        for block in chapter.get("blocks", [])
        for sentence in block.get("sentences", [])
    }
    tokens = {token["id"]: token for token in vocabulary.get("tokens", [])}
    candidates = {candidate["id"]: candidate for candidate in vocabulary.get("candidates", [])}
    ruby_ids = {
        ruby["id"]
        for chapter in book.get("chapters", [])
        for block in chapter.get("blocks", [])
        for ruby in block.get("publisher_ruby", [])
    }
    plan_occurrences = []
    anchors = set()
    occurrence_ids = set()
    for item in annotation_plan.get("items", []):
        if item.get("kind") not in {"vocabulary", "expression", "name"}:
            raise GrammarPlanError("Unsupported vocabulary item kind")
        if item.get("note_anchor_id"):
            if item["note_anchor_id"] in anchors:
                raise GrammarPlanError("Duplicate source note anchor")
            anchors.add(item["note_anchor_id"])
        for occurrence in item.get("occurrences", []):
            if occurrence.get("id") in occurrence_ids:
                raise GrammarPlanError("Duplicate vocabulary occurrence")
            occurrence_ids.add(occurrence.get("id"))
            source = sentences.get(occurrence.get("sentence_id"))
            if source is None:
                raise GrammarPlanError("Unknown vocabulary occurrence sentence")
            chapter, block, sentence = source
            if (
                occurrence.get("chapter_id") != chapter["id"]
                or occurrence.get("block_id") != block["id"]
            ):
                raise GrammarPlanError("Mismatched vocabulary occurrence source")
            start, end = occurrence.get("sentence_start"), occurrence.get("sentence_end")
            if (
                not isinstance(start, int)
                or not isinstance(end, int)
                or not 0 <= start < end <= len(sentence["text"])
                or occurrence.get("block_start") != sentence["start"] + start
                or occurrence.get("block_end") != sentence["start"] + end
            ):
                raise GrammarPlanError("Invalid vocabulary occurrence offsets")
            if any(token_id not in tokens for token_id in occurrence.get("token_ids", [])):
                raise GrammarPlanError("Unknown vocabulary occurrence token")
            if any(candidate_id not in candidates for candidate_id in occurrence.get("candidate_ids", [])):
                raise GrammarPlanError("Unknown vocabulary occurrence candidate")
            if occurrence.get("publisher_ruby_id") not in ruby_ids | {None}:
                raise GrammarPlanError("Unknown publisher-ruby reference")
            if occurrence.get("source_anchor_id"):
                if occurrence["source_anchor_id"] in anchors:
                    raise GrammarPlanError("Duplicate source occurrence anchor")
                anchors.add(occurrence["source_anchor_id"])
            plan_occurrences.append((item, occurrence))
    return sentences, tokens, candidates, plan_occurrences, anchors


def _validate_sources(book, vocabulary, annotation_plan, grammar_report, dataset):
    _validate_base_sources(book, vocabulary, annotation_plan)
    book_id = book.get("book_id")
    if grammar_report.get("book_id") != book_id:
        raise GrammarPlanError("Mismatched grammar-report book identity")
    try:
        validate_dataset(dataset)
        validate_grammar_report(book, vocabulary, grammar_report)
    except GrammarAnalysisError as error:
        raise GrammarPlanError("Invalid grammar source") from error
    report_dataset = grammar_report.get("dataset") or {}
    if (
        report_dataset.get("id") != dataset.get("dataset_id")
        or report_dataset.get("version") != dataset.get("dataset_version")
        or report_dataset.get("rules")
        != [{"id": rule["id"], "hash": rule["hash"]} for rule in dataset["rules"]]
    ):
        raise GrammarPlanError("Stale grammar dataset or report mismatch")


def _validate_base_sources(book, vocabulary, annotation_plan):
    if book.get("schema_version") != 2:
        raise GrammarPlanError("Unsupported canonical schema")
    if vocabulary.get("schema_version") != 4:
        raise GrammarPlanError("Unsupported vocabulary schema")
    if annotation_plan.get("schema_version") != 2:
        raise GrammarPlanError("Unsupported annotation-plan schema")
    book_id = book.get("book_id")
    if any(value.get("book_id") != book_id for value in (vocabulary, annotation_plan)):
        raise GrammarPlanError("Mismatched source book identity")


def _relationship(grammar, vocabulary_occurrence):
    gs, ge = grammar["sentence_start"], grammar["sentence_end"]
    vs, ve = vocabulary_occurrence["sentence_start"], vocabulary_occurrence["sentence_end"]
    if (
        grammar["publisher_ruby_interaction"] == "adjacent-preserved-publisher-ruby"
        and vocabulary_occurrence.get("publisher_ruby_id")
        and (ge == vs or ve == gs)
    ):
        return "publisher-ruby-protected"
    if gs == vs and ge == ve:
        return "exact-span"
    if gs <= vs and ve <= ge:
        return "contains-vocabulary"
    if vs <= gs and ge <= ve:
        return "contained-by-vocabulary"
    if gs < ve and vs < ge:
        return "partial-overlap"
    return "no-overlap"


def _disposition(relations, has_same_sentence_vocabulary):
    if "partial-overlap" in relations:
        return "partial-overlap", "rejected-ambiguous-overlap"
    if "publisher-ruby-protected" in relations:
        return "publisher-ruby-protected", "publisher-ruby-preserved"
    if "exact-span" in relations:
        return "exact-span", "grammar-note-reference-only"
    if "contains-vocabulary" in relations:
        return "contains-vocabulary", "grammar-note-reference-only"
    if "contained-by-vocabulary" in relations:
        return "contained-by-vocabulary", "grammar-note-reference-only"
    if has_same_sentence_vocabulary:
        return "no-overlap", "separate-nonoverlapping-links"
    return "no-overlap", "grammar-link"


def build_grammar_plan(
    book: dict[str, Any],
    vocabulary: dict[str, Any],
    annotation_plan: dict[str, Any],
    grammar_report: dict[str, Any],
    dataset: dict[str, Any],
    *,
    enabled: bool = False,
    per_chapter_limit: int = 4,
    include_synthetic_mechanics: bool = False,
) -> dict[str, Any]:
    _validate_base_sources(book, vocabulary, annotation_plan)
    if not isinstance(per_chapter_limit, int) or per_chapter_limit < 1:
        raise GrammarPlanError("Invalid per-chapter grammar-item limit")
    config = {
        "enabled": enabled,
        "per_chapter_item_limit": per_chapter_limit,
        "include_synthetic_mechanics": include_synthetic_mechanics,
    }
    base = {
        "schema_version": SCHEMA_VERSION,
        "book_id": book["book_id"],
        "source_book_schema_version": 2,
        "source_vocabulary_schema_version": 4,
        "source_annotation_plan_schema_version": 2,
        "source_grammar_report_schema_version": 1,
        "source_hashes": {
            "book": stable_hash(book),
            "vocabulary": stable_hash(vocabulary),
            "annotation_plan": stable_hash(annotation_plan),
            "grammar_report": stable_hash(grammar_report),
        },
        "dataset": None,
        "config": config,
        "items": [],
        "occurrences": [],
        "overlaps": [],
        "diagnostics": [],
    }
    if not enabled:
        return base
    _validate_sources(book, vocabulary, annotation_plan, grammar_report, dataset)
    base["dataset"] = {
        "id": dataset["dataset_id"],
        "version": dataset["dataset_version"],
        "source_provenance": dataset["source_provenance"],
    }

    sentences, tokens, vocabulary_candidates, plan_occurrences, existing_anchors = _source_maps(
        book, vocabulary, annotation_plan
    )
    rules = {rule["id"]: rule for rule in dataset["rules"]}
    chapter_item_counts: dict[str, int] = {}
    selected_candidates = []
    raw_diagnostics = []
    for candidate in grammar_report["candidates"]:
        rule = rules.get(candidate["rule_id"])
        if rule is None:
            raise GrammarPlanError("Unknown grammar rule")
        if candidate["rule_id"] == SYNTHETIC_MECHANICS_RULE_ID and not include_synthetic_mechanics:
            raw_diagnostics.append({
                "reason": "synthetic-mechanics-rule",
                "source_id": candidate["id"],
                "chapter_id": candidate["first_location"]["chapter_id"],
            })
            continue
        chapter_id = candidate["first_location"]["chapter_id"]
        if chapter_item_counts.get(chapter_id, 0) >= per_chapter_limit:
            raw_diagnostics.append({
                "reason": "per-chapter-limit",
                "source_id": candidate["id"],
                "chapter_id": chapter_id,
            })
            continue
        chapter_item_counts[chapter_id] = chapter_item_counts.get(chapter_id, 0) + 1
        selected_candidates.append((candidate, rule))

    selected_source_occurrences = {
        occurrence_id
        for candidate, _ in selected_candidates
        for occurrence_id in candidate["occurrence_ids"]
    }
    for diagnostic in grammar_report["diagnostics"]:
        if diagnostic["reason"] == "publisher-ruby-protected":
            raw_diagnostics.append({
                "reason": "publisher-ruby-conflict",
                "source_id": diagnostic["id"],
                "chapter_id": diagnostic["sentence_id"].split("-b-")[0],
            })

    overlaps = []
    occurrences = []
    item_occurrence_ids: dict[str, list[str]] = {}
    for source in grammar_report["occurrences"]:
        if source["id"] not in selected_source_occurrences:
            continue
        same_sentence = [
            (item, occurrence)
            for item, occurrence in plan_occurrences
            if occurrence.get("sentence_id") == source["sentence_id"]
        ]
        relations = []
        for item, vocabulary_occurrence in same_sentence:
            relation = _relationship(source, vocabulary_occurrence)
            relations.append(relation)
            overlap = {
                "id": f"grammar-overlap-{len(overlaps) + 1:04d}",
                "grammar_occurrence_id": source["id"],
                "vocabulary_item_id": item["id"],
                "vocabulary_occurrence_id": vocabulary_occurrence["id"],
                "vocabulary_kind": item["kind"],
                "relationship": relation,
                "vocabulary_link_preserved": True,
                "reason": {
                    "contains-vocabulary": "grammar-contains-existing-vocabulary-link",
                    "contained-by-vocabulary": "grammar-contained-by-existing-vocabulary-link",
                    "exact-span": "exact-span-preserve-vocabulary-link",
                    "partial-overlap": "unsafe-partial-overlap-preserve-vocabulary-link",
                    "no-overlap": "same-sentence-nonoverlapping-links",
                    "publisher-ruby-protected": "publisher-ruby-precedence",
                }[relation],
            }
            overlap["hash"] = stable_hash(overlap)
            overlaps.append(overlap)
            if relation == "contains-vocabulary":
                raw_diagnostics.append({"reason": "containing-overlap", "source_id": source["id"], "chapter_id": source["chapter_id"]})
            elif relation == "exact-span":
                raw_diagnostics.append({"reason": "exact-span-overlap", "source_id": source["id"], "chapter_id": source["chapter_id"]})
            elif relation == "partial-overlap":
                raw_diagnostics.append({"reason": "partial-overlap-rejected", "source_id": source["id"], "chapter_id": source["chapter_id"]})

        overlap_disposition, link_disposition = _disposition(relations, bool(same_sentence))
        occurrence = {
            "id": f"grammar-plan-occurrence-{len(occurrences) + 1:04d}",
            "source_grammar_occurrence_id": source["id"],
            "chapter_id": source["chapter_id"],
            "block_id": source["block_id"],
            "sentence_id": source["sentence_id"],
            "sentence_record_id": source["sentence_record_id"],
            "surface": source["surface"],
            "sentence_start": source["sentence_start"],
            "sentence_end": source["sentence_end"],
            "block_start": source["block_start"],
            "block_end": source["block_end"],
            "component_token_ids": list(source["component_token_ids"]),
            "overlapping_candidate_ids": list(source["overlapping_candidate_ids"]),
            "publisher_ruby_interaction": source["publisher_ruby_interaction"],
            "source_anchor_id": f"grammar-src-{source['id']}",
            "link_disposition": link_disposition,
            "overlap_disposition": overlap_disposition,
        }
        occurrence["hash"] = stable_hash(occurrence)
        if occurrence["source_anchor_id"] in existing_anchors:
            raise GrammarPlanError("Grammar source anchor collision")
        existing_anchors.add(occurrence["source_anchor_id"])
        occurrences.append(occurrence)
        item_occurrence_ids.setdefault(source["rule_id"], []).append(occurrence["id"])

    items = []
    for candidate, rule in selected_candidates:
        occurrence_ids = item_occurrence_ids.get(rule["id"], [])
        item = {
            "id": f"grammar-item-{len(items) + 1:04d}",
            "grammar_candidate_id": candidate["id"],
            "rule_id": rule["id"],
            "dataset_id": dataset["dataset_id"],
            "dataset_version": dataset["dataset_version"],
            "dataset_source_provenance": dataset["source_provenance"],
            "rule_hash": rule["hash"],
            "canonical_key": rule["canonical_key"],
            "label": rule["label"],
            "explanation": rule["explanation"],
            "formation_patterns": list(rule["formation_patterns"]),
            "usage_labels": list(rule["usage_labels"]),
            "source_provenance": rule["source_provenance"],
            "occurrence_ids": occurrence_ids,
            "chapter_counts": list(candidate["chapter_counts"]),
            "book_count": candidate["book_count"],
            "selection_status": "selected",
            "selection_reason": "exact-curated-rule-within-chapter-limit",
            "note_anchor_id": f"grammar-note-{len(items) + 1:04d}",
        }
        if item["note_anchor_id"] in existing_anchors:
            raise GrammarPlanError("Grammar note anchor collision")
        existing_anchors.add(item["note_anchor_id"])
        item["hash"] = stable_hash(item)
        items.append(item)

    diagnostics = []
    for raw in raw_diagnostics:
        diagnostic = {
            "id": f"grammar-plan-diagnostic-{len(diagnostics) + 1:04d}",
            **raw,
        }
        diagnostic["hash"] = stable_hash(diagnostic)
        diagnostics.append(diagnostic)
    base.update({
        "items": items,
        "occurrences": occurrences,
        "overlaps": overlaps,
        "diagnostics": diagnostics,
    })
    validate_grammar_plan(book, vocabulary, annotation_plan, grammar_report, dataset, base)
    return base


def validate_grammar_plan(book, vocabulary, annotation_plan, grammar_report, dataset, plan):
    _validate_sources(book, vocabulary, annotation_plan, grammar_report, dataset)
    required = {
        "schema_version", "book_id", "source_book_schema_version",
        "source_vocabulary_schema_version", "source_annotation_plan_schema_version",
        "source_grammar_report_schema_version", "source_hashes", "dataset", "config",
        "items", "occurrences", "overlaps", "diagnostics",
    }
    if set(plan) != required or plan.get("schema_version") != SCHEMA_VERSION:
        raise GrammarPlanError("Unsupported grammar-plan schema")
    if plan["book_id"] != book["book_id"]:
        raise GrammarPlanError("Grammar-plan book mismatch")
    expected_hashes = {
        "book": stable_hash(book),
        "vocabulary": stable_hash(vocabulary),
        "annotation_plan": stable_hash(annotation_plan),
        "grammar_report": stable_hash(grammar_report),
    }
    if plan["source_hashes"] != expected_hashes:
        raise GrammarPlanError("Stale grammar-plan source hash")
    if set(plan["config"]) != {
        "enabled", "per_chapter_item_limit", "include_synthetic_mechanics"
    }:
        raise GrammarPlanError("Invalid grammar-plan configuration")
    if (
        plan["config"]["enabled"] is not True
        or not isinstance(plan["config"]["per_chapter_item_limit"], int)
        or plan["config"]["per_chapter_item_limit"] < 1
        or not isinstance(plan["config"]["include_synthetic_mechanics"], bool)
    ):
        raise GrammarPlanError("Invalid grammar-plan configuration")
    ids = set()
    source_occurrences = {value["id"]: value for value in grammar_report["occurrences"]}
    source_candidates = {value["id"]: value for value in grammar_report["candidates"]}
    rules = {value["id"]: value for value in dataset["rules"]}
    sentence_map, token_map, candidate_map, vocabulary_occurrences, existing_anchors = _source_maps(
        book, vocabulary, annotation_plan
    )
    vocabulary_occurrence_by_id = {
        occurrence["id"]: (item, occurrence)
        for item, occurrence in vocabulary_occurrences
    }
    previous = None
    chapter_selected: dict[str, int] = {}
    for index, item in enumerate(plan["items"], 1):
        if item["id"] != f"grammar-item-{index:04d}" or item["id"] in ids:
            raise GrammarPlanError("Duplicate or unstable grammar item ID")
        ids.add(item["id"])
        candidate = source_candidates.get(item["grammar_candidate_id"])
        rule = rules.get(item["rule_id"])
        if candidate is None or rule is None or candidate["rule_id"] != rule["id"]:
            raise GrammarPlanError("Unknown grammar item source")
        if rule["id"] == SYNTHETIC_MECHANICS_RULE_ID and not plan["config"]["include_synthetic_mechanics"]:
            raise GrammarPlanError("Synthetic mechanics rule selected without explicit enablement")
        for field in ("canonical_key", "label", "explanation", "formation_patterns", "usage_labels", "source_provenance"):
            if item[field] != rule[field]:
                raise GrammarPlanError("Grammar rule content changed")
        if item["rule_hash"] != rule["hash"] or item["hash"] != stable_hash({k: v for k, v in item.items() if k != "hash"}):
            raise GrammarPlanError("Invalid grammar item hash")
        chapter_id = candidate["first_location"]["chapter_id"]
        chapter_selected[chapter_id] = chapter_selected.get(chapter_id, 0) + 1
        if chapter_selected[chapter_id] > plan["config"]["per_chapter_item_limit"]:
            raise GrammarPlanError("Per-chapter grammar limit exceeded")
        if item["note_anchor_id"] in existing_anchors:
            raise GrammarPlanError("Grammar note anchor collision")
        existing_anchors.add(item["note_anchor_id"])

    occurrence_by_id = {}
    for index, occurrence in enumerate(plan["occurrences"], 1):
        if occurrence["id"] != f"grammar-plan-occurrence-{index:04d}" or occurrence["id"] in ids:
            raise GrammarPlanError("Duplicate or unstable grammar occurrence ID")
        ids.add(occurrence["id"])
        source = source_occurrences.get(occurrence["source_grammar_occurrence_id"])
        if source is None:
            raise GrammarPlanError("Unknown grammar occurrence source")
        for field in (
            "chapter_id", "block_id", "sentence_id", "sentence_record_id", "surface",
            "sentence_start", "sentence_end", "block_start", "block_end",
            "component_token_ids", "overlapping_candidate_ids", "publisher_ruby_interaction",
        ):
            if occurrence[field] != source[field]:
                raise GrammarPlanError("Grammar occurrence source changed")
        if occurrence["sentence_id"] not in sentence_map:
            raise GrammarPlanError("Unknown grammar sentence")
        _, _, sentence = sentence_map[occurrence["sentence_id"]]
        if sentence["text"][occurrence["sentence_start"]:occurrence["sentence_end"]] != occurrence["surface"]:
            raise GrammarPlanError("Grammar occurrence text mismatch")
        if any(token_id not in token_map for token_id in occurrence["component_token_ids"]):
            raise GrammarPlanError("Unknown grammar component token")
        if any(candidate_id not in candidate_map for candidate_id in occurrence["overlapping_candidate_ids"]):
            raise GrammarPlanError("Unknown grammar vocabulary candidate")
        order = (occurrence["chapter_id"], occurrence["block_id"], occurrence["sentence_id"], occurrence["sentence_start"])
        if previous is not None and order < previous:
            raise GrammarPlanError("Unordered grammar-plan occurrences")
        previous = order
        if occurrence["link_disposition"] not in LINK_DISPOSITIONS or occurrence["overlap_disposition"] not in OVERLAP_RELATIONS:
            raise GrammarPlanError("Unsupported overlap disposition")
        if occurrence["source_anchor_id"] in existing_anchors:
            raise GrammarPlanError("Grammar source anchor collision")
        existing_anchors.add(occurrence["source_anchor_id"])
        if occurrence["hash"] != stable_hash({k: v for k, v in occurrence.items() if k != "hash"}):
            raise GrammarPlanError("Invalid grammar occurrence hash")
        occurrence_by_id[occurrence["id"]] = occurrence

    source_plan_occurrence_by_source = {
        value["source_grammar_occurrence_id"]: value
        for value in plan["occurrences"]
    }
    for item in plan["items"]:
        if any(value not in occurrence_by_id for value in item["occurrence_ids"]):
            raise GrammarPlanError("Unknown grammar item occurrence")
        candidate = source_candidates[item["grammar_candidate_id"]]
        expected_occurrence_ids = [
            source_plan_occurrence_by_source[source_id]["id"]
            for source_id in candidate["occurrence_ids"]
            if source_id in source_plan_occurrence_by_source
        ]
        if item["occurrence_ids"] != expected_occurrence_ids:
            raise GrammarPlanError("Grammar item occurrence order mismatch")
    expected_overlap_keys = []
    for plan_occurrence in plan["occurrences"]:
        source = source_occurrences[plan_occurrence["source_grammar_occurrence_id"]]
        for vocabulary_item, vocabulary_occurrence in vocabulary_occurrences:
            if vocabulary_occurrence["sentence_id"] == source["sentence_id"]:
                expected_overlap_keys.append((
                    source["id"], vocabulary_item["id"], vocabulary_occurrence["id"]
                ))
    actual_overlap_keys = [
        (
            overlap["grammar_occurrence_id"],
            overlap["vocabulary_item_id"],
            overlap["vocabulary_occurrence_id"],
        )
        for overlap in plan["overlaps"]
    ]
    if actual_overlap_keys != expected_overlap_keys:
        raise GrammarPlanError("Missing or unordered overlap dispositions")
    relationships_by_source: dict[str, list[str]] = {}
    for index, overlap in enumerate(plan["overlaps"], 1):
        if overlap["id"] != f"grammar-overlap-{index:04d}" or overlap["id"] in ids:
            raise GrammarPlanError("Duplicate or unstable overlap ID")
        ids.add(overlap["id"])
        source = source_occurrences.get(overlap["grammar_occurrence_id"])
        vocabulary_source = vocabulary_occurrence_by_id.get(overlap["vocabulary_occurrence_id"])
        if source is None or vocabulary_source is None:
            raise GrammarPlanError("Unknown overlap source")
        vocabulary_item, vocabulary_occurrence = vocabulary_source
        expected_relationship = _relationship(source, vocabulary_occurrence)
        if (
            overlap["vocabulary_item_id"] != vocabulary_item["id"]
            or overlap["vocabulary_kind"] != vocabulary_item["kind"]
            or overlap["relationship"] != expected_relationship
        ):
            raise GrammarPlanError("Incorrect overlap classification")
        if overlap["relationship"] not in OVERLAP_RELATIONS or not overlap["vocabulary_link_preserved"]:
            raise GrammarPlanError("Vocabulary link suppression is forbidden")
        if overlap["hash"] != stable_hash({k: v for k, v in overlap.items() if k != "hash"}):
            raise GrammarPlanError("Invalid overlap hash")
        relationships_by_source.setdefault(source["id"], []).append(expected_relationship)
    for occurrence in plan["occurrences"]:
        source_id = occurrence["source_grammar_occurrence_id"]
        relations = relationships_by_source.get(source_id, [])
        expected_overlap, expected_link = _disposition(relations, bool(relations))
        if (
            occurrence["overlap_disposition"] != expected_overlap
            or occurrence["link_disposition"] != expected_link
        ):
            raise GrammarPlanError("Incorrect grammar link disposition")
    for index, diagnostic in enumerate(plan["diagnostics"], 1):
        if diagnostic["id"] != f"grammar-plan-diagnostic-{index:04d}" or diagnostic["id"] in ids:
            raise GrammarPlanError("Duplicate or unstable grammar diagnostic ID")
        ids.add(diagnostic["id"])
        if diagnostic["hash"] != stable_hash({k: v for k, v in diagnostic.items() if k != "hash"}):
            raise GrammarPlanError("Invalid grammar diagnostic hash")


def safe_build_grammar_plan(*args, **kwargs):
    forced_reason = kwargs.pop("_failure_reason", None)
    try:
        return build_grammar_plan(*args, **kwargs)
    except (GrammarPlanError, GrammarAnalysisError, KeyError, TypeError, ValueError) as error:
        book = args[0] if args else {}
        vocabulary = args[1] if len(args) > 1 else {}
        annotation_plan = args[2] if len(args) > 2 else {}
        grammar_report = args[3] if len(args) > 3 else {}
        reason = forced_reason
        if reason is None:
            reason = "stale-input" if "stale" in str(error).lower() else "invalid-input"
        diagnostic = {
            "id": "grammar-plan-diagnostic-0001",
            "reason": reason,
            "source_id": "grammar-plan-input",
            "chapter_id": None,
        }
        diagnostic["hash"] = stable_hash(diagnostic)
        return {
            "schema_version": SCHEMA_VERSION,
            "book_id": book.get("book_id", "unknown"),
            "source_book_schema_version": book.get("schema_version"),
            "source_vocabulary_schema_version": vocabulary.get("schema_version"),
            "source_annotation_plan_schema_version": annotation_plan.get("schema_version"),
            "source_grammar_report_schema_version": grammar_report.get("schema_version"),
            "source_hashes": {},
            "dataset": None,
            "config": {
                "enabled": False,
                "per_chapter_item_limit": kwargs.get("per_chapter_limit", 4),
                "include_synthetic_mechanics": False,
            },
            "items": [],
            "occurrences": [],
            "overlaps": [],
            "diagnostics": [diagnostic],
        }


def load_plan_json(path: str | Path):
    return load_json(path)
