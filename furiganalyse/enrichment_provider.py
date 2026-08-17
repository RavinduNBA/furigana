"""Deterministic prompts and an opt-in, transport-injected provider adapter."""

from __future__ import annotations

import importlib
import json
from typing import Any, Protocol

from .enrichment import (
    MAX_AMBIGUITY,
    MAX_MEANING,
    PROMPT_VERSION,
    RESPONSE_SCHEMA_VERSION,
    EnrichmentError,
    _canonical,
    _sha,
    validate_request_report,
)

PROMPT_SCHEMA_VERSION = 1
PROMPT_REPORT_SCHEMA_VERSION = 1
PROVIDER_CONFIG_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_OUTPUT_TOKENS = 300


class ProviderConfigurationError(EnrichmentError):
    """Raised before provider invocation when opt-in configuration is invalid."""


class ProviderTransport(Protocol):
    def create(self, payload: dict[str, Any], api_key: str, timeout: int) -> Any: ...


def _response_contract(request):
    return {
        "additionalProperties": False,
        "required": [
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
        ],
        "type": "object",
        "properties": {
            "schema_version": {"const": RESPONSE_SCHEMA_VERSION},
            "request_id": {"const": request["id"]},
            "item_id": {"const": request["item_id"]},
            "context_hash": {"const": request["context_hash"]},
            "selected_entry_id": {"type": "string"},
            "selected_sense_id": {"type": ["string", "null"]},
            "selected_translation_id": {"type": ["string", "null"]},
            "display_meaning": {"type": "string", "maxLength": MAX_MEANING},
            "ambiguity_note": {
                "type": ["string", "null"],
                "maxLength": MAX_AMBIGUITY,
            },
            "provider_id": {"const": "openai-compatible"},
            "model_id": {"type": "string"},
            "prompt_version": {"const": request["prompt_version"]},
        },
    }


def render_prompt(request):
    content = {
        "schema_version": PROMPT_SCHEMA_VERSION,
        "prompt_version": request["prompt_version"],
        "requested_response_schema_version": request["response_schema_version"],
        "study_item": {
            "request_id": request["id"],
            "item_id": request["item_id"],
            "kind": request["item_kind"],
            "surface": request["surface"],
            "lemma": request["lemma"],
            "normalized_form": request["normalized_form"],
            "authoritative_reading": request["authoritative_reading"],
        },
        "context": request["context"],
        "dictionary": {
            "kind": request["dictionary_kind"],
            "entries": request["dictionary_entries"],
            "provenance": request["dictionary_provenance"],
        },
        "tokenizer_provenance": request["tokenizer_provenance"],
        "precedence": request["precedence"],
        "instructions": [
            "Select exactly one supplied entry and one compatible supplied sense or translation.",
            "Return a short context-sensitive meaning supported by that supplied record.",
            "Keep names as names and preserve the authoritative reading.",
            "Return only the required JSON object; do not return markup or URLs.",
        ],
        "response_contract": _response_contract(request),
    }
    return {
        "schema_version": PROMPT_SCHEMA_VERSION,
        "id": request["id"].replace("enrichment-request", "enrichment-prompt"),
        "request_id": request["id"],
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": _sha(content),
        "content": content,
    }


def build_prompt_report(request_report):
    validate_request_report(request_report)
    prompts = [render_prompt(request) for request in request_report["requests"]]
    return {
        "schema_version": PROMPT_REPORT_SCHEMA_VERSION,
        "book_id": request_report["book_id"],
        "prompts": prompts,
    }


class OpenAICompatibleProvider:
    """Opt-in provider; transport injection keeps tests and core network-free."""

    provider_id = "openai-compatible"
    provider_config_version = PROVIDER_CONFIG_VERSION

    def __init__(
        self,
        *,
        model_id: str,
        api_key: str,
        transport: ProviderTransport,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    ):
        if not isinstance(model_id, str) or not model_id.strip():
            raise ProviderConfigurationError("A model name is required")
        if not isinstance(api_key, str) or not api_key:
            raise ProviderConfigurationError("Provider credentials are required")
        if not 1 <= timeout_seconds <= 120:
            raise ProviderConfigurationError("Unsupported provider timeout")
        if not 64 <= max_output_tokens <= 1000:
            raise ProviderConfigurationError("Unsupported output-token limit")
        if transport is None:
            raise ProviderConfigurationError("A provider transport is required")
        self.model_id = model_id
        self._api_key = api_key
        self._transport = transport
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens

    def prompt_hash_for(self, request):
        return render_prompt(request)["prompt_hash"]

    def enrich(self, request):
        prompt = render_prompt(request)
        payload = {
            "model": self.model_id,
            "input": _canonical(prompt["content"]),
            "max_output_tokens": self.max_output_tokens,
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "name": "furiganalyse_enrichment_response_v1",
                "strict": True,
                "schema": prompt["content"]["response_contract"],
            },
        }
        raw = self._transport.create(payload, self._api_key, self.timeout_seconds)
        if isinstance(raw, dict) and raw.get("refusal"):
            raise EnrichmentError("Provider refusal")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError as error:
                raise EnrichmentError("Malformed provider JSON") from error
        if not isinstance(raw, dict):
            raise EnrichmentError("Provider returned no JSON object")
        return raw


class OpenAISDKTransport:
    """Optional SDK boundary, imported lazily and never used by tests or gates."""

    def create(self, payload, api_key, timeout):
        try:
            module = importlib.import_module("openai")
        except ImportError as error:
            raise ProviderConfigurationError("Optional openai SDK is not installed") from error
        client = module.OpenAI(api_key=api_key, timeout=timeout, max_retries=0)
        sdk_payload = dict(payload)
        sdk_payload["text"] = {"format": sdk_payload.pop("response_format")}
        response = client.responses.create(**sdk_payload)
        if getattr(response, "output_text", None):
            return response.output_text
        raise EnrichmentError("Provider returned no output text")
