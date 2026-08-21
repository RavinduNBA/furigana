#!/usr/bin/env python3
"""Build deterministic synthetic Phase 7 evaluation inputs and ground truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from furiganalyse.grammar_analysis import detect_grammar, load_json
from furiganalyse.grammar_evaluation import prepare_corpus, stable_hash


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_inputs(spec: dict) -> tuple[dict, dict, dict, list[dict]]:
    chapters = []
    tokens = []
    candidates = []
    expressions = []
    case_sources = []
    for chapter_number, chapter_spec in enumerate(spec["chapters"], 1):
        blocks = []
        chapter_text = []
        for block_number, block_spec in enumerate(chapter_spec["blocks"], 1):
            block_id = f"eval-ch-{chapter_number:04d}-b-{block_number:04d}"
            sentence_values = []
            block_text = "".join(value["text"] for value in block_spec["sentences"])
            ruby_values = []
            for ruby_number, source in enumerate(block_spec.get("publisher_ruby", []), 1):
                ruby_values.append({
                    "id": f"{block_id}-r-{ruby_number:04d}", "surface": source["surface"],
                    "reading": source["reading"], "source": "publisher",
                    "start": source["start"], "end": source["end"],
                    "source_anchor": f"evaluation-ruby-{chapter_number}-{block_number}-{ruby_number}",
                })
            sentence_cursor = 0
            expression_sentence = None
            for sentence_number, sentence_spec in enumerate(block_spec["sentences"], 1):
                sentence_id = f"{block_id}-s-{sentence_number:04d}"
                text = sentence_spec["text"]
                sentence_values.append({
                    "id": sentence_id, "text": text, "start": sentence_cursor,
                    "end": sentence_cursor + len(text), "text_spans": [],
                    "publisher_ruby": [
                        value["id"] for value in ruby_values
                        if value["start"] < sentence_cursor + len(text) and sentence_cursor < value["end"]
                    ],
                })
                token_cursor = 0
                sentence_token_ids = []
                sentence_candidate_ids = []
                for token_number, surface in enumerate(sentence_spec["tokens"], 1):
                    start = text.index(surface, token_cursor)
                    end = start + len(surface)
                    token_cursor = end
                    token_id = f"{sentence_id}-tok-{token_number:04d}"
                    block_start = sentence_cursor + start
                    block_end = sentence_cursor + end
                    ruby_id = next((
                        value["id"] for value in ruby_values
                        if block_start >= value["start"] and block_end <= value["end"]
                    ), None)
                    token = {
                        "id": token_id, "surface": surface, "lemma": surface,
                        "reading": None, "part_of_speech": "synthetic",
                        "chapter_id": chapter_spec["id"], "block_id": block_id,
                        "sentence_id": sentence_id, "sentence_start": start,
                        "sentence_end": end, "block_start": block_start,
                        "block_end": block_end,
                        "reading_source": "publisher" if ruby_id else "synthetic-tokenizer",
                        "publisher_ruby_id": ruby_id,
                    }
                    tokens.append(token)
                    sentence_token_ids.append(token_id)
                    if surface not in {"。", "、"}:
                        candidate = dict(token)
                        candidate["id"] = f"{token_id}-cand"
                        candidate["token_id"] = token_id
                        candidates.append(candidate)
                        sentence_candidate_ids.append(candidate["id"])
                for ordinal, case in enumerate(sentence_spec.get("cases", []), 1):
                    case_sources.append((chapter_number, block_number, sentence_number, ordinal, {
                        **case, "chapter_id": chapter_spec["id"], "block_id": block_id,
                        "sentence_id": sentence_id, "sentence_text": text,
                        "sentence_block_start": sentence_cursor,
                        "sentence_token_ids": sentence_token_ids,
                        "publisher_ruby_ids": [value["id"] for value in ruby_values],
                    }))
                if block_spec.get("lexical_expression") and sentence_number == 1:
                    expression_sentence = (
                        sentence_id, sentence_token_ids, sentence_candidate_ids,
                        block_spec["lexical_expression"], sentence_cursor,
                    )
                sentence_cursor += len(text)
            if expression_sentence:
                sentence_id, token_ids, candidate_ids, surface, block_start = expression_sentence
                expressions.append({
                    "id": f"{sentence_id}-expr-0001", "surface": surface,
                    "normalized_form": surface, "token_ids": token_ids[:-1],
                    "candidate_ids": candidate_ids, "chapter_id": chapter_spec["id"],
                    "block_id": block_id, "sentence_id": sentence_id,
                    "sentence_start": 0, "sentence_end": len(surface),
                    "block_start": block_start, "block_end": block_start + len(surface),
                })
            blocks.append({
                "id": block_id, "text": block_text,
                "source_anchor": f"evaluation-block-{chapter_number}-{block_number}",
                "publisher_ruby": ruby_values, "sentences": sentence_values,
            })
            chapter_text.append(block_text)
        chapters.append({
            "id": chapter_spec["id"], "spine_index": chapter_number - 1,
            "source_path": chapter_spec["source_path"], "text": "\n".join(chapter_text),
            "blocks": blocks,
        })
    tokenizer = {
        "name": "synthetic-tokenizer", "version": "1",
        "wrapper": "phase7-evaluation-fixture-builder", "wrapper_version": "1",
        "dictionary": "synthetic", "dictionary_version": "1",
    }
    book = {
        "schema_version": 2, "book_id": spec["book_id"],
        "package_path": "EPUB/package.opf", "chapters": chapters,
    }
    vocabulary = {
        "schema_version": 4, "book_id": spec["book_id"],
        "source_book_schema_version": 2, "tokenizer": tokenizer,
        "tokens": tokens, "candidates": candidates, "dictionary": None,
        "dictionary_matches": [], "expressions": expressions,
        "expression_dictionary_matches": [],
        "name_dictionary": {
            "dataset_id": "synthetic-empty-jmnedict", "dataset_version": "1",
            "format_version": 1, "sha256": "0" * 64,
        },
        "name_occurrences": [], "name_dictionary_matches": [], "name_diagnostics": [],
    }
    plan = {
        "schema_version": 2, "source_annotation_plan_schema_version": 1,
        "source_report_schema_version": 4, "book_id": spec["book_id"],
        "config": {"per_chapter_limit": 0}, "items": [], "diagnostics": [],
        "enrichments": [], "enrichment_diagnostics": [],
    }
    return book, vocabulary, plan, case_sources


def build_corpus(
    spec: dict, book: dict, vocabulary: dict, plan: dict, report: dict,
    dataset: dict, case_sources: list[dict],
) -> dict:
    rules = {rule["id"]: rule for rule in dataset["rules"]}
    token_map = {token["id"]: token for token in vocabulary["tokens"]}
    cases = []
    for _chapter, _block, _sentence, _ordinal, source in sorted(case_sources):
        surface = source.get("surface")
        start = source["sentence_text"].index(surface) if surface is not None else 0
        end = start + len(surface) if surface is not None else 0
        token_ids = [
            token_id for token_id in source["sentence_token_ids"]
            if token_map[token_id]["sentence_start"] < end and start < token_map[token_id]["sentence_end"]
        ] if surface is not None else []
        rule = rules.get(source.get("rule_id"))
        case = {
            "id": f"grammar-eval-case-{len(cases) + 1:04d}",
            "kind": source["kind"],
            "category": source.get("category", "primary-curated-positive"),
            "rule_id": source.get("rule_id"),
            "canonical_key": rule["canonical_key"] if rule else None,
            "surface": surface, "chapter_id": source["chapter_id"],
            "block_id": source["block_id"], "sentence_id": source["sentence_id"],
            "token_ids": token_ids, "sentence_start": start, "sentence_end": end,
            "block_start": source["sentence_block_start"] + start,
            "block_end": source["sentence_block_start"] + end,
            "expected_confidence": "exact-curated-rule" if source["kind"] == "positive" else None,
            "expected_selection_reason": "longest-exact-then-specific-priority" if source["kind"] == "positive" else None,
            "publisher_ruby_interaction": (
                "publisher-ruby-protected" if source.get("category") == "publisher-ruby-covered"
                else "none"
            ),
            "expected_nonmatch_reason": source.get("expected_nonmatch_reason"),
            "publisher_ruby_ids": source["publisher_ruby_ids"],
            "hash": "",
        }
        cases.append(case)
    corpus = {
        "schema_version": 1, "id": "furiganalyse-synthetic-grammar-evaluation",
        "version": spec["version"], "fixture_notice": spec["fixture_notice"],
        "book_id": spec["book_id"],
        "source_hashes": {
            "canonical_book": stable_hash(book), "vocabulary_report": stable_hash(vocabulary),
            "annotation_plan": stable_hash(plan), "grammar_report": stable_hash(report),
            "grammar_dataset": stable_hash(dataset),
        },
        "cases": cases, "hash": "",
    }
    return prepare_corpus(corpus)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--corpus-output")
    args = parser.parse_args()
    spec = load_json(args.source)
    dataset = load_json(args.dataset)
    book, vocabulary, plan, case_sources = build_inputs(spec)
    report = detect_grammar(book, vocabulary, plan, dataset)
    output = Path(args.output_dir)
    for name, value in (
        ("book.json", book), ("vocabulary.json", vocabulary),
        ("annotation-plan.json", plan), ("grammar.json", report),
    ):
        _write(output / name, value)
    corpus = build_corpus(spec, book, vocabulary, plan, report, dataset, case_sources)
    _write(Path(args.corpus_output) if args.corpus_output else output / "corpus.json", corpus)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
