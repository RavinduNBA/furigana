"""Manage and persist the list of recent ebook conversions (up to 10)."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


MAX_RECENT_CONVERSIONS = 10


def format_timestamp(dt: Optional[datetime] = None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%b %d, %H:%M")


def format_file_size(bytes_count: Optional[int]) -> str:
    if bytes_count is None or bytes_count <= 0:
        return ""
    if bytes_count < 1024:
        return f"{bytes_count} B"
    if bytes_count < 1048576:
        return f"{bytes_count / 1024:.1f} KB"
    return f"{bytes_count / 1048576:.1f} MB"


def get_recent_conversions_path(output_folder: str | Path) -> Path:
    return Path(output_folder) / "recent_conversions.json"


def load_recent_conversions(output_folder: str | Path) -> list[dict[str, Any]]:
    path = get_recent_conversions_path(output_folder)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data[:MAX_RECENT_CONVERSIONS]
    except Exception:
        pass
    return []


def record_conversion(
    output_folder: str | Path,
    uid: str,
    filename: str,
    output_filename: str,
    pipeline_mode: str,
    furigana_mode: str = "add",
    status: str = "in_progress",
    output_bytes: Optional[int] = None,
) -> list[dict[str, Any]]:
    path = get_recent_conversions_path(output_folder)
    items = load_recent_conversions(output_folder)

    # Check if entry already exists (e.g. updating from in_progress to complete)
    now_str = format_timestamp()
    existing_idx = next((i for i, item in enumerate(items) if item.get("uid") == uid), None)

    record = {
        "uid": uid,
        "filename": filename,
        "output_filename": output_filename,
        "pipeline_mode": pipeline_mode,
        "furigana_mode": furigana_mode,
        "status": status,
        "timestamp": now_str if existing_idx is None else items[existing_idx].get("timestamp", now_str),
        "file_size": format_file_size(output_bytes),
        "output_bytes": output_bytes,
        "download_url": f"/jobs/{uid}/file",
        "job_url": f"/jobs/{uid}",
    }

    if existing_idx is not None:
        items[existing_idx] = {**items[existing_idx], **record}
    else:
        items.insert(0, record)

    items = items[:MAX_RECENT_CONVERSIONS]

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        pass

    return items
