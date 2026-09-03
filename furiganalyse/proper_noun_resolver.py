"""LLM-assisted proper noun resolver for furigana correction.

Collects 固有名詞 tokens that have no JMnedict match and feeds them as a single
batch JSON request to the configured LLM. The resolved readings and romanizations
are returned as an override dictionary keyed on the token surface form, and are
applied to the vocabulary report before furigana rendering.

Design goals:
- One large batch call per book (not per token/per chapter)
- Results are cached keyed on book_id + candidate hash (re-conversion is free)
- If the LLM is unavailable or times out, the pipeline continues without it
- Works independently of the Bilingual Companion feature
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CACHE_SCHEMA_VERSION = 1

# Maximum number of unresolved proper nouns to send to the LLM in a single batch
MAX_BATCH_SIZE = 120

# Part-of-speech tags that indicate a proper noun candidate
PROPER_NOUN_POS_PATTERNS = re.compile(r"固有名詞|人名|地名|組織|国名")

SYSTEM_PROMPT = """You are a Japanese light novel expert specialising in proper noun romanisation and furigana correction.

You will receive a JSON array of Japanese proper noun surface forms extracted from a light novel,
each accompanied by 1-3 short context sentences from the book.

For each item, determine:
1. The correct phonetic reading in hiragana (e.g. "たつや")
2. The standard romanised English form (e.g. "Tatsuya")
3. The entity type: "person", "place", "organization", "title", "magic_term", or "other"

Respond ONLY with a valid JSON array. Each element must have exactly these keys:
  surface, reading, romanized, entity_type

Rules:
- For personal names, use Hepburn romanisation (family name first if both parts are given).
- If the surface form is a common word used as a name (e.g. "深雪"), still give the name reading.
- If the surface form is an author-invented technical term, romanise it phonetically.
- If you cannot determine the reading with confidence, set "reading" to null and "romanized" to null.
- Do NOT add any explanatory text outside the JSON array.

Example output:
[
  {"surface": "司波達也", "reading": "しばたつや", "romanized": "Tatsuya Shiba", "entity_type": "person"},
  {"surface": "深雪", "reading": "みゆき", "romanized": "Miyuki", "entity_type": "person"},
  {"surface": "十師族", "reading": "じゅうしぞく", "romanized": "Juushi-zoku", "entity_type": "organization"}
]
"""


def _candidate_hash(candidates: list[dict[str, Any]], series_context: str = "") -> str:
    """Deterministic hash of the candidate list for cache keying."""
    key = json.dumps(
        [sorted(c["surface"] for c in candidates), series_context], ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def collect_unresolved_proper_nouns(
    vocabulary: dict[str, Any],
    canonical_book: dict[str, Any],
    *,
    max_items: int = MAX_BATCH_SIZE,
    series_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Collect proper-noun candidates that have no JMnedict or Series Memory match.

    Returns a list of dicts with keys: surface, context_sentences
    """
    # Build a set of surfaces that already have JMnedict matches
    resolved_surfaces: set[str] = set()
    name_matches = vocabulary.get("name_dictionary_matches", [])
    name_occurrences = {
        occ["id"]: occ for occ in vocabulary.get("name_occurrences", [])
    }
    for match in name_matches:
        name_id = match.get("name_id", "")
        if name_id in name_occurrences:
            resolved_surfaces.add(name_occurrences[name_id].get("surface", ""))

    # Pre-resolve and skip any surfaces already present in Series Memory
    if series_profile:
        for name in (series_profile.get("characters") or {}).keys():
            resolved_surfaces.add(name)
        for kanji in (series_profile.get("ruby_overrides") or {}).keys():
            resolved_surfaces.add(kanji)
        for term in (series_profile.get("glossary") or {}).keys():
            resolved_surfaces.add(term)

    # Build a quick sentence lookup: block_id -> sentence texts
    block_sentences: dict[str, list[str]] = {}
    for chapter in canonical_book.get("chapters", []):
        for block in chapter.get("blocks", []):
            bid = block.get("id", "")
            block_sentences[bid] = [
                s.get("text", "") for s in block.get("sentences", [])
            ]

    # Scan candidates for proper-noun POS that are NOT in resolved_surfaces
    seen: dict[str, dict[str, Any]] = {}
    for cand in vocabulary.get("candidates", []):
        pos = cand.get("part_of_speech") or ""
        surface = cand.get("surface", "")
        if not surface or surface in resolved_surfaces:
            continue
        if not PROPER_NOUN_POS_PATTERNS.search(pos):
            continue
        if surface in seen:
            # Add another context sentence if we have room
            existing = seen[surface]
            ctx = block_sentences.get(cand.get("block_id", ""), [])
            if ctx and len(existing["context_sentences"]) < 3:
                sentence = " ".join(ctx)[:120]
                if sentence not in existing["context_sentences"]:
                    existing["context_sentences"].append(sentence)
            continue
        ctx = block_sentences.get(cand.get("block_id", ""), [])
        seen[surface] = {
            "surface": surface,
            "context_sentences": [" ".join(ctx)[:120]] if ctx else [],
        }

    candidates = list(seen.values())[:max_items]
    logger.info(
        "collect_unresolved_proper_nouns: found %d unresolved proper nouns "
        "(%d already resolved by JMnedict or Series Memory)",
        len(candidates),
        len(resolved_surfaces),
    )
    return candidates


