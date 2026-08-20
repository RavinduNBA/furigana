#!/usr/bin/env python3
"""Build deterministic canonical/vocabulary/plan inputs from the legal Phase 7 fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build(spec):
    chapters = []
    tokens = []
    candidates = []
    expressions = []
    for chapter_index, chapter_spec in enumerate(spec["chapters"], 1):
        blocks = []
        chapter_text = []
        for block_index, block_spec in enumerate(chapter_spec["blocks"], 1):
            block_id = f"ch-{chapter_index:04d}-b-{block_index:04d}"
            sentence_id = f"{block_id}-s-0001"
            text = block_spec["text"]
            ruby_records = []
            for ruby_index, ruby_spec in enumerate(block_spec.get("publisher_ruby", []), 1):
                ruby_records.append({
                    "id": f"{block_id}-r-{ruby_index:04d}",
                    "surface": ruby_spec["surface"],
                    "reading": ruby_spec["reading"],
                    "source": "publisher",
                    "start": ruby_spec["start"],
                    "end": ruby_spec["end"],
                    "source_anchor": f"publisher-ruby-{chapter_index}-{block_index}-{ruby_index}",
                })
            blocks.append({
                "id": block_id,
                "text": text,
                "source_anchor": f"grammar-block-{chapter_index}-{block_index}",
                "publisher_ruby": ruby_records,
                "sentences": [{
                    "id": sentence_id,
                    "text": text,
                    "start": 0,
                    "end": len(text),
                    "text_spans": [],
                    "publisher_ruby": [ruby["id"] for ruby in ruby_records],
                }],
            })
            chapter_text.append(text)
            cursor = 0
            sentence_token_ids = []
            sentence_candidate_ids = []
            for token_index, surface in enumerate(block_spec["tokens"], 1):
                start = text.index(surface, cursor)
                end = start + len(surface)
                cursor = end
                token_id = f"{sentence_id}-tok-{token_index:04d}"
                ruby_id = next((
                    ruby["id"] for ruby in ruby_records
                    if start >= ruby["start"] and end <= ruby["end"]
                ), None)
                token = {
                    "id": token_id,
                    "surface": surface,
                    "lemma": surface,
                    "reading": None,
                    "part_of_speech": "synthetic",
                    "chapter_id": chapter_spec["id"],
                    "block_id": block_id,
                    "sentence_id": sentence_id,
                    "sentence_start": start,
                    "sentence_end": end,
                    "block_start": start,
                    "block_end": end,
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
            if block_spec.get("lexical_expression"):
                surface = block_spec["lexical_expression"]
                expressions.append({
                    "id": f"{sentence_id}-expr-0001",
                    "surface": surface,
                    "normalized_form": surface,
                    "token_ids": sentence_token_ids[:-1],
                    "candidate_ids": sentence_candidate_ids,
                    "chapter_id": chapter_spec["id"],
                    "block_id": block_id,
                    "sentence_id": sentence_id,
                    "sentence_start": 0,
                    "sentence_end": len(surface),
                    "block_start": 0,
                    "block_end": len(surface),
                })
        chapters.append({
            "id": chapter_spec["id"],
            "spine_index": chapter_index - 1,
            "source_path": chapter_spec["source_path"],
            "text": "\n".join(chapter_text),
            "blocks": blocks,
        })
    tokenizer = {
        "name": "synthetic-tokenizer",
        "version": "1",
        "wrapper": "phase7-fixture-builder",
        "wrapper_version": "1",
        "dictionary": "synthetic",
        "dictionary_version": "1",
    }
    book = {"schema_version": 2, "book_id": spec["book_id"], "package_path": "EPUB/package.opf", "chapters": chapters}
    vocabulary = {
        "schema_version": 4,
        "book_id": spec["book_id"],
        "source_book_schema_version": 2,
        "tokenizer": tokenizer,
        "tokens": tokens,
        "candidates": candidates,
        "dictionary": None,
        "dictionary_matches": [],
        "expressions": expressions,
        "expression_dictionary_matches": [],
        "name_dictionary": {
            "dataset_id": "synthetic-empty-jmnedict",
            "dataset_version": "1",
            "format_version": 1,
            "sha256": "0" * 64,
        },
        "name_occurrences": [],
        "name_dictionary_matches": [],
        "name_diagnostics": [],
    }
    def study_occurrence(item_number, occurrence_number, block_number, start, end, token_numbers, *, publisher=False):
        sentence_id = f"ch-0001-b-{block_number:04d}-s-0001"
        token_ids = [f"{sentence_id}-tok-{number:04d}" for number in token_numbers]
        return {
            "id": f"study-item-{item_number:04d}-occ-{occurrence_number:04d}",
            "occurrence_number": occurrence_number,
            "chapter_id": "ch-0001",
            "block_id": f"ch-0001-b-{block_number:04d}",
            "sentence_id": sentence_id,
            "sentence_start": start,
            "sentence_end": end,
            "block_start": start,
            "block_end": end,
            "token_ids": token_ids,
            "candidate_ids": [f"{token_id}-cand" for token_id in token_ids],
            "expression_id": None,
            "name_id": None,
            "publisher_ruby_id": (
                f"ch-0001-b-{block_number:04d}-r-0001" if publisher else None
            ),
            "source_anchor_id": f"src-study-item-{item_number:04d}-occ-{occurrence_number:04d}",
            "annotation_target": "preserved_publisher_ruby" if publisher else "text",
        }

    plan_items = [
        {
            "id": "study-item-0001",
            "kind": "vocabulary",
            "surface": "読ん",
            "note_anchor_id": "note-study-item-0001",
            "occurrences": [study_occurrence(1, 1, 1, 2, 4, [3])],
        },
        {
            "id": "study-item-0002",
            "kind": "expression",
            "surface": "忘れてしまう",
            "note_anchor_id": "note-study-item-0002",
            "occurrences": [study_occurrence(2, 1, 4, 0, 6, [1, 2, 3])],
        },
        {
            "id": "study-item-0003",
            "kind": "vocabulary",
            "surface": "毎日読む",
            "note_anchor_id": "note-study-item-0003",
            "occurrences": [study_occurrence(3, 1, 3, 0, 4, [1, 2])],
        },
        {
            "id": "study-item-0004",
            "kind": "vocabulary",
            "surface": "表舞台",
            "note_anchor_id": "note-study-item-0004",
            "occurrences": [study_occurrence(4, 1, 8, 0, 3, [1], publisher=True)],
        },
        {
            "id": "study-item-0005",
            "kind": "name",
            "surface": "前",
            "note_anchor_id": "note-study-item-0005",
            "occurrences": [study_occurrence(5, 1, 2, 0, 1, [1])],
        },
    ]
    plan = {
        "schema_version": 2,
        "source_annotation_plan_schema_version": 1,
        "source_report_schema_version": 4,
        "book_id": spec["book_id"],
        "config": {"per_chapter_limit": 0},
        "items": plan_items,
        "diagnostics": [],
        "enrichments": [],
        "enrichment_diagnostics": [],
    }
    return book, vocabulary, plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    book, vocabulary, plan = build(spec)
    output = Path(args.output_dir)
    _write(output / "book.json", book)
    _write(output / "vocabulary.json", vocabulary)
    _write(output / "annotation-plan.json", plan)


if __name__ == "__main__":
    main()
