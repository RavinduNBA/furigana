"""Privacy-safe, cross-process conversion progress snapshots."""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Mapping


STAGE_PERCENT = {
    "queued": 0,
    "preparing": 2,
    "extracting": 5,
    "processing": 10,
    "packaging": 95,
    "complete": 100,
    "error": 100,
}


class ProgressWriter:
    """Write atomic aggregate snapshots readable by the web process."""

    def __init__(self, path: str | Path, input_bytes: int = 0):
        self.path = Path(path)
        self.started = time.monotonic()
        self.values: dict[str, Any] = {
            "stage": "queued",
            "percent": 0,
            "sections_total": 0,
            "sections_completed": 0,
            "sections_remaining": 0,
            "characters_total": 0,
            "characters_processed": 0,
            "characters_remaining": 0,
            "characters_per_second": 0,
            "eta_seconds": None,
            "elapsed_seconds": 0,
            "input_bytes": input_bytes,
            "output_bytes": None,
        }
        self.update({"stage": "queued"})

    def update(self, event: Mapping[str, Any]) -> None:
        allowed = {
            "stage", "sections_total", "sections_completed", "characters_total",
            "characters_processed", "output_bytes",
        }
        self.values.update({key: value for key, value in event.items() if key in allowed})
        elapsed = max(0.0, time.monotonic() - self.started)
        total = int(self.values["characters_total"])
        processed = int(self.values["characters_processed"])
        section_total = int(self.values["sections_total"])
        section_done = int(self.values["sections_completed"])
        self.values["elapsed_seconds"] = round(elapsed, 1)
        self.values["sections_remaining"] = max(0, section_total - section_done)
        self.values["characters_remaining"] = max(0, total - processed)
        rate = processed / elapsed if elapsed > 0 and processed > 0 else 0
        self.values["characters_per_second"] = round(rate)
        self.values["eta_seconds"] = (
            round(self.values["characters_remaining"] / rate)
            if rate > 0 and self.values["stage"] == "processing"
            else None
        )
        if self.values["stage"] == "processing":
            fraction = processed / total if total else section_done / section_total if section_total else 0
            self.values["percent"] = min(90, 10 + round(80 * fraction))
        else:
            self.values["percent"] = STAGE_PERCENT.get(str(self.values["stage"]), 0)
        self._write_atomic()
        logging.info(
            "conversion_progress stage=%s percent=%d sections=%d/%d characters=%d/%d elapsed_seconds=%.1f eta_seconds=%s",
            self.values["stage"],
            self.values["percent"],
            section_done,
            section_total,
            processed,
            total,
            self.values["elapsed_seconds"],
            self.values["eta_seconds"],
        )

    def _write_atomic(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.values, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)


def read_progress(path: str | Path) -> dict[str, Any] | None:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None