def _load_cache(cache_path: Path) -> dict[str, dict[str, Any]] | None:
    """Load cached resolution results, returning None if invalid or missing."""
    if not cache_path.is_file():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if data.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None
        return data.get("overrides", {})
    except Exception:
        return None


def _save_cache(
    cache_path: Path,
    candidate_hash: str,
    overrides: dict[str, dict[str, Any]],
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": CACHE_SCHEMA_VERSION,
                "candidate_hash": candidate_hash,
                "overrides": overrides,
                "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def resolve_proper_nouns(
    candidates: list[dict[str, Any]],
    provider: Any,
    *,
    model: str | None = None,
    series_profile: dict[str, Any] | None = None,
    cache_dir: Path | None = None,
    progress_callback: Any = None,
) -> dict[str, dict[str, Any]]:
    """Send unresolved proper nouns to the LLM in a single batch.

    Returns a dict keyed by surface form:
        { "達也": {"reading": "たつや", "romanized": "Tatsuya", "entity_type": "person"}, ... }
    """
    from furiganalyse.llm_provider import LLMMessage, LLMRequest
    from furiganalyse.series_glossary import build_series_prompt_context

    if not candidates:
        return {}

    series_ctx_str = build_series_prompt_context(series_profile)
    active_system_prompt = (
        f"{SYSTEM_PROMPT}\n\nESTABLISHED SERIES CAST & MEMORY:\n{series_ctx_str}\n"
        if series_ctx_str
        else SYSTEM_PROMPT
    )

    candidate_hash = _candidate_hash(candidates, series_ctx_str)
    cache_path = (
        (cache_dir / f"proper_noun_overrides_{candidate_hash}.json")
        if cache_dir
        else None
    )

    # Pre-populate from Series Memory so known characters/words do not require an LLM call
    series_overrides: dict[str, dict[str, Any]] = {}
    if series_profile:
        for name, char_data in (series_profile.get("characters") or {}).items():
            reading = char_data.get("reading") or char_data.get("hiragana") or ""
            romanized = char_data.get("romanized") or name
            role = char_data.get("role") or "person"
            if reading or romanized:
                series_overrides[name] = {"reading": reading or None, "romanized": romanized or None, "entity_type": role}
        for kanji, reading in (series_profile.get("ruby_overrides") or {}).items():
            if kanji not in series_overrides and reading:
                series_overrides[kanji] = {"reading": reading, "romanized": None, "entity_type": "ruby_override"}

    unresolved_candidates = [c for c in candidates if c["surface"] not in series_overrides]
    if not unresolved_candidates:
        logger.info("resolve_proper_nouns: all %d proper nouns resolved directly from Series Memory — no LLM call needed", len(candidates))
        if progress_callback:
            try:
                progress_callback({
                    "log": f"Module 4: All {len(candidates)} proper nouns resolved from Series Memory — zero LLM calls needed",
                })
            except Exception:
                pass
        if cache_path:
            _save_cache(cache_path, candidate_hash, series_overrides)
        return series_overrides

    # Save local context file to disk for fault tolerance and debug logging
    context_backup_dir = (cache_dir / "context_backups") if cache_dir else Path("data/context_backups")
    context_backup_dir.mkdir(parents=True, exist_ok=True)
    ctx_file = context_backup_dir / f"module4_proper_nouns_{candidate_hash}.json"
    try:
        ctx_file.write_text(json.dumps({
            "module": "module_4_proper_nouns",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "pending_llm",
            "candidates": unresolved_candidates,
            "system_prompt": active_system_prompt,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.debug("Could not write module 4 context file: %s", e)

    if progress_callback:
        try:
            progress_callback({
                "log": f"Module 4 (Proper Nouns): Sending {len(unresolved_candidates)} unresolved proper nouns to {model or 'LLM'} for reading/romanization…",
                "translation_current_chapter": "LLM Proper Noun Resolution",
                "translation_latest_japanese": "  ".join(c["surface"] for c in unresolved_candidates[:20]),
                "translation_latest_english": "Resolving readings and romanizations…",
            })
        except Exception:
            pass

    user_content = json.dumps(
        [
            {
                "surface": c["surface"],
                "context": c.get("context_sentences", [])[:2],
            }
            for c in unresolved_candidates
        ],
        ensure_ascii=False,
        indent=2,
    )

    req = LLMRequest(
        messages=[
            LLMMessage(role="system", content=active_system_prompt),
            LLMMessage(role="user", content=user_content),
        ],
        temperature=0.1,
        model=model,
        response_json=False,
        max_tokens=8192,
    )

    try:
        start_t = time.time()
        resp = provider.generate(req)
        elapsed = time.time() - start_t
        raw = resp.content.strip()
        logger.info("Module 4 (Proper Nouns) LLM response (%d characters in %.1fs):\n%s", len(raw), elapsed, raw)
        # Strip any markdown code fences the model may add
        if raw.startswith("```"):
            raw = re.sub(r"^```[^\n]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw.strip())
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            logger.warning("resolve_proper_nouns: LLM returned non-list, skipping. Response preview: %s", raw[:300])
            if progress_callback:
                try:
                    progress_callback({
                        "log": f"Module 4 (Proper Nouns): LLM response format unexpected (preview: {raw[:150]}). Using dictionary-only readings.",
                    })
                except Exception:
                    pass
            return {}

        overrides: dict[str, dict[str, Any]] = {}
        for item in parsed:
            surface = item.get("surface", "")
            reading = item.get("reading") or None
            romanized = item.get("romanized") or None
            entity_type = item.get("entity_type", "other")
            if surface and (reading or romanized):
                overrides[surface] = {
                    "reading": reading,
                    "romanized": romanized,
                    "entity_type": entity_type,
                }

        # Merge pre-resolved series overrides with new LLM resolutions
        for k, v in series_overrides.items():
            if k not in overrides:
                overrides[k] = v

        try:
            ctx_file.write_text(json.dumps({
                "module": "module_4_proper_nouns",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "status": "completed",
                "elapsed_seconds": round(elapsed, 2),
                "resolved_count": len(overrides),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        if progress_callback and overrides:
            try:
                progress_callback({
                    "log": f"Module 4: LLM resolved {len(overrides)} proper nouns in {elapsed:.1f}s",
                })
                for surf, details in list(overrides.items())[:5]:
                    progress_callback({
                        "log": f"  ↳ 【{surf}】→ {details.get('reading')} ({details.get('romanized')})",
                    })
            except Exception:
                pass

        logger.info(
            "resolve_proper_nouns: resolved %d/%d candidates via LLM in %.1fs",
            len(overrides),
            len(candidates),
            elapsed,
        )

        if progress_callback:
            try:
                sample = ", ".join(
                    f"{s} → {v['romanized'] or v['reading']}"
                    for s, v in list(overrides.items())[:8]
                )
                progress_callback({
                    "log": f"Module 4 complete: {len(overrides)} proper names resolved via {model or 'LLM'} in {elapsed:.1f}s. Sample: {sample}",
                    "translation_latest_english": sample or "No resolutions returned",
                })
            except Exception:
                pass

        if cache_path:
            _save_cache(cache_path, candidate_hash, overrides)

        return overrides

    except Exception as exc:
        logger.warning("resolve_proper_nouns: LLM call failed (%s), skipping", exc)
        if progress_callback:
            try:
                progress_callback({
                    "log": f"Module 4 (Proper Nouns): LLM call failed ({exc}). Using dictionary-only readings.",
                })
            except Exception:
                pass
        return {}


def apply_proper_noun_overrides(
    vocabulary: dict[str, Any],
    overrides: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Patch vocabulary candidates and name_occurrences with LLM-resolved readings.

    Returns a modified copy of the vocabulary dict.
    """
    if not overrides:
        return vocabulary

    patched_candidates = []
    patch_count = 0
    for cand in vocabulary.get("candidates", []):
        surface = cand.get("surface", "")
        if surface in overrides:
            override = overrides[surface]
            new_reading = override.get("reading")
            if new_reading and cand.get("reading") != new_reading:
                cand = dict(cand)
                cand["reading"] = new_reading
                cand["reading_source"] = "llm-proper-noun-resolver"
                patch_count += 1
        patched_candidates.append(cand)

    patched_names = []
    for occ in vocabulary.get("name_occurrences", []):
        surface = occ.get("surface", "")
        if surface in overrides:
            override = overrides[surface]
            new_reading = override.get("reading")
            if new_reading and occ.get("reading") != new_reading:
                occ = dict(occ)
                occ["reading"] = new_reading
                patch_count += 1
        patched_names.append(occ)

    logger.info(
        "apply_proper_noun_overrides: patched %d readings in %d override surfaces",
        patch_count,
        len(overrides),
    )

    result = dict(vocabulary)
    result["candidates"] = patched_candidates
    result["name_occurrences"] = patched_names
    result["proper_noun_overrides"] = overrides
    return result
