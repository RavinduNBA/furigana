"""Lightweight, resilient LLM provider abstractions for context discovery and translation."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """Raised when an LLM provider request fails or returns invalid data."""


@dataclass
class LLMMessage:
    role: str
    content: str


@dataclass
class LLMRequest:
    messages: list[LLMMessage]
    temperature: float = 0.3
    response_json: bool = True
    model: str = "gpt-4o-mini"
    max_tokens: int = 4096


@dataclass
class LLMResponse:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def json_data(self) -> dict[str, Any]:
        try:
            # Strip markdown code blocks if present
            text = self.content.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(f"Failed to parse LLM response as JSON: {exc}\nRaw: {self.content}") from exc


class BaseLLMProvider(ABC):
    """Base interface for all LLM providers."""

    @abstractmethod
    def generate(
        self,
        request: LLMRequest,
        stream_callback: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        """Generate a response from the model."""

    def generate_json(self, request: LLMRequest) -> dict[str, Any]:
        """Generate and parse a JSON response."""
        request.response_json = True
        response = self.generate(request)
        return response.json_data()


class MockLLMProvider(BaseLLMProvider):
    """Deterministic mock provider for offline processing and unit tests."""

    def __init__(self, responses: dict[str, Any] | None = None, default_response: dict[str, Any] | None = None):
        self.responses = responses or {}
        self.default_response = default_response or {"status": "ok"}
        self.call_history: list[LLMRequest] = []

    def generate(
        self,
        request: LLMRequest,
        stream_callback: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        self.call_history.append(request)
        # Search messages for matching key in self.responses
        full_text = " ".join(m.content for m in request.messages)
        matched = None
        for key, res in self.responses.items():
            if key in full_text:
                matched = res
                break
        data = matched if matched is not None else self.default_response
        content_str = json.dumps(data, ensure_ascii=False)
        if stream_callback:
            stream_callback(content_str)
        return LLMResponse(
            content=content_str,
            prompt_tokens=len(full_text) // 4,
            completion_tokens=len(content_str) // 4,
            model="mock-model",
            raw={"mock": True},
        )


class OpenAICompatibleProvider(BaseLLMProvider):
    """Provider for OpenAI, OpenRouter, Ollama, vLLM, DeepSeek, etc."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        default_model: str = "gpt-4o-mini",
        timeout_seconds: int = 60,
        max_retries: int = 3,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def generate(
        self,
        request: LLMRequest,
        stream_callback: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        model = request.model or self.default_model
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_json:
            payload["response_format"] = {"type": "json_object"}
        if stream_callback:
            payload["stream"] = True

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.base_url}/chat/completions"
        data_bytes = json.dumps(payload).encode("utf-8")

        for attempt in range(1, self.max_retries + 1):
            try:
                req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    if stream_callback:
                        accumulated = []
                        for line_bytes in resp:
                            line = line_bytes.decode("utf-8", errors="replace").strip()
                            if not line or line.startswith(":") or line == "data: [DONE]":
                                continue
                            if line.startswith("data: "):
                                chunk_str = line[6:]
                                try:
                                    chunk_json = json.loads(chunk_str)
                                    choices = chunk_json.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {}).get("content", "")
                                        if delta:
                                            accumulated.append(delta)
                                            stream_callback(delta)
                                except Exception:
                                    pass
                        full_content = "".join(accumulated)
                        return LLMResponse(
                            content=full_content,
                            prompt_tokens=0,
                            completion_tokens=len(full_content) // 4,
                            model=model,
                            raw={},
                        )
                    else:
                        resp_body = resp.read().decode("utf-8")
                        result = json.loads(resp_body)
                        choice = result["choices"][0]
                        content = choice["message"]["content"]
                        usage = result.get("usage", {})
                        return LLMResponse(
                            content=content,
                            prompt_tokens=usage.get("prompt_tokens", 0),
                            completion_tokens=usage.get("completion_tokens", 0),
                            model=result.get("model", model),
                            raw=result,
                        )
            except urllib.error.HTTPError as exc:
                err_msg = exc.read().decode("utf-8", errors="replace")
                logger.warning(f"HTTP {exc.code} from LLM provider (attempt {attempt}/{self.max_retries}): {err_msg}")
                if attempt == self.max_retries or exc.code in {400, 401, 403}:
                    raise LLMProviderError(f"LLM API HTTP {exc.code}: {err_msg}") from exc
                time.sleep(2**attempt)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                logger.warning(f"Connection error to LLM provider (attempt {attempt}/{self.max_retries}): {exc}")
                if attempt == self.max_retries:
                    raise LLMProviderError(f"LLM connection error: {exc}") from exc
                time.sleep(2**attempt)

        raise LLMProviderError("Exceeded maximum retries contacting LLM provider")


def get_llm_provider(
    provider_name: str = "mock",
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> BaseLLMProvider:
    """Factory function for instantiating an LLM provider."""
    name = (provider_name or "mock").lower()
    if name == "mock":
        return MockLLMProvider()
    if name in {"openai", "openrouter", "ollama", "vllm", "deepseek", "openai_compatible"}:
        default_url = {
            "openai": "https://api.openai.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "ollama": "http://localhost:11434/v1",
            "deepseek": "https://api.deepseek.com/v1",
        }.get(name, "https://api.openai.com/v1")
        default_model = model
        if not default_model:
            if name == "ollama":
                default_model = "qwen2.5:3b"
            elif name == "openai":
                default_model = "gpt-4o-mini"
            elif name == "deepseek":
                default_model = "deepseek-chat"
            else:
                default_model = "gpt-4o-mini"

        timeout = 240 if name == "ollama" else 90
        return OpenAICompatibleProvider(
            api_key=api_key,
            base_url=base_url or default_url,
            default_model=default_model,
            timeout_seconds=timeout,
        )
    raise ValueError(f"Unsupported LLM provider: {provider_name}")
