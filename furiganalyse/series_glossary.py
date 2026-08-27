"""Series Glossary & Context Persistence (Cross-Volume Memory).

Allows saving, loading, and merging character profiles, world glossaries, and
established publisher ruby overrides across multiple volumes of a light novel series.

Storage:
- Stored as JSON documents in `data/series/<series_slug>.json`
- Each series profile contains cumulative characters, terminology, and ruby overrides.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SERIES_SCHEMA_VERSION = 1
DEFAULT_STORAGE_DIR = Path(os.environ.get("FURIGANALYSE_SERIES_DIR", "data/series"))


def _slugify(text: str) -> str:
    """Convert text to a safe filename slug."""
    text = re.sub(r"[^\w\s-]", "", text.strip().lower())
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-") or "unnamed-series"


def get_series_storage_dir() -> Path:
    """Get and ensure the series profiles storage directory exists."""
    DEFAULT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_STORAGE_DIR


def list_series_profiles() -> list[dict[str, Any]]:
    """List summary metadata for all saved series profiles."""
    storage_dir = get_series_storage_dir()
    profiles = []

    for path in sorted(storage_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("schema_version") == SERIES_SCHEMA_VERSION:
                profiles.append({
                    "series_id": data.get("series_id", path.stem),
                    "title": data.get("title", path.stem),
                    "character_count": len(data.get("characters", {})),
                    "glossary_count": len(data.get("glossary", {})),
                    "ruby_override_count": len(data.get("ruby_overrides", {})),
                    "volumes_processed": data.get("volumes_processed", []),
                    "updated_at": data.get("updated_at", ""),
                })
        except Exception as exc:
            logger.warning("Failed to load series profile %s: %s", path, exc)

    return sorted(profiles, key=lambda p: p.get("updated_at", ""), reverse=True)


def load_series_profile(series_id: str) -> dict[str, Any] | None:
    """Load a specific series profile by ID/slug."""
    storage_dir = get_series_storage_dir()
    path = storage_dir / f"{_slugify(series_id)}.json"
    if not path.is_file():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Failed to read series profile %s: %s", path, exc)
        return None


def save_series_profile(
    series_id: str,
    title: str,
    characters: dict[str, Any] | None = None,
    glossary: dict[str, Any] | None = None,
    ruby_overrides: dict[str, str] | None = None,
    volume_name: str = "",
) -> dict[str, Any]:
    """Create or update a series profile, merging existing data."""
    slug = _slugify(series_id or title)
    storage_dir = get_series_storage_dir()
    path = storage_dir / f"{slug}.json"

    # Load existing to merge if available
    existing = load_series_profile(slug) or {
        "schema_version": SERIES_SCHEMA_VERSION,
        "series_id": slug,
        "title": title or slug,
        "characters": {},
        "glossary": {},
        "ruby_overrides": {},
        "volumes_processed": [],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Merge characters
    merged_chars = dict(existing.get("characters", {}))
    if characters:
        for k, v in characters.items():
            if isinstance(v, dict):
                merged_chars[k] = v
            elif hasattr(v, "__dict__"):
                merged_chars[k] = v.__dict__

    # Merge glossary
    merged_glossary = dict(existing.get("glossary", {}))
    if glossary:
        for k, v in glossary.items():
            if isinstance(v, dict):
                merged_glossary[k] = v
            elif hasattr(v, "__dict__"):
                merged_glossary[k] = v.__dict__

    # Merge ruby overrides
    merged_ruby = dict(existing.get("ruby_overrides", {}))
    if ruby_overrides:
        merged_ruby.update(ruby_overrides)

    # Volumes list
    volumes = list(existing.get("volumes_processed", []))
    if volume_name and volume_name not in volumes:
        volumes.append(volume_name)

    profile_data = {
        "schema_version": SERIES_SCHEMA_VERSION,
        "series_id": slug,
        "title": title or existing.get("title", slug),
        "characters": merged_chars,
        "glossary": merged_glossary,
        "ruby_overrides": merged_ruby,
        "volumes_processed": volumes,
        "created_at": existing.get("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    path.write_text(
        json.dumps(profile_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("Saved series profile '%s' to %s (%d chars, %d glossary terms)", title, path, len(merged_chars), len(merged_glossary))
    return profile_data


def delete_series_profile(series_id: str) -> bool:
    """Delete a series profile by ID."""
    storage_dir = get_series_storage_dir()
    path = storage_dir / f"{_slugify(series_id)}.json"
    if path.is_file():
        path.unlink()
        logger.info("Deleted series profile %s", path)
        return True
    return False


def apply_series_profile_to_vocabulary(
    series_profile: dict[str, Any],
    vocabulary: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Apply saved character and ruby readings from a series profile as overrides.

    Returns (patched_vocabulary_dict, patch_count).
    """
    if not series_profile:
        return vocabulary, 0

    ruby_overrides = series_profile.get("ruby_overrides", {})
    characters = series_profile.get("characters", {})

    # Build combined surface -> reading map
    readings_map: dict[str, str] = dict(ruby_overrides)
    for surface, char in characters.items():
        reading = char.get("reading") or char.get("hiragana")
        if reading and surface not in readings_map:
            readings_map[surface] = reading

    if not readings_map:
        return vocabulary, 0

    patch_count = 0
    patched_candidates = []
    for cand in vocabulary.get("candidates", []):
        surface = cand.get("surface", "")
        if surface in readings_map and not cand.get("publisher_ruby_id"):
            target_reading = readings_map[surface]
            if cand.get("reading") != target_reading:
                cand = dict(cand)
                cand["reading"] = target_reading
                cand["reading_source"] = f"series-profile:{series_profile.get('series_id', 'custom')}"
                patch_count += 1
        patched_candidates.append(cand)

    patched_names = []
    for occ in vocabulary.get("name_occurrences", []):
        surface = occ.get("surface", "")
        if surface in readings_map and not occ.get("publisher_ruby_id"):
            target_reading = readings_map[surface]
            if occ.get("reading") != target_reading:
                occ = dict(occ)
                occ["reading"] = target_reading
                patch_count += 1
        patched_names.append(occ)

    logger.info(
        "apply_series_profile_to_vocabulary: applied %d overrides from series '%s'",
        patch_count,
        series_profile.get("title", "unknown"),
    )

    result = dict(vocabulary)
    result["candidates"] = patched_candidates
    result["name_occurrences"] = patched_names
    result["series_profile_applied"] = series_profile.get("series_id")
    return result, patch_count
