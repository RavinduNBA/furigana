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


def _candidate_hash(candidates: list[dict[str, Any]]) -> str:
    """Deterministic hash of the candidate list for cache keying."""
    key = json.dumps(
        sorted(c["surface"] for c in candidates), ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def collect_unresolved_proper_nouns(
    vocabulary: dict[str, Any],
    canonical_book: dict[str, Any],
    *,
    max_items: int = MAX_BATCH_SIZE,
) -> list[dict[str, Any]]:
    """Collect proper-noun candidates that have no JMnedict match.

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
        "(%d already resolved by JMnedict)",
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
    cache_dir: Path | None = None,
    progress_callback: Any = None,
) -> dict[str, dict[str, Any]]:
    """Send unresolved proper nouns to the LLM in a single batch.

    Returns a dict keyed by surface form:
        { "達也": {"reading": "たつや", "romanized": "Tatsuya", "entity_type": "person"}, ... }
    """
    from furiganalyse.llm_provider import LLMMessage, LLMRequest

    if not candidates:
        return {}

    candidate_hash = _candidate_hash(candidates)
    cache_path = (
        (cache_dir / f"proper_noun_overrides_{candidate_hash}.json")
        if cache_dir
        else None
    )

    # Try cache first
    if cache_path:
        cached = _load_cache(cache_path)
        if cached is not None:
            logger.info("resolve_proper_nouns: loaded %d overrides from cache", len(cached))
            if progress_callback:
                try:
                    progress_callback({
                        "log": f"Proper noun resolution: loaded {len(cached)} cached overrides (no LLM call needed)",
                    })
                except Exception:
                    pass
            return cached

    if progress_callback:
        try:
            progress_callback({
                "log": f"Module 4 (Proper Nouns): Sending {len(candidates)} unresolved proper nouns to {model or 'LLM'} for reading/romanization…",
                "translation_current_chapter": "LLM Proper Noun Resolution",
                "translation_latest_japanese": "  ".join(c["surface"] for c in candidates[:20]),
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
            for c in candidates
        ],
        ensure_ascii=False,
        indent=2,
    )

    req = LLMRequest(
        messages=[
            LLMMessage(role="system", content=SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_content),
        ],
        temperature=0.1,
        model=model,
        response_json=False,
    )

    try:
        start_t = time.time()
        resp = provider.generate(req)
        elapsed = time.time() - start_t
        raw = resp.content.strip()
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
