"""Deterministic curated grammar detection over existing canonical reports."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DATASET_SCHEMA_VERSION = 1
CONFIDENCE_VALUES = {"exact-curated-rule"}
SAFE_TEXT = re.compile(r"^[^<>\x00-\x1f]*$")


class GrammarAnalysisError(ValueError):
    """Raised when grammar input or output violates deterministic invariants."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def serialize_grammar_report(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GrammarAnalysisError("JSON root must be an object")
    return value


def validate_dataset(dataset: dict[str, Any]) -> None:
    expected = {
        "schema_version", "dataset_id", "dataset_version", "fixture_notice",
        "source_provenance", "rules",
    }
    if set(dataset) != expected or dataset.get("schema_version") != DATASET_SCHEMA_VERSION:
        raise GrammarAnalysisError("Unsupported grammar dataset schema")
    for field in ("dataset_id", "dataset_version", "fixture_notice", "source_provenance"):
        if not isinstance(dataset.get(field), str) or not dataset[field] or not SAFE_TEXT.match(dataset[field]):
            raise GrammarAnalysisError(f"Invalid grammar dataset field: {field}")
    if "synthetic" not in dataset["fixture_notice"].lower():
        raise GrammarAnalysisError("Grammar fixture must identify itself as synthetic")
    seen: set[str] = set()
    rule_keys = {
        "id", "canonical_key", "surface_patterns", "label", "explanation",
        "formation_patterns", "usage_labels", "positive_examples",
        "exclusion_patterns", "priority", "source_provenance", "hash",
    }
    for index, rule in enumerate(dataset.get("rules", []), 1):
        if set(rule) != rule_keys or rule.get("id") != f"grammar-rule-{index:04d}":
            raise GrammarAnalysisError("Invalid or unstable grammar rule")
        if rule["id"] in seen:
            raise GrammarAnalysisError("Duplicate grammar rule ID")
        seen.add(rule["id"])
        for field in ("canonical_key", "label", "explanation", "source_provenance"):
            if not isinstance(rule[field], str) or not rule[field] or not SAFE_TEXT.match(rule[field]):
                raise GrammarAnalysisError(f"Invalid grammar rule field: {field}")
        for field in ("surface_patterns", "formation_patterns", "usage_labels", "positive_examples", "exclusion_patterns"):
            if not isinstance(rule[field], list) or any(
                not isinstance(item, str) or not item or not SAFE_TEXT.match(item)
                for item in rule[field]
            ):
                raise GrammarAnalysisError(f"Invalid grammar rule list: {field}")
        if not rule["surface_patterns"] or not isinstance(rule["priority"], int):
            raise GrammarAnalysisError("Rule requires patterns and integer priority")
        body = {key: value for key, value in rule.items() if key != "hash"}
        if rule["hash"] != stable_hash(body):
            raise GrammarAnalysisError(f"Invalid grammar rule hash: {rule['id']}")


def prepare_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    value = json.loads(json.dumps(dataset, ensure_ascii=False))
    for rule in value["rules"]:
        rule["hash"] = stable_hash({key: item for key, item in rule.items() if key != "hash"})
    validate_dataset(value)
    return value


def _source_maps(book: dict[str, Any], vocabulary: dict[str, Any]):
    chapters: dict[str, dict] = {}
    blocks: dict[str, dict] = {}
    sentences: dict[str, tuple[dict, dict, dict]] = {}
    ruby: dict[str, dict] = {}
    for chapter in book.get("chapters", []):
        chapters[chapter["id"]] = chapter
        for block in chapter["blocks"]:
            blocks[block["id"]] = block
            for record in block.get("publisher_ruby", []):
                ruby[record["id"]] = record
            for sentence in block["sentences"]:
                sentences[sentence["id"]] = (chapter, block, sentence)
    tokens = {token["id"]: token for token in vocabulary.get("tokens", [])}
    candidates_by_token: dict[str, list[str]] = {}
    for candidate in vocabulary.get("candidates", []):
        candidates_by_token.setdefault(candidate["token_id"], []).append(candidate["id"])
    lexical_expressions = [
        (expression["sentence_id"], expression["sentence_start"], expression["sentence_end"])
        for expression in vocabulary.get("expressions", [])
    ]
    return chapters, blocks, sentences, ruby, tokens, candidates_by_token, lexical_expressions


