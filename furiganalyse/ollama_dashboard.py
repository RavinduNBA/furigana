"""Ollama Management and Telemetry Dashboard backend for Furiganalyse."""

from __future__ import annotations

import json
import os
import shutil
import time
import urllib.error
import urllib.request
from typing import Any

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


def _http_get(endpoint: str, timeout: int = 5) -> dict[str, Any]:
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    req = urllib.request.Request(url, headers={"User-Agent": "Furiganalyse/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post(endpoint: str, data: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Furiganalyse/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_delete(endpoint: str, data: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Furiganalyse/1.0"}, method="DELETE")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read().decode("utf-8")
        return json.loads(content) if content else {"status": "success"}


def get_system_telemetry() -> dict[str, Any]:
    """Gathers CPU, memory, and disk telemetry."""
    mem_total = 0
    mem_available = 0
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split(":")
                if parts[0] == "MemTotal":
                    mem_total = int(parts[1].split()[0]) * 1024
                elif parts[0] == "MemAvailable":
                    mem_available = int(parts[1].split()[0]) * 1024
    except Exception:
        pass

    mem_used = max(0, mem_total - mem_available)
    mem_percent = round((mem_used / mem_total * 100), 1) if mem_total else 0

    disk = shutil.disk_usage("/")
    cpu_count = os.cpu_count() or 1

    return {
        "cpu_count": cpu_count,
        "mem_total_bytes": mem_total,
        "mem_used_bytes": mem_used,
        "mem_available_bytes": mem_available,
        "mem_percent": mem_percent,
        "disk_total_bytes": disk.total,
        "disk_used_bytes": disk.used,
        "disk_free_bytes": disk.free,
        "disk_percent": round((disk.used / disk.total * 100), 1) if disk.total else 0,
    }


def get_ollama_dashboard_data() -> dict[str, Any]:
    """Gathers complete status, installed models, loaded models, and system metrics."""
    telemetry = get_system_telemetry()
    start_time = time.perf_counter()

    try:
        version_data = _http_get("/api/version")
        latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
        is_online = True
        version = version_data.get("version", "unknown")
    except Exception:
        latency_ms = 0
        is_online = False
        version = "offline"

    installed_models = []
    loaded_models = []

    if is_online:
        try:
            tags_data = _http_get("/api/tags")
            installed_models = tags_data.get("models", [])
        except Exception:
            pass

        try:
            ps_data = _http_get("/api/ps")
            loaded_models = ps_data.get("models", [])
        except Exception:
            pass

    return {
        "online": is_online,
        "endpoint": OLLAMA_BASE_URL,
        "version": version,
        "latency_ms": latency_ms,
        "installed_models": installed_models,
        "installed_count": len(installed_models),
        "loaded_models": loaded_models,
        "loaded_count": len(loaded_models),
        "telemetry": telemetry,
    }


def run_translation_test(model: str = "qwen2.5:3b", japanese_text: str = "司波達也は静かに立ち上がった。") -> dict[str, Any]:
    """Runs an interactive Japanese to English translation test."""
    start = time.perf_counter()
    data = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a professional Japanese to English light novel translator. Translate accurately while preserving nuance. Return only the English translation.",
            },
            {
                "role": "user",
                "content": japanese_text,
            },
        ],
        "stream": False,
    }

    resp = _http_post("/api/chat", data, timeout=60)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)

    message = resp.get("message", {})
    english = message.get("content", "").strip()
    eval_count = resp.get("eval_count", 0)
    eval_duration = resp.get("eval_duration", 0)
    tok_per_sec = round(eval_count / (eval_duration / 1e9), 1) if eval_duration > 0 else 0

    return {
        "japanese": japanese_text,
        "english": english,
        "model": model,
        "duration_ms": duration_ms,
        "eval_count": eval_count,
        "tokens_per_second": tok_per_sec,
    }
