"""Manage, persist, and housekeep recent ebook conversions (up to 10)."""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

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


def ensure_job_conversion_log(task_dir: Path) -> None:
    """Ensure conversion.log exists in the task directory from progress.json if available."""
    log_file = task_dir / "conversion.log"
    prog_file = task_dir / "progress.json"
    if not log_file.is_file() and prog_file.is_file():
        try:
            data = json.loads(prog_file.read_text(encoding="utf-8"))
            log_lines = data.get("log_lines") or []
            if log_lines:
                log_file.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        except Exception:
            pass


def housekeep_conversions(output_folder: str | Path) -> list[dict[str, Any]]:
    """Enforce retention of at most 10 recent conversions, save verbose logs, and purge older/orphaned folders."""
    path = get_recent_conversions_path(output_folder)
    items = load_recent_conversions(output_folder)

    # 1. Separate top 10 from older items
    retained_items = items[:MAX_RECENT_CONVERSIONS]
    dropped_items = items[MAX_RECENT_CONVERSIONS:]

    out_dir = Path(output_folder)
    if not out_dir.is_dir():
        return retained_items

    # 2. Delete folders for dropped items
    for item in dropped_items:
        uid = item.get("uid")
        if uid:
            task_dir = out_dir / uid
            if task_dir.is_dir():
                try:
                    shutil.rmtree(task_dir, ignore_errors=True)
                    logger.info("Housekeeping: purged older conversion folder %s", uid)
                except Exception as exc:
                    logger.warning("Housekeeping failed to remove folder %s: %s", uid, exc)

    # 3. Ensure verbose logs are saved and intermediate scratch files removed in retained items
    retained_uids: set[str] = set()
    for item in retained_items:
        uid = item.get("uid")
        if not uid:
            continue
        retained_uids.add(uid)
        task_dir = out_dir / uid
        if task_dir.is_dir():
            ensure_job_conversion_log(task_dir)
            # Remove heavy intermediate scratch directories to save disk space
            study_work = task_dir / "study-work"
            if study_work.is_dir():
                shutil.rmtree(study_work, ignore_errors=True)
            stage_furi = task_dir / "furigana-stage.epub"
            if stage_furi.is_file():
                try:
                    stage_furi.unlink()
                except Exception:
                    pass

    # 4. Scan output directory for any orphaned subdirectories not in retained_uids
    try:
        for sub in out_dir.iterdir():
            if sub.is_dir() and not sub.name.startswith("."):
                if sub.name not in retained_uids:
                    try:
                        shutil.rmtree(sub, ignore_errors=True)
                        logger.info("Housekeeping: purged orphaned folder %s", sub.name)
                    except Exception as exc:
                        logger.warning("Housekeeping failed to remove %s: %s", sub.name, exc)
    except Exception:
        pass

    # 5. Save the updated recent_conversions.json
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(retained_items, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        pass

    return retained_items


def record_conversion(
    output_folder: str | Path,
    uid: str,
    filename: str,
    output_filename: str,
    pipeline_mode: str = "furigana",
    furigana_mode: str = "add",
    status: str = "in_progress",
    output_bytes: Optional[int] = None,
) -> list[dict[str, Any]]:
    path = get_recent_conversions_path(output_folder)
    items = load_recent_conversions(output_folder)

    # Normalize pipeline_mode
    if isinstance(pipeline_mode, bool) or not pipeline_mode:
        pipeline_mode = "furigana"

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

    # Ensure log is saved in task dir
    task_dir = Path(output_folder) / uid
    if task_dir.is_dir():
        ensure_job_conversion_log(task_dir)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        pass

    # Run housekeeping
    return housekeep_conversions(output_folder)


def remove_recent_conversion(output_folder: str | Path, uid: str) -> list[dict[str, Any]]:
    """Removes a specific conversion from history and deletes its task folder."""
    path = get_recent_conversions_path(output_folder)
    items = load_recent_conversions(output_folder)
    items = [item for item in items if item.get("uid") != uid]

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        pass

    # Clean up directory on disk
    task_dir = Path(output_folder) / uid
    if task_dir.is_dir():
        try:
            shutil.rmtree(task_dir, ignore_errors=True)
        except Exception:
            pass

    return housekeep_conversions(output_folder)


def clear_all_recent_conversions(output_folder: str | Path) -> list[dict[str, Any]]:
    """Clears all recent conversions and purges their task directories from disk."""
    path = get_recent_conversions_path(output_folder)
    items = load_recent_conversions(output_folder)
    out_dir = Path(output_folder)

    for item in items:
        uid = item.get("uid")
        if uid:
            task_dir = out_dir / uid
            if task_dir.is_dir():
                try:
                    shutil.rmtree(task_dir, ignore_errors=True)
                except Exception:
                    pass

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]", encoding="utf-8")
    except Exception:
        pass

    return []


def cleanup_orphaned_conversions(output_folder: str | Path) -> list[dict[str, Any]]:
    """Marks any leftover 'in_progress' jobs as 'stopped' and triggers full housekeeping."""
    path = get_recent_conversions_path(output_folder)
    items = load_recent_conversions(output_folder)
    changed = False

    for item in items:
        if item.get("status") == "in_progress":
            item["status"] = "stopped"
            changed = True

    if changed:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        except Exception:
            pass

    return housekeep_conversions(output_folder)
