"""Series Glossary & Context Persistence (Cross-Volume Memory).

Allows saving, loading, and merging character profiles, world glossaries, and
established publisher ruby overrides across multiple volumes of a light novel series.

Storage:
- Stored as JSON documents in `data/series/<series_slug>.json`
- Each series profile contains cumulative characters, terminology, ruby overrides, and plot memories.
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

SERIES_SCHEMA_VERSION = 2
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
            if data.get("schema_version") in {1, SERIES_SCHEMA_VERSION}:
                profiles.append({
                    "series_id": data.get("series_id", path.stem),
                    "title": data.get("title", path.stem),
                    "synopsis": data.get("synopsis", ""),
                    "world_setting": data.get("world_setting", ""),
                    "character_count": len(data.get("characters", {})),
                    "glossary_count": len(data.get("glossary", {})),
                    "ruby_override_count": len(data.get("ruby_overrides", {})),
                    "plot_memory_count": len(data.get("plot_memories", [])),
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
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") in {1, SERIES_SCHEMA_VERSION}:
            return data
        return None
    except Exception as exc:
        logger.error("Failed to read series profile %s: %s", path, exc)
        return None


def save_series_profile(
    series_id: str,
    title: str,
    characters: dict[str, Any] | None = None,
    glossary: dict[str, Any] | None = None,
    ruby_overrides: dict[str, str] | None = None,
    synopsis: str = "",
    world_setting: str = "",
    plot_memories: list[dict[str, Any]] | None = None,
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
        "synopsis": synopsis,
        "world_setting": world_setting,
        "characters": {},
        "glossary": {},
        "ruby_overrides": {},
        "plot_memories": [],
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

    # Merge plot memories
    merged_plots = list(existing.get("plot_memories", []))
    if plot_memories:
        for pm in plot_memories:
            if pm not in merged_plots:
                merged_plots.append(pm)

    # Volumes list
    volumes = list(existing.get("volumes_processed", []))
    if volume_name and volume_name not in volumes:
        volumes.append(volume_name)

    profile_data = {
        "schema_version": SERIES_SCHEMA_VERSION,
        "series_id": slug,
        "title": title or existing.get("title", slug),
        "synopsis": synopsis or existing.get("synopsis", ""),
        "world_setting": world_setting or existing.get("world_setting", ""),
        "characters": merged_chars,
        "glossary": merged_glossary,
        "ruby_overrides": merged_ruby,
        "plot_memories": merged_plots,
        "volumes_processed": volumes,
        "created_at": existing.get("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    path.write_text(
        json.dumps(profile_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info(
        "Saved series profile '%s' to %s (%d chars, %d glossary terms, %d plot memories)",
        title,
        path,
        len(merged_chars),
        len(merged_glossary),
        len(merged_plots),
    )
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


def build_series_prompt_context(series_profile: dict[str, Any] | None, max_items: int = 40) -> str:
    """Build a dense, structured context block for LLM prompt injection."""
    if not series_profile:
        return ""

    lines = []
    title = series_profile.get("title", "").strip()
    synopsis = series_profile.get("synopsis", "").strip()
    world_setting = series_profile.get("world_setting", "").strip()

    if title:
        lines.append(f"SERIES TITLE: {title}")
    if synopsis:
        lines.append(f"SERIES SYNOPSIS: {synopsis}")
    if world_setting:
        lines.append(f"WORLD SETTING & MAGIC SYSTEM: {world_setting}")

    characters = series_profile.get("characters", {})
    if characters:
        lines.append("\nESTABLISHED KEY CHARACTERS:")
        for name, char in list(characters.items())[:max_items]:
            if isinstance(char, dict):
                reading = char.get("reading") or char.get("hiragana") or ""
                romanized = char.get("romanized") or ""
                role = char.get("role") or "Character"
                gender = char.get("gender") or ""
                tone = char.get("speaking_tone") or ""
                aliases = char.get("aliases") or []
                relationships = char.get("relationships")
                rel_str = ""
                if isinstance(relationships, dict) and relationships:
                    rel_str = f", Relations: {', '.join(f'{k}: {v}' for k, v in relationships.items())}"
                elif isinstance(relationships, str) and relationships.strip():
                    rel_str = f", Relations: {relationships.strip()}"
                alias_str = f" Aliases: {', '.join(aliases)}." if aliases else ""
                gender_str = f", Gender: {gender}" if gender else ""
                tone_str = f", Tone: {tone}" if tone else ""
                lines.append(f"- {name} ({reading}{' / ' + romanized if romanized and romanized != reading else ''}): {role}{gender_str}{tone_str}{rel_str}.{alias_str}")
            else:
                lines.append(f"- {name}: {char}")

    ruby_overrides = series_profile.get("ruby_overrides", {})
    glossary = series_profile.get("glossary", {})
    if ruby_overrides or glossary:
        lines.append("\nESTABLISHED WORLD GLOSSARY & AUTHOR RUBY:")
        for term, custom_reading in list(ruby_overrides.items())[:20]:
            lines.append(f"- {term} 【{custom_reading}】: (Author ruby override)")
        for term, item in list(glossary.items())[:max_items]:
            if isinstance(item, dict):
                trans = item.get("preferred_translation") or item.get("translation") or ""
                defn = item.get("definition") or ""
                reading = item.get("reading") or ""
                trans_str = f" -> {trans}" if trans else ""
                defn_str = f" ({defn})" if defn else ""
                reading_str = f" 【{reading}】" if reading else ""
                lines.append(f"- {term}{reading_str}{trans_str}{defn_str}")
            else:
                lines.append(f"- {term}: {item}")

    plot_memories = series_profile.get("plot_memories", [])
    if plot_memories:
        lines.append("\nPREVIOUS VOLUME STORY MEMORY & REVELATIONS:")
        for pm in plot_memories[:5]:
            if isinstance(pm, dict):
                v_title = pm.get("volume_title") or f"Volume {pm.get('volume_number', '')}"
                v_sum = pm.get("summary") or ""
                lines.append(f"- {v_title}: {v_sum}")

    return "\n".join(lines).strip()


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
        if isinstance(char, dict):
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


def suggest_series_name(raw_text: str) -> dict[str, str]:
    """Auto-suggest series title, slug ID, and volume from a book title or filename.

    Examples:
        '魔法科高校の劣等生 3.epub' -> {'clean_title': '魔法科高校の劣等生', 'slug': '魔法科高校の劣等生', 'volume': 'Volume 3'}
        'Sword Art Online - Vol 03.epub' -> {'clean_title': 'Sword Art Online', 'slug': 'sword-art-online', 'volume': 'Volume 3'}
    """
    if not raw_text:
        return {"clean_title": "", "slug": "", "volume": ""}

    s = raw_text.strip()
    # Strip file extension
    s = re.sub(r"\.[a-zA-Z0-9]+$", "", s)
    # Strip tags like - Guided, - Enriched, etc.
    s = re.sub(r"[-_]\s*(Guided|Enriched|Furigana|Bilingual|Converted).*$", "", s, flags=re.IGNORECASE)
    # Strip brackets like [Light Novel], (Digital), [JAP], (Seven Seas), etc.
    s = re.sub(r"\[[^\]]*\]", "", s)
    s = re.sub(r"\([^\)]*\)", "", s)

    # Extract volume indicator if present
    vol_match = re.search(
        r"(?:第\s*([0-9０-９]+)\s*巻|[\b_\s-]v(?:ol(?:ume)?)?\.?\s*([0-9]+)|[\b_\s-]+([0-9０-９]+)(?:[\b_\s-]|$))",
        s,
        re.IGNORECASE,
    )
    vol_str = ""
    if vol_match:
        v_num = vol_match.group(1) or vol_match.group(2) or vol_match.group(3)
        if v_num:
            try:
                v_num_clean = v_num.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
                vol_str = f"Volume {int(v_num_clean)}"
            except Exception:
                vol_str = f"Volume {v_num}"

    # Strip volume indicators from title
    s = re.sub(r"(?:第\s*[0-9０-９]+\s*巻|[\b_\s-]v(?:ol(?:ume)?)?\.?\s*[0-9]+|[\b_\s-]+[0-9０-９]+(?:[\b_\s-]|$))", " ", s, flags=re.IGNORECASE)

    # Normalize whitespace & separators
    clean_title = re.sub(r"[_\s]+", " ", s).strip(" -_")
    if not clean_title:
        clean_title = raw_text

    slug = _slugify(clean_title)
    return {
        "clean_title": clean_title,
        "slug": slug,
        "volume": vol_str,
    }


def find_matching_series_profile(
    raw_text: str,
    existing_profiles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Find an existing series profile matching the book or suggest a new profile."""
    suggestion = suggest_series_name(raw_text)
    clean_title = suggestion["clean_title"].lower()
    clean_slug = suggestion["slug"].lower()
    raw_lower = raw_text.lower()

    if existing_profiles is None:
        existing_profiles = list_series_profiles()

    # Check exact & substring matches against existing profiles
    for p in existing_profiles:
        p_id = (p.get("series_id") or "").lower()
        p_title = (p.get("title") or "").lower()

        # High confidence matches on ID or Title
        if p_id and (p_id == clean_slug or p_id in raw_lower or clean_slug in p_id):
            return {
                "series_id": p.get("series_id"),
                "title": p.get("title") or suggestion["clean_title"],
                "is_existing": True,
                "volume_name": suggestion["volume"],
                "character_count": p.get("character_count", 0),
                "glossary_count": p.get("glossary_count", 0),
            }
        if p_title and (p_title == clean_title or p_title in clean_title or clean_title in p_title or p_title in raw_lower):
            return {
                "series_id": p.get("series_id"),
                "title": p.get("title"),
                "is_existing": True,
                "volume_name": suggestion["volume"],
                "character_count": p.get("character_count", 0),
                "glossary_count": p.get("glossary_count", 0),
            }

    # If no existing match, return newly suggested profile template
    return {
        "series_id": suggestion["slug"],
        "title": suggestion["clean_title"],
        "is_existing": False,
        "volume_name": suggestion["volume"],
        "character_count": 0,
        "glossary_count": 0,
    }