def _validate_inputs(book: dict[str, Any], vocabulary: dict[str, Any], plan: dict[str, Any]) -> None:
    if book.get("schema_version") != 2:
        raise GrammarAnalysisError("Unsupported canonical book schema")
    if vocabulary.get("schema_version") != 4:
        raise GrammarAnalysisError("Unsupported vocabulary schema")
    if plan.get("schema_version") != 2:
        raise GrammarAnalysisError("Unsupported annotation-plan schema")
    book_id = book.get("book_id")
    if vocabulary.get("book_id") != book_id or plan.get("book_id") != book_id:
        raise GrammarAnalysisError("Mismatched book identity")


def detect_grammar(
    book: dict[str, Any],
    vocabulary: dict[str, Any],
    plan: dict[str, Any],
    dataset: dict[str, Any] | None,
    *,
    disabled: bool = False,
) -> dict[str, Any]:
    _validate_inputs(book, vocabulary, plan)
    if disabled:
        return {
            "schema_version": SCHEMA_VERSION,
            "book_id": book["book_id"],
            "source_book_schema_version": 2,
            "source_vocabulary_schema_version": 4,
            "source_annotation_plan_schema_version": 2,
            "dataset": None,
            "occurrences": [],
            "candidates": [],
            "diagnostics": [],
        }
    if dataset is None:
        raise GrammarAnalysisError("Explicit grammar dataset required")
    validate_dataset(dataset)
    chapters, blocks, sentences, ruby, token_map, candidates_by_token, lexical = _source_maps(book, vocabulary)
    sentence_tokens: dict[str, list[dict]] = {}
    for token in vocabulary.get("tokens", []):
        if token["sentence_id"] not in sentences:
            raise GrammarAnalysisError(f"Unknown token sentence: {token['id']}")
        chapter, block, sentence = sentences[token["sentence_id"]]
        if token["chapter_id"] != chapter["id"] or token["block_id"] != block["id"]:
            raise GrammarAnalysisError(f"Mismatched token source: {token['id']}")
        if not (0 <= token["sentence_start"] < token["sentence_end"] <= len(sentence["text"])):
            raise GrammarAnalysisError(f"Invalid token offsets: {token['id']}")
        if sentence["text"][token["sentence_start"]:token["sentence_end"]] != token["surface"]:
            raise GrammarAnalysisError(f"Token text mismatch: {token['id']}")
        sentence_tokens.setdefault(token["sentence_id"], []).append(token)

    proposals: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    rule_order = {rule["id"]: index for index, rule in enumerate(dataset["rules"])}
    for sentence_id, tokens in sentence_tokens.items():
        chapter, block, sentence = sentences[sentence_id]
        tokens = sorted(tokens, key=lambda item: (item["sentence_start"], item["sentence_end"], item["id"]))
        for rule in dataset["rules"]:
            exclusions = set(rule["exclusion_patterns"])
            for pattern in rule["surface_patterns"]:
                for start_index in range(len(tokens)):
                    surface = ""
                    component: list[dict] = []
                    for token in tokens[start_index:]:
                        if component and token["sentence_start"] != component[-1]["sentence_end"]:
                            break
                        surface += token["surface"]
                        component.append(token)
                        if not pattern.startswith(surface):
                            break
                        if surface != pattern:
                            continue
                        start = component[0]["sentence_start"]
                        end = component[-1]["sentence_end"]
                        if surface in exclusions:
                            continue
                        if any(item.get("publisher_ruby_id") for item in component):
                            diagnostics.append({
                                "reason": "publisher-ruby-protected",
                                "rule_id": rule["id"],
                                "sentence_id": sentence_id,
                                "start": start,
                                "end": end,
                            })
                            continue
                        if any(
                            lexical_sentence == sentence_id
                            and start >= lexical_start
                            and end <= lexical_end
                            for lexical_sentence, lexical_start, lexical_end in lexical
                        ):
                            diagnostics.append({
                                "reason": "lexical-expression-not-grammar",
                                "rule_id": rule["id"],
                                "sentence_id": sentence_id,
                                "start": start,
                                "end": end,
                            })
                            continue
                        proposals.append({
                            "rule": rule,
                            "pattern": pattern,
                            "surface": surface,
                            "chapter_id": chapter["id"],
                            "block_id": block["id"],
                            "sentence_id": sentence_id,
                            "sentence_record_id": sentence_id,
                            "sentence_start": start,
                            "sentence_end": end,
                            "block_start": sentence["start"] + start,
                            "block_end": sentence["start"] + end,
                            "tokens": list(component),
                        })

    proposals.sort(key=lambda item: (
        item["chapter_id"], item["block_id"], item["sentence_id"],
        -(item["sentence_end"] - item["sentence_start"]),
        -item["rule"]["priority"], rule_order[item["rule"]["id"]],
        item["sentence_start"],
    ))
    selected: list[dict] = []
    for proposal in proposals:
        conflict = next((
            current for current in selected
            if current["sentence_id"] == proposal["sentence_id"]
            and proposal["sentence_start"] < current["sentence_end"]
            and current["sentence_start"] < proposal["sentence_end"]
        ), None)
        if conflict is not None:
            diagnostics.append({
                "reason": "overlap-rejected-longest-specific-rule",
                "rule_id": proposal["rule"]["id"],
                "sentence_id": proposal["sentence_id"],
                "start": proposal["sentence_start"],
                "end": proposal["sentence_end"],
                "selected_rule_id": conflict["rule"]["id"],
            })
        else:
            selected.append(proposal)

    selected.sort(key=lambda item: (
        item["chapter_id"], item["block_id"], item["sentence_id"], item["sentence_start"],
        item["rule"]["id"],
    ))
    occurrences = []
    grouped: dict[str, list[dict]] = {}
    for number, proposal in enumerate(selected, 1):
        rule = proposal["rule"]
        token_ids = [token["id"] for token in proposal["tokens"]]
        candidate_ids = [
            candidate_id for token_id in token_ids
            for candidate_id in candidates_by_token.get(token_id, [])
        ]
        adjacent_ruby = any(
            proposal["block_start"] == record["end"]
            or proposal["block_end"] == record["start"]
            for record in blocks[proposal["block_id"]].get("publisher_ruby", [])
        )
        occurrence = {
            "id": f"grammar-occurrence-{number:04d}",
            "rule_id": rule["id"],
            "dataset_id": dataset["dataset_id"],
            "dataset_version": dataset["dataset_version"],
            "canonical_key": rule["canonical_key"],
            "surface": proposal["surface"],
            "chapter_id": proposal["chapter_id"],
            "block_id": proposal["block_id"],
            "sentence_id": proposal["sentence_id"],
            "sentence_record_id": proposal["sentence_record_id"],
            "sentence_start": proposal["sentence_start"],
            "sentence_end": proposal["sentence_end"],
            "block_start": proposal["block_start"],
            "block_end": proposal["block_end"],
            "component_token_ids": token_ids,
            "overlapping_candidate_ids": candidate_ids,
            "match_form": proposal["pattern"],
            "confidence": "exact-curated-rule",
            "selection_reason": "longest-exact-then-specific-priority",
            "publisher_ruby_interaction": (
                "adjacent-preserved-publisher-ruby" if adjacent_ruby else "none"
            ),
        }
        occurrence["hash"] = stable_hash(occurrence)
        occurrences.append(occurrence)
        grouped.setdefault(rule["id"], []).append(occurrence)

    candidates = []
    grouped_rules = sorted(
        (rule for rule in dataset["rules"] if grouped.get(rule["id"])),
        key=lambda rule: occurrences.index(grouped[rule["id"]][0]),
    )
    for rule in grouped_rules:
        values = grouped[rule["id"]]
        chapter_counts = []
        for chapter_id in dict.fromkeys(value["chapter_id"] for value in values):
            chapter_counts.append({
                "chapter_id": chapter_id,
                "count": sum(value["chapter_id"] == chapter_id for value in values),
            })
        candidate = {
            "id": f"grammar-candidate-{len(candidates) + 1:04d}",
            "rule_id": rule["id"],
            "canonical_key": rule["canonical_key"],
            "occurrence_ids": [value["id"] for value in values],
            "first_location": {
                "chapter_id": values[0]["chapter_id"],
                "block_id": values[0]["block_id"],
                "sentence_id": values[0]["sentence_id"],
                "sentence_start": values[0]["sentence_start"],
            },
            "last_location": {
                "chapter_id": values[-1]["chapter_id"],
                "block_id": values[-1]["block_id"],
                "sentence_id": values[-1]["sentence_id"],
                "sentence_start": values[-1]["sentence_start"],
            },
            "chapter_counts": chapter_counts,
            "book_count": len(values),
        }
        candidate["hash"] = stable_hash(candidate)
        candidates.append(candidate)

    diagnostics.sort(key=lambda item: (
        item["sentence_id"], item["start"], item["end"], item["rule_id"], item["reason"]
    ))
    for index, diagnostic in enumerate(diagnostics, 1):
        diagnostic["id"] = f"grammar-diagnostic-{index:04d}"
        diagnostic["hash"] = stable_hash(diagnostic)
    report = {
        "schema_version": SCHEMA_VERSION,
        "book_id": book["book_id"],
        "source_book_schema_version": 2,
        "source_vocabulary_schema_version": 4,
        "source_annotation_plan_schema_version": 2,
        "dataset": {
            "id": dataset["dataset_id"],
            "version": dataset["dataset_version"],
            "schema_version": dataset["schema_version"],
            "source_provenance": dataset["source_provenance"],
            "rules": [{"id": rule["id"], "hash": rule["hash"]} for rule in dataset["rules"]],
        },
        "occurrences": occurrences,
        "candidates": candidates,
        "diagnostics": diagnostics,
    }
    validate_grammar_report(book, vocabulary, report)
    return report


