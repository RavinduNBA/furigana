"""Deterministic local-context enrichment requests, validation, and fallback."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Protocol

REQUEST_SCHEMA_VERSION = 1
RESPONSE_SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = 1
PROMPT_VERSION = "phase5-local-context-v1"
MAX_MEANING = 120
MAX_AMBIGUITY = 160
UNSAFE_TEXT = re.compile(
    r"[<>]|https?://|javascript:|[\x00-\x08\x0b\x0c\x0e-\x1f]", re.I
)


class EnrichmentError(ValueError):
    """Raised when an enrichment artifact violates its strict schema."""


class EnrichmentProvider(Protocol):
    provider_id: str
    model_id: str

    def enrich(self, request: dict[str, Any]) -> dict[str, Any]: ...


class ScriptedProvider:
    """Local deterministic provider used only by tests and reviewed fixtures."""

    provider_id = "scripted-local"
    model_id = "scripted-v1"

    def __init__(self, responses: dict[str, Any]):
        self.responses = responses
        self.calls: list[str] = []

    def enrich(self, request):
        self.calls.append(request["id"])
        value = self.responses.get(request["id"])
        if isinstance(value, BaseException):
            raise value
        if not isinstance(value, dict):
            raise EnrichmentError("Scripted provider has no object response")
        return value


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _index(values, label):
    result = {}
    for value in values:
        identifier = value.get("id")
        if not identifier or identifier in result:
            raise EnrichmentError(f"Duplicate or missing {label} ID")
        result[identifier] = value
    return result


def build_enrichment_requests(book, vocabulary, plan):
    if (
        book.get("schema_version") != 2
        or vocabulary.get("schema_version") != 4
        or plan.get("schema_version") != 1
    ):
        raise EnrichmentError("Unsupported source schema")
    if len({book.get("book_id"), vocabulary.get("book_id"), plan.get("book_id")}) != 1:
        raise EnrichmentError("Source book identity mismatch")
    blocks = _index([b for c in book["chapters"] for b in c["blocks"]], "block")
    sentences = _index([s for b in blocks.values() for s in b["sentences"]], "sentence")
    matches = {
        value["id"]: value
        for key in (
            "dictionary_matches",
            "expression_dictionary_matches",
            "name_dictionary_matches",
        )
        for value in vocabulary[key]
    }
    requests = []
    for number, item in enumerate(plan["items"], 1):
        primary = item["occurrences"][0]
        block = blocks.get(primary["block_id"])
        if block is None:
            raise EnrichmentError(f"Unknown block: {primary['block_id']}")
        sentence_ids = [s["id"] for s in block["sentences"]]
        try:
            position = sentence_ids.index(primary["sentence_id"])
        except ValueError as error:
            raise EnrichmentError(
                f"Unknown sentence: {primary['sentence_id']}"
            ) from error
        context = [
            {"id": sentence["id"], "text": sentence["text"]}
            for sentence in block["sentences"][max(0, position - 1) : position + 2]
        ]
        if item["kind"] == "vocabulary":
            match_id = f"{primary['candidate_ids'][0]}-jmdict"
            dictionary_kind = "jmdict"
        elif item["kind"] == "expression":
            match_id = f"{primary['expression_id']}-jmdict"
            dictionary_kind = "jmdict"
        else:
            match_id = f"{primary['name_id']}-jmnedict"
            dictionary_kind = "jmnedict"
        match = matches.get(match_id)
        if match is None:
            raise EnrichmentError(f"Unknown dictionary match: {match_id}")
        request = {
            "schema_version": REQUEST_SCHEMA_VERSION,
            "response_schema_version": RESPONSE_SCHEMA_VERSION,
            "prompt_version": PROMPT_VERSION,
            "id": f"enrichment-request-{number:04d}",
            "item_id": item["id"],
            "item_kind": item["kind"],
            "surface": item["surface"],
            "lemma": item.get("lemma"),
            "normalized_form": item.get("normalized_form"),
            "authoritative_reading": item.get("reading"),
            "reading_source": item.get("reading_source"),
            "chapter_id": primary["chapter_id"],
            "block_id": primary["block_id"],
            "sentence_id": primary["sentence_id"],
            "occurrence_ids": [o["id"] for o in item["occurrences"]],
            "token_ids": primary["token_ids"],
            "candidate_ids": primary["candidate_ids"],
            "expression_id": primary.get("expression_id"),
            "name_id": primary.get("name_id"),
            "publisher_ruby_id": primary.get("publisher_ruby_id"),
            "containing_sentence": sentences[primary["sentence_id"]]["text"],
            "context": context,
            "context_hash": _sha(context),
            "dictionary_kind": dictionary_kind,
            "dictionary_entries": match["entries"],
            "dictionary_provenance": plan["name_dictionary"]
            if dictionary_kind == "jmnedict"
            else plan["dictionary"],
            "tokenizer_provenance": plan["tokenizer"],
            "dictionary_only_meaning": item["display_meaning"],
            "precedence": ["publisher", "user", "dictionary", "model"],
        }
        requests.append(request)
    report = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "book_id": book["book_id"],
        "requests": requests,
    }
    validate_request_report(report)
    return report


def validate_request_report(report):
    if (
        set(report) != {"schema_version", "book_id", "requests"}
        or report["schema_version"] != 1
    ):
        raise EnrichmentError("Invalid request report schema")
    ids = set()
    for number, request in enumerate(report["requests"], 1):
        if request["id"] != f"enrichment-request-{number:04d}" or request["id"] in ids:
            raise EnrichmentError("Unstable or duplicate request ID")
        ids.add(request["id"])
        if request["context_hash"] != _sha(request["context"]):
            raise EnrichmentError("Context hash mismatch")
        context_ids = [x["id"] for x in request["context"]]
        if (
            len(context_ids) > 3
            or request["sentence_id"] not in context_ids
            or len(context_ids) != len(set(context_ids))
        ):
            raise EnrichmentError("Invalid bounded context")
        if any(UNSAFE_TEXT.search(x["text"]) for x in request["context"]):
            raise EnrichmentError("Unsafe context text")
        if (
            request["dictionary_kind"] not in {"jmdict", "jmnedict"}
            or not request["dictionary_entries"]
        ):
            raise EnrichmentError("Missing dictionary candidates")
        if request["item_kind"] == "name" and request["dictionary_kind"] != "jmnedict":
            raise EnrichmentError("Name/JMnedict mismatch")
        if request["item_kind"] != "name" and request["dictionary_kind"] != "jmdict":
            raise EnrichmentError("Vocabulary/JMdict mismatch")


def cache_key(request, provider):
    candidates = [
        {
            "entry_id": entry["entry_id"],
            "senses": [s["id"] for s in entry.get("senses", [])],
            "translations": [t["id"] for t in entry.get("translations", [])],
        }
        for entry in request["dictionary_entries"]
    ]
    return _sha(
        {
            "provider": provider.provider_id,
            "model": provider.model_id,
            "prompt_version": request["prompt_version"],
            "response_schema_version": request["response_schema_version"],
            "item_id": request["item_id"],
            "candidates": candidates,
            "context_hash": request["context_hash"],
        }
    )


def validate_response(request, response, provider):
    allowed = {
        "schema_version",
        "request_id",
        "item_id",
        "context_hash",
        "selected_entry_id",
        "selected_sense_id",
        "selected_translation_id",
        "display_meaning",
        "ambiguity_note",
        "provider_id",
        "model_id",
        "prompt_version",
    }
    if set(response) != allowed or response.get("schema_version") != 1:
        raise EnrichmentError("Invalid response schema or unsupported fields")
    expected = {
        "request_id": request["id"],
        "item_id": request["item_id"],
        "context_hash": request["context_hash"],
        "provider_id": provider.provider_id,
        "model_id": provider.model_id,
        "prompt_version": request["prompt_version"],
    }
    if any(response.get(k) != v for k, v in expected.items()):
        raise EnrichmentError("Response identity or provenance mismatch")
    entries = {e["entry_id"]: e for e in request["dictionary_entries"]}
    entry = entries.get(response["selected_entry_id"])
    if entry is None:
        raise EnrichmentError("Response selected an unsupplied entry")
    if request["dictionary_kind"] == "jmnedict":
        valid = {x["id"] for x in entry.get("translations", [])}
        if (
            response["selected_translation_id"] not in valid
            or response["selected_sense_id"] is not None
        ):
            raise EnrichmentError("Invalid JMnedict translation")
    else:
        valid = {x["id"] for x in entry.get("senses", [])}
        if (
            response["selected_sense_id"] not in valid
            or response["selected_translation_id"] is not None
        ):
            raise EnrichmentError("Invalid JMdict sense")
    for field, limit, required in (
        ("display_meaning", MAX_MEANING, True),
        ("ambiguity_note", MAX_AMBIGUITY, False),
    ):
        value = response.get(field)
        if required and (not isinstance(value, str) or not value.strip()):
            raise EnrichmentError(f"Missing {field}")
        if value is not None and (
            not isinstance(value, str)
            or len(value) > limit
            or UNSAFE_TEXT.search(value)
        ):
            raise EnrichmentError(f"Unsafe or overlong {field}")
    return response


def _cache_path(cache_dir, key):
    return Path(cache_dir) / f"{key}.json"


def _write_cache(path, key, response):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(
            {"cache_key": key, "response": response},
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def enrich_requests(request_report, provider=None, cache_dir=None):
    validate_request_report(request_report)
    results, diagnostics = [], []
    for request in request_report["requests"]:
        base = {
            "request_id": request["id"],
            "item_id": request["item_id"],
            "display_meaning": request["dictionary_only_meaning"],
            "source": "dictionary",
            "cache": "disabled",
            "selected_entry_id": None,
            "selected_sense_id": None,
            "selected_translation_id": None,
        }
        if provider is None or cache_dir is None:
            results.append(base)
            continue
        key = cache_key(request, provider)
        path = _cache_path(cache_dir, key)
        try:
            if path.exists():
                record = json.loads(path.read_text(encoding="utf-8"))
                if record.get("cache_key") != key:
                    raise EnrichmentError("Cache key mismatch")
                response = validate_response(request, record.get("response"), provider)
                source = "cache"
                cache = "hit"
            else:
                response = validate_response(
                    request, provider.enrich(request), provider
                )
                _write_cache(path, key, response)
                source = "model"
                cache = "miss"
            results.append(
                {
                    "request_id": request["id"],
                    "item_id": request["item_id"],
                    "display_meaning": response["display_meaning"],
                    "source": source,
                    "cache": cache,
                    "cache_key": key,
                    "selected_entry_id": response["selected_entry_id"],
                    "selected_sense_id": response["selected_sense_id"],
                    "selected_translation_id": response["selected_translation_id"],
                    "ambiguity_note": response["ambiguity_note"],
                    "provider_id": provider.provider_id,
                    "model_id": provider.model_id,
                }
            )
        except Exception as error:
            diagnostics.append(
                {
                    "id": f"enrichment-diagnostic-{len(diagnostics)+1:04d}",
                    "request_id": request["id"],
                    "reason": type(error).__name__,
                }
            )
            base["cache"] = "error"
            results.append(base)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "book_id": request_report["book_id"],
        "results": results,
        "diagnostics": diagnostics,
    }


def serialize(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
