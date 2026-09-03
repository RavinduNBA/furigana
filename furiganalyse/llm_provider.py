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
from pathlib import Path
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


def log_llm_debug(
    provider_name: str,
    model: str,
    request: LLMRequest,
    response: LLMResponse | None = None,
    error: Exception | str | None = None,
    elapsed: float = 0.0,
    extra_path: Path | None = None,
) -> None:
    """Record LLM prompt, context, and response to a local debug log file (not exposed to web UI)."""
    try:
        targets: list[Path] = [Path("data/llm_debug.log"), Path("/root/furiganalyse/data/llm_debug.log")]
        if extra_path:
            targets.append(extra_path if extra_path.suffix == ".log" else extra_path / "llm_debug.log")

        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        lines = [
            "=" * 80,
            f"TIMESTAMP: {ts} | PROVIDER: {provider_name} | MODEL: {model} | ELAPSED: {elapsed:.2f}s",
            "PROMPT MESSAGES:",
        ]
        for m in request.messages:
            lines.append(f"[{m.role.upper()}]:\n{m.content}\n")
        if response:
            lines.append(f"RESPONSE (prompt_tokens={response.prompt_tokens}, completion_tokens={response.completion_tokens}):")
            lines.append(f"{response.content}\n")
        if error:
            lines.append(f"API ERROR / EXCEPTION:\n{error}\n")
        lines.append("=" * 80 + "\n")
        payload = "\n".join(lines)

        for tgt in targets:
            try:
                tgt.parent.mkdir(parents=True, exist_ok=True)
                with open(tgt, "a", encoding="utf-8") as f:
                    f.write(payload)
            except Exception:
                pass
    except Exception as exc:
        logger.debug("Failed writing to llm_debug.log: %s", exc)


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
    """Provider for OpenAI, OpenRouter, Ollama, vLLM, DeepSeek, Hetzner, Alibaba, etc."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        default_model: str = "gpt-4o-mini",
        timeout_seconds: int = 180,
        max_retries: int = 2,
        provider_name: str = "openai_compatible",
        debug_log_path: Path | None = None,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        raw_url = (base_url or "https://api.openai.com/v1").strip().rstrip("/")
        if not (raw_url.startswith("http://") or raw_url.startswith("https://")):
            raw_url = "https://" + raw_url
        self.base_url = raw_url
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.provider_name = provider_name
        self.debug_log_path = debug_log_path

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
            start_time = time.time()
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
                        elapsed = time.time() - start_time
                        logger.info(
                            "LLM stream [%s] finished in %.1fs (%d chars)",
                            model,
                            elapsed,
                            len(full_content),
                        )
                        return LLMResponse(
                            content=full_content,
                            prompt_tokens=0,
                            completion_tokens=len(full_content) // 4,
                            model=model,
                            raw={},
                        )
                    else:
                        resp_body = resp.read().decode("utf-8")
                        elapsed = time.time() - start_time
                        result = json.loads(resp_body)
                        choice = result["choices"][0]
                        msg = choice.get("message", {})
                        content = msg.get("content")
                        if content is None:
                            content = msg.get("text") or msg.get("reasoning") or ""
                        usage = result.get("usage", {})
                        p_tok = usage.get("prompt_tokens", 0)
                        c_tok = usage.get("completion_tokens", 0)
                        logger.info(
                            "LLM [%s] response received in %.1fs (Prompt: %d tokens, Completion: %d tokens, Output: %d chars):\n%s",
                            model,
                            elapsed,
                            p_tok,
                            c_tok,
                            len(content),
                            content,
                        )
                        resp_obj = LLMResponse(
                            content=content,
                            prompt_tokens=p_tok,
                            completion_tokens=c_tok,
                            model=result.get("model", model),
                            raw=result,
                        )
                        log_llm_debug(self.provider_name, model, request, response=resp_obj, elapsed=elapsed, extra_path=self.debug_log_path)
                        return resp_obj
            except urllib.error.HTTPError as exc:
                elapsed = time.time() - start_time
                err_msg = exc.read().decode("utf-8", errors="replace")
                logger.warning(
                    "HTTP %d from LLM provider [%s] after %.1fs (attempt %d/%d): %s",
                    exc.code,
                    model,
                    elapsed,
                    attempt,
                    self.max_retries,
                    err_msg,
                )
                log_llm_debug(self.provider_name, model, request, error=f"HTTP {exc.code}: {err_msg}", elapsed=elapsed, extra_path=self.debug_log_path)
                # Auto-fallback to verified working default models on 404 (endpoint not found / deprecated) or 402
                if exc.code in {402, 404} and attempt < self.max_retries:
                    if "openrouter.ai" in self.base_url and model != "nvidia/nemotron-3.5-lightning:free":
                        logger.info("OpenRouter model [%s] returned HTTP %d. Auto-switching to fallback default: nvidia/nemotron-3.5-lightning:free", model, exc.code)
                        model = "nvidia/nemotron-3.5-lightning:free"
                        time.sleep(0.5)
                        continue
                    elif "generativelanguage.googleapis.com" in self.base_url and model != "gemini-flash-latest":
                        logger.info("Google AI Studio model [%s] returned HTTP %d. Auto-switching to fallback default: gemini-flash-latest", model, exc.code)
                        model = "gemini-flash-latest"
                        time.sleep(0.5)
                        continue

                if attempt == self.max_retries or exc.code in {400, 401, 403, 404, 429}:
                    raise LLMProviderError(f"LLM API HTTP {exc.code} from {self.provider_name} ({model}): {err_msg}") from exc
                time.sleep(1)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                elapsed = time.time() - start_time
                logger.warning(
                    "Connection/timeout error to LLM [%s] after %.1fs (attempt %d/%d): %s",
                    model,
                    elapsed,
                    attempt,
                    self.max_retries,
                    exc,
                )
                log_llm_debug(self.provider_name, model, request, error=f"Connection/Timeout: {exc}", elapsed=elapsed, extra_path=self.debug_log_path)
                if attempt == self.max_retries:
                    raise LLMProviderError(f"LLM connection error after {elapsed:.1f}s from {self.provider_name} ({model}): {exc}") from exc
                time.sleep(2**attempt)

        raise LLMProviderError(f"Exceeded maximum retries contacting LLM provider {self.provider_name} ({model})")


class ResilientFallbackProvider(BaseLLMProvider):
    """Orchestrates an ordered chain of LLM providers with automatic failure fallback and live progress logging."""

    def __init__(
        self,
        primary_provider: BaseLLMProvider,
        primary_name: str,
        fallback_providers: list[tuple[BaseLLMProvider, str, str | None]] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        debug_log_path: Path | None = None,
    ):
        self.primary_provider = primary_provider
        self.primary_name = primary_name
        self.fallback_providers = fallback_providers or []
        self.progress_callback = progress_callback
        self.debug_log_path = debug_log_path

    @property
    def base_url(self) -> str:
        return getattr(self.primary_provider, "base_url", "")

    @property
    def default_model(self) -> str:
        return getattr(self.primary_provider, "default_model", "")

    @property
    def api_key(self) -> str:
        return getattr(self.primary_provider, "api_key", "")

    def generate(
        self,
        request: LLMRequest,
        stream_callback: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        candidates: list[tuple[BaseLLMProvider, str, str | None]] = [
            (self.primary_provider, self.primary_name, getattr(self.primary_provider, "default_model", None))
        ]
        for f_prov, f_name, f_model in self.fallback_providers:
            candidates.append((f_prov, f_name, f_model))

        errors: list[str] = []
        for idx, (prov, name, model_slug) in enumerate(candidates):
            is_fallback = idx > 0
            req_to_use = request
            if model_slug and req_to_use.model != model_slug:
                req_to_use = LLMRequest(
                    messages=request.messages,
                    temperature=request.temperature,
                    response_json=request.response_json,
                    model=model_slug,
                    max_tokens=request.max_tokens,
                )

            try:
                if is_fallback and self.progress_callback:
                    self.progress_callback({
                        "log": f"[LLM] Dynamic Fallback: attempting service '{name}' ({req_to_use.model})…",
                    })
                resp = prov.generate(req_to_use, stream_callback=stream_callback)
                if is_fallback and self.progress_callback:
                    self.progress_callback({
                        "log": f"[LLM] Fallback to service '{name}' ({req_to_use.model}) succeeded!",
                    })
                return resp
            except Exception as exc:
                err_summary = str(exc)
                errors.append(f"{name} ({req_to_use.model}): {err_summary}")
                logger.warning("Provider '%s' (%s) failed: %s", name, req_to_use.model, err_summary)

                if self.progress_callback:
                    if idx + 1 < len(candidates):
                        next_name, next_model = candidates[idx + 1][1], candidates[idx + 1][2]
                        self.progress_callback({
                            "log": f"[LLM API Error] {name} ({req_to_use.model}) failed ({err_summary[:160]}). Dynamically switching to '{next_name}' ({next_model})…",
                        })
                    else:
                        self.progress_callback({
                            "log": f"[LLM API Error] {name} ({req_to_use.model}) failed ({err_summary[:160]}). All fallback providers exhausted.",
                        })

        all_errs = "; ".join(errors)
        raise LLMProviderError(f"All LLM providers in fallback chain failed: {all_errs}")


def _resolve_alibaba_credentials() -> tuple[str | None, str | None]:
    """Discover Alibaba Cloud Model Studio (DashScope / MaaS) credentials from environment or CSV token files."""
    env_key = os.environ.get("ALIBABA_API_KEY") or os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("ALIYUN_API_KEY")
    env_url = os.environ.get("ALIBABA_BASE_URL") or os.environ.get("DASHSCOPE_BASE_URL")
    if env_key and env_key.strip():
        return env_key.strip(), env_url.strip() if env_url else None

    search_dirs = [
        Path("/root/furiganalyse/api_tokens"),
        Path("api_tokens"),
        Path("/root/furiganalyse"),
        Path("."),
    ]
    for d in search_dirs:
        if d.is_dir():
            for p in sorted(d.glob("*.csv")):
                try:
                    lines = p.read_text(encoding="utf-8").splitlines()
                    data = {}
                    for line in lines:
                        parts = line.strip().split(",", 1)
                        if len(parts) == 2:
                            data[parts[0].strip()] = parts[1].strip()
                    if "apiKey" in data:
                        return data["apiKey"], data.get("openAiCompatible")
                except Exception:
                    pass
    return None, None


def resolve_provider_api_key(provider_name: str, explicit_key: str | None = None) -> str | None:
    """Resolve API key from explicit argument, environment variables, or local key files."""
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()

    prov = provider_name.lower()
    if prov in {"google", "gemini"}:
        env_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if env_key and env_key.strip():
            return env_key.strip()
        for fpath in (
            "/root/furiganalyse/api_tokens/googleaistidioapi.txt",
            "/root/furiganalyse/googleaistidioapi.txt",
            "api_tokens/googleaistidioapi.txt",
            "googleaistidioapi.txt",
        ):
            try:
                p = Path(fpath)
                if p.is_file():
                    content = p.read_text(encoding="utf-8").strip()
                    if content:
                        return content
            except Exception:
                pass

    elif prov == "openrouter":
        env_key = os.environ.get("OPENROUTER_API_KEY")
        if env_key and env_key.strip():
            return env_key.strip()
        for fpath in (
            "/root/furiganalyse/api_tokens/openrouterapi.txt",
            "/root/furiganalyse/openrouterapi.txt",
            "api_tokens/openrouterapi.txt",
            "openrouterapi.txt",
        ):
            try:
                p = Path(fpath)
                if p.is_file():
                    content = p.read_text(encoding="utf-8").strip()
                    if content:
                        return content
            except Exception:
                pass

    elif prov in {"alibaba", "dashscope", "aliyun", "qwen"}:
        key, _ = _resolve_alibaba_credentials()
        if key:
            return key

    elif prov == "hetzner":
        env_key = os.environ.get("HETZNER_API_KEY")
        if env_key and env_key.strip():
            return env_key.strip()

    elif prov == "openai":
        env_key = os.environ.get("OPENAI_API_KEY")
        if env_key and env_key.strip():
            return env_key.strip()

    elif prov == "deepseek":
        env_key = os.environ.get("DEEPSEEK_API_KEY")
        if env_key and env_key.strip():
            return env_key.strip()

    return None


def get_llm_provider(
    provider_name: str = "mock",
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    auto_fallback: bool = False,
    debug_log_path: Path | None = None,
) -> BaseLLMProvider:
    """Factory function for instantiating an LLM provider with optional resilient multi-provider fallback."""
    name = (provider_name or "mock").lower()
    if name == "mock":
        return MockLLMProvider()

    resolved_key = resolve_provider_api_key(name, api_key)

    if name in {"openai", "openrouter", "ollama", "vllm", "deepseek", "hetzner", "google", "gemini", "alibaba", "dashscope", "aliyun", "qwen", "openai_compatible"}:
        ali_key, ali_url = _resolve_alibaba_credentials()
        if name in {"alibaba", "dashscope", "aliyun", "qwen"}:
            resolved_key = resolved_key or ali_key

        default_url = {
            "openai": "https://api.openai.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "ollama": "http://localhost:11434/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "hetzner": "https://inference.hetzner.com/api/v1",
            "google": "https://generativelanguage.googleapis.com/v1beta/openai",
            "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
            "alibaba": ali_url or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            "dashscope": ali_url or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            "aliyun": ali_url or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            "qwen": ali_url or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        }.get(name, "https://api.openai.com/v1")

        default_model = model
        if not default_model:
            if name == "ollama":
                default_model = "qwen2.5:3b"
            elif name == "hetzner":
                default_model = "Qwen/Qwen3.6-35B-A3B-FP8"
            elif name in {"google", "gemini"}:
                default_model = "gemini-flash-latest"
            elif name in {"alibaba", "dashscope", "aliyun", "qwen"}:
                default_model = "qwen-plus-character"
            elif name == "openrouter":
                default_model = "nvidia/nemotron-3.5-lightning:free"
            elif name == "deepseek":
                default_model = "deepseek-chat"
            else:
                default_model = "gpt-4o-mini"

        timeout = 180
        retries = 2
        primary = OpenAICompatibleProvider(
            api_key=resolved_key,
            base_url=base_url or default_url,
            default_model=default_model,
            timeout_seconds=timeout,
            max_retries=retries,
            provider_name=name,
            debug_log_path=debug_log_path,
        )

        if not auto_fallback:
            return primary

        # Build fallback list for alternative configured providers
        fallbacks: list[tuple[BaseLLMProvider, str, str | None]] = []

        # 0. Alibaba secondary model fallback (if alibaba is primary, fallback to flash-character or vice-versa)
        if name in {"alibaba", "dashscope", "aliyun", "qwen"} and ali_key:
            alt_ali_model = "qwen-flash-character" if default_model == "qwen-plus-character" else "qwen-plus-character"
            alt_ali_prov = OpenAICompatibleProvider(
                api_key=ali_key,
                base_url=ali_url or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                default_model=alt_ali_model,
                timeout_seconds=timeout,
                max_retries=retries,
                provider_name="alibaba",
                debug_log_path=debug_log_path,
            )
            fallbacks.append((alt_ali_prov, "alibaba", alt_ali_model))

        # 1. Google AI Studio fallback
        if name not in {"google", "gemini"}:
            g_key = resolve_provider_api_key("google")
            if g_key:
                g_prov = OpenAICompatibleProvider(
                    api_key=g_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                    default_model="gemini-flash-latest",
                    timeout_seconds=timeout,
                    max_retries=retries,
                    provider_name="google",
                    debug_log_path=debug_log_path,
                )
                fallbacks.append((g_prov, "google", "gemini-flash-latest"))

        # 2. Alibaba Cloud fallback (when another provider is primary)
        if name not in {"alibaba", "dashscope", "aliyun", "qwen"}:
            if ali_key:
                a_prov = OpenAICompatibleProvider(
                    api_key=ali_key,
                    base_url=ali_url or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                    default_model="qwen-plus-character",
                    timeout_seconds=timeout,
                    max_retries=retries,
                    provider_name="alibaba",
                    debug_log_path=debug_log_path,
                )
                fallbacks.append((a_prov, "alibaba", "qwen-plus-character"))

        # 3. OpenRouter fallback
        if name != "openrouter":
            or_key = resolve_provider_api_key("openrouter")
            if or_key:
                or_prov = OpenAICompatibleProvider(
                    api_key=or_key,
                    base_url="https://openrouter.ai/api/v1",
                    default_model="nvidia/nemotron-3.5-lightning:free",
                    timeout_seconds=timeout,
                    max_retries=retries,
                    provider_name="openrouter",
                    debug_log_path=debug_log_path,
                )
                fallbacks.append((or_prov, "openrouter", "nvidia/nemotron-3.5-lightning:free"))

        # 4. Hetzner fallback
        if name != "hetzner":
            hz_key = resolve_provider_api_key("hetzner")
            if hz_key:
                hz_prov = OpenAICompatibleProvider(
                    api_key=hz_key,
                    base_url="https://inference.hetzner.com/api/v1",
                    default_model="Qwen/Qwen3.6-35B-A3B-FP8",
                    timeout_seconds=timeout,
                    max_retries=retries,
                    provider_name="hetzner",
                    debug_log_path=debug_log_path,
                )
                fallbacks.append((hz_prov, "hetzner", "Qwen/Qwen3.6-35B-A3B-FP8"))

        if fallbacks:
            return ResilientFallbackProvider(
                primary_provider=primary,
                primary_name=name,
                fallback_providers=fallbacks,
                progress_callback=progress_callback,
                debug_log_path=debug_log_path,
            )
        return primary

    raise ValueError(f"Unsupported LLM provider: {provider_name}")
