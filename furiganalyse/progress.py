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
    "canonical-analysis": 10,
    "tokenizing": 15,
    "dictionary-lookup": 30,
    "expression-lookup": 50,
    "name-lookup": 55,
    "study-selection": 65,
    "linked-rendering": 72,
    "assistance-selection": 78,
    "density-planning": 84,
    "adaptive-rendering": 90,
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
            "words_total": 0,
            "words_processed": 0,
            "words_remaining": 0,
            "tokens_found": 0,
            "dictionary_matches": 0,
            "expressions_total": 0,
            "expressions_processed": 0,
            "expression_matches": 0,
            "names_total": 0,
            "names_processed": 0,
            "name_matches": 0,
            "study_items": 0,
            "pipeline_mode": "furigana",
            "combined_phase": None,
            "eta_seconds": None,
            "elapsed_seconds": 0,
            "input_bytes": input_bytes,
            "output_bytes": None,
        }
        self.update({"stage": "queued"})

    def update(self, event: Mapping[str, Any]) -> None:
        allowed = {
            "stage", "sections_total", "sections_completed", "characters_total",
            "characters_processed", "output_bytes", "words_total",
            "words_processed", "tokens_found", "dictionary_matches",
            "expressions_total", "expressions_processed", "expression_matches",
            "names_total", "names_processed", "name_matches", "study_items",
            "units_total", "units_completed", "pipeline_mode",
            "combined_phase", "status_note",
            "translation_model", "translation_backend",
            "translation_chapters_completed", "translation_chapters_total",
            "translation_paragraphs_completed", "translation_paragraphs_total",
            "translation_cache_hits", "translation_current_chapter",
            "translation_latest_japanese", "translation_latest_english",
            "cast_summary", "glossary_summary",
            "main_file_ready", "bilingual_file_ready",
            "main_output_bytes", "bilingual_output_bytes",
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
        self.values["words_remaining"] = max(
            0, int(self.values["words_total"]) - int(self.values["words_processed"])
        )
        rate = processed / elapsed if elapsed > 0 and processed > 0 else 0
        self.values["characters_per_second"] = round(rate)
        self.values["eta_seconds"] = (
            round(self.values["characters_remaining"] / rate)
            if rate > 0 and self.values["stage"] in {"processing", "tokenizing"}
            else None
        )
        if self.values["stage"] == "processing":
            fraction = processed / total if total else section_done / section_total if section_total else 0
            self.values["percent"] = min(90, 10 + round(80 * fraction))
        elif self.values["stage"] in {
            "tokenizing", "dictionary-lookup", "expression-lookup", "name-lookup"
        }:
            ranges = {
                "tokenizing": (15, 30, "units_completed", "units_total"),
                "dictionary-lookup": (30, 50, "words_processed", "words_total"),
                "expression-lookup": (50, 57, "expressions_processed", "expressions_total"),
                "name-lookup": (57, 65, "names_processed", "names_total"),
            }
            start, end, completed_key, total_key = ranges[self.values["stage"]]
            count = int(self.values.get(completed_key, 0))
            count_total = int(self.values.get(total_key, 0))
            fraction = count / count_total if count_total else 0
            self.values["percent"] = min(end, start + round((end - start) * fraction))
        if self.values["stage"] in {"complete", "error"}:
            self.values["percent"] = 100
        elif self.values["pipeline_mode"] in {"combined", "guided"}:
            if self.values["combined_phase"] == "furigana":
                # Furigana stage runs first: scale 0-100% to 0-40%
                self.values["percent"] = min(40, round(self.values["percent"] * 0.4))
            elif self.values["combined_phase"] == "dictionary":
                # Dictionary stage runs second: scale 0-100% to 40-98%
                self.values["percent"] = min(98, 40 + round(self.values["percent"] * 0.58))
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