def validate_grammar_report(book: dict[str, Any], vocabulary: dict[str, Any], report: dict[str, Any]) -> None:
    required = {
        "schema_version", "book_id", "source_book_schema_version",
        "source_vocabulary_schema_version", "source_annotation_plan_schema_version",
        "dataset", "occurrences", "candidates", "diagnostics",
    }
    if set(report) != required or report.get("schema_version") != SCHEMA_VERSION:
        raise GrammarAnalysisError("Unsupported grammar report schema")
    if report["book_id"] != book.get("book_id") or report["source_vocabulary_schema_version"] != vocabulary.get("schema_version"):
        raise GrammarAnalysisError("Grammar report source mismatch")
    sentence_map = {
        sentence["id"]: (block, sentence)
        for chapter in book["chapters"] for block in chapter["blocks"]
        for sentence in block["sentences"]
    }
    token_map = {token["id"]: token for token in vocabulary["tokens"]}
    candidate_ids = {candidate["id"] for candidate in vocabulary["candidates"]}
    seen: set[str] = set()
    previous = None
    spans: dict[str, list[tuple[int, int]]] = {}
    for index, occurrence in enumerate(report["occurrences"], 1):
        if occurrence["id"] != f"grammar-occurrence-{index:04d}" or occurrence["id"] in seen:
            raise GrammarAnalysisError("Duplicate or unstable occurrence ID")
        seen.add(occurrence["id"])
        body = {key: value for key, value in occurrence.items() if key != "hash"}
        if occurrence["hash"] != stable_hash(body) or occurrence["confidence"] not in CONFIDENCE_VALUES:
            raise GrammarAnalysisError("Invalid occurrence hash or confidence")
        if occurrence["sentence_id"] not in sentence_map:
            raise GrammarAnalysisError("Unknown occurrence sentence")
        block, sentence = sentence_map[occurrence["sentence_id"]]
        start, end = occurrence["sentence_start"], occurrence["sentence_end"]
        if not 0 <= start < end <= len(sentence["text"]) or sentence["text"][start:end] != occurrence["surface"]:
            raise GrammarAnalysisError("Occurrence text or offsets mismatch")
        if occurrence["block_start"] != sentence["start"] + start or occurrence["block_end"] != sentence["start"] + end:
            raise GrammarAnalysisError("Occurrence block offsets mismatch")
        tokens = [token_map.get(token_id) for token_id in occurrence["component_token_ids"]]
        if any(token is None for token in tokens):
            raise GrammarAnalysisError("Unknown component token")
        if "".join(token["surface"] for token in tokens) != occurrence["surface"]:
            raise GrammarAnalysisError("Component token text mismatch")
        if any(token.get("publisher_ruby_id") for token in tokens):
            raise GrammarAnalysisError("Grammar occurrence enters publisher ruby")
        if any(value not in candidate_ids for value in occurrence["overlapping_candidate_ids"]):
            raise GrammarAnalysisError("Unknown overlapping vocabulary candidate")
        order = (occurrence["chapter_id"], occurrence["block_id"], occurrence["sentence_id"], start)
        if previous is not None and order < previous:
            raise GrammarAnalysisError("Unordered grammar occurrences")
        previous = order
        sentence_spans = spans.setdefault(occurrence["sentence_id"], [])
        if any(start < old_end and old_start < end for old_start, old_end in sentence_spans):
            raise GrammarAnalysisError("Overlapping grammar occurrences")
        sentence_spans.append((start, end))
    occurrence_ids = {item["id"] for item in report["occurrences"]}
    for index, candidate in enumerate(report["candidates"], 1):
        if candidate["id"] != f"grammar-candidate-{index:04d}" or candidate["id"] in seen:
            raise GrammarAnalysisError("Duplicate or unstable candidate ID")
        seen.add(candidate["id"])
        if any(value not in occurrence_ids for value in candidate["occurrence_ids"]):
            raise GrammarAnalysisError("Unknown grouped occurrence")
        body = {key: value for key, value in candidate.items() if key != "hash"}
        if candidate["hash"] != stable_hash(body):
            raise GrammarAnalysisError("Invalid candidate hash")
        if sum(value["count"] for value in candidate["chapter_counts"]) != candidate["book_count"]:
            raise GrammarAnalysisError("Incorrect grammar occurrence totals")
    for index, diagnostic in enumerate(report["diagnostics"], 1):
        if diagnostic["id"] != f"grammar-diagnostic-{index:04d}" or diagnostic["id"] in seen:
            raise GrammarAnalysisError("Duplicate or unstable diagnostic ID")
        seen.add(diagnostic["id"])
        body = {key: value for key, value in diagnostic.items() if key != "hash"}
        if diagnostic["hash"] != stable_hash(body):
            raise GrammarAnalysisError("Invalid diagnostic hash")


def safe_detect(
    book: dict[str, Any],
    vocabulary: dict[str, Any],
    plan: dict[str, Any],
    dataset: dict[str, Any] | None,
    *,
    disabled: bool = False,
) -> dict[str, Any]:
    try:
        return detect_grammar(book, vocabulary, plan, dataset, disabled=disabled)
    except (GrammarAnalysisError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        diagnostic = {
            "id": "grammar-diagnostic-0001",
            "reason": "invalid-or-corrupt-input",
        }
        diagnostic["hash"] = stable_hash(diagnostic)
        return {
            "schema_version": SCHEMA_VERSION,
            "book_id": book.get("book_id", "unknown"),
            "source_book_schema_version": book.get("schema_version"),
            "source_vocabulary_schema_version": vocabulary.get("schema_version"),
            "source_annotation_plan_schema_version": plan.get("schema_version"),
            "dataset": None,
            "occurrences": [],
            "candidates": [],
            "diagnostics": [diagnostic],
        }
