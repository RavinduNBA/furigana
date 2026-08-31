"""LLM-assisted contextual gloss enrichment for study notes.

Replaces generic JMdict sense-1 descriptions in study note cards with
book-specific usage glosses, produced by a single batched LLM call.

Design goals:
- Feed the LLM the word, its reading, and the 3 best context sentences from the book.
- One batch call per conversion covering all selected study items.
- Results are cached per (book_id + item_hash) — free on re-conversion.
- Graceful fallback: if the LLM fails, JMdict glosses are used unchanged.
- Works for ALL conversion modes (study, guided, combined) — does not require
  the Bilingual Companion feature.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CACHE_SCHEMA_VERSION = 1
MAX_ITEMS_PER_BATCH = 6   # 6 items per batch ensures reasoning models finish within token and timeout budgets

SYSTEM_PROMPT = """You are a Japanese light novel terminology expert.
For each vocabulary item from the novel, provide a concise 1-2 sentence contextual gloss explaining its meaning in this light novel.
If the term has a novel-specific or hierarchy-specific meaning (magic, school division, CAD, etc.), explain that directly.

Respond ONLY with a valid JSON array. Each element must have exactly these keys:
  id (the item id from input), gloss (the contextual description)

Do NOT add any text outside the JSON array.

Example:
[
  {"id": "item-001", "gloss": "Spell activation device worn on the wrist; standard equipment for magic high school students."},
  {"id": "item-002", "gloss": "Course 2 reserve student at First High (Weed), subject to social hierarchy and discrimination."}
]
"""


def _items_hash(items: list[dict[str, Any]]) -> str:
    key = json.dumps(sorted(i["id"] for i in items), sort_keys=True)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def collect_gloss_candidates(
    annotation_plan: dict[str, Any],
    canonical_book: dict[str, Any],
    *,
    max_items: int = 200,
) -> list[dict[str, Any]]:
    """Build a list of study items with their in-book context sentences.

    Returns a list of dicts: { id, surface, reading, jmdict_gloss, context_sentences }
    """
    # Build block_id -> sentence texts lookup
    block_sentences: dict[str, str] = {}
    for chapter in canonical_book.get("chapters", []):
        for block in chapter.get("blocks", []):
            bid = block.get("id", "")
            block_sentences[bid] = " ".join(
                s.get("text", "") for s in block.get("sentences", [])
            )[:200]

    results = []
    for item in annotation_plan.get("items", [])[:max_items]:
        item_id = item.get("id", "")
        surface = item.get("surface", "")
        reading = item.get("reading", "")
        # Get the first JMdict gloss if available
        gloss = ""
        meanings = item.get("meanings", [])
        if meanings:
            first_meaning = meanings[0]
            senses = first_meaning.get("senses", [])
            if senses:
                glosses = senses[0].get("glosses", [])
                if glosses:
                    gloss = "; ".join(g.get("text", "") for g in glosses[:3])

        # Collect up to 3 unique context sentences from occurrences
        context_sentences = []
        for occ in item.get("occurrences", [])[:5]:
            bid = occ.get("block_id", "")
            sentence = block_sentences.get(bid, "")
            if sentence and sentence not in context_sentences:
                context_sentences.append(sentence)
            if len(context_sentences) >= 3:
                break

        results.append({
            "id": item_id,
            "surface": surface,
            "reading": reading,
            "jmdict_gloss": gloss,
            "context_sentences": context_sentences,
        })

    logger.info("collect_gloss_candidates: prepared %d items for contextual gloss enrichment", len(results))
    return results


def _load_cache(cache_path: Path) -> dict[str, str] | None:
    if not cache_path.is_file():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if data.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None
        return data.get("glosses", {})
    except Exception:
        return None


def _save_cache(cache_path: Path, glosses: dict[str, str]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": CACHE_SCHEMA_VERSION,
                "glosses": glosses,
                "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def enrich_glosses(
    candidates: list[dict[str, Any]],
    provider: Any,
    *,
    model: str | None = None,
    cache_dir: Path | None = None,
    progress_callback: Any = None,
) -> dict[str, str]:
    """Send study item candidates to the LLM for contextual gloss generation.

    Returns a dict mapping item_id -> contextual_gloss string.
    """
    from furiganalyse.llm_provider import LLMMessage, LLMRequest

    if not candidates:
        return {}

    items_hash = _items_hash(candidates)
    cache_path = (cache_dir / f"contextual_glosses_{items_hash}.json") if cache_dir else None

    if cache_path:
        cached = _load_cache(cache_path)
        if cached is not None:
            logger.info("enrich_glosses: loaded %d glosses from cache", len(cached))
            if progress_callback:
                try:
                    progress_callback({
                        "log": f"Contextual gloss enrichment: loaded {len(cached)} cached glosses",
                    })
                except Exception:
                    pass
            return cached

    all_glosses: dict[str, str] = {}
    total_batches = (len(candidates) + MAX_ITEMS_PER_BATCH - 1) // MAX_ITEMS_PER_BATCH

    for batch_idx in range(0, len(candidates), MAX_ITEMS_PER_BATCH):
        batch = candidates[batch_idx:batch_idx + MAX_ITEMS_PER_BATCH]
        batch_num = batch_idx // MAX_ITEMS_PER_BATCH + 1

        if progress_callback:
            try:
                progress_callback({
                    "log": f"Contextual gloss enrichment: batch {batch_num}/{total_batches} ({len(batch)} items)…",
                    "translation_latest_japanese": "  ".join(c["surface"] for c in batch[:10]),
                    "translation_latest_english": f"Generating contextual glosses (batch {batch_num}/{total_batches})…",
                })
            except Exception:
                pass

        user_content = json.dumps(
            [
                {
                    "id": c["id"],
                    "surface": c["surface"],
                    "reading": c["reading"],
                    "jmdict_gloss": c["jmdict_gloss"],
                    "context_sentences": c["context_sentences"],
                }
                for c in batch
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
            max_tokens=8192,
        )

        try:
            start_t = time.time()
            resp = provider.generate(req)
            elapsed = time.time() - start_t
            import re
            raw = (resp.content or "").strip()
            if not raw and isinstance(getattr(resp, "raw", None), dict):
                choices = resp.raw.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    raw = (msg.get("content") or msg.get("reasoning") or "").strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw.strip())
            # Find outermost JSON array if surrounded by commentary
            json_match = re.search(r"\[\s*\{.*\}\s*\]", raw, re.DOTALL)
            if json_match:
                raw = json_match.group(0)
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                batch_count = 0
                for item in parsed:
                    item_id = item.get("id", "")
                    gloss = item.get("gloss", "")
                    if item_id and gloss:
                        all_glosses[item_id] = gloss
                        batch_count += 1
                if progress_callback:
                    try:
                        progress_callback({
                            "log": f"Module 3: Batch {batch_num}/{total_batches} enriched ({batch_count} glosses from {model or 'LLM'} in {elapsed:.1f}s)",
                        })
                    except Exception:
                        pass
        except Exception as exc:
            preview = repr(raw[:100]) if "raw" in locals() and raw else "empty/None"
            logger.warning("enrich_glosses: batch %d failed (%s, preview=%s), skipping remaining batches", batch_num, exc, preview)
            if progress_callback:
                try:
                    progress_callback({
                        "log": f"Module 3 warning: Batch {batch_num}/{total_batches} failed ({exc} | preview: {preview}). Using standard JMdict definitions.",
                    })
                except Exception:
                    pass
            break

    if progress_callback:
        try:
            progress_callback({
                "log": f"Module 3 complete: {len(all_glosses)}/{len(candidates)} contextual study glosses enriched",
            })
        except Exception:
            pass

    if cache_path and all_glosses:
        _save_cache(cache_path, all_glosses)

    return all_glosses


def apply_gloss_enrichments(
    annotation_plan: dict[str, Any],
    glosses: dict[str, str],
) -> dict[str, Any]:
    """Patch annotation plan items with contextual glosses.

    Returns a modified copy of the annotation plan.
    """
    if not glosses:
        return annotation_plan

    patched_items = []
    patch_count = 0
    for item in annotation_plan.get("items", []):
        item_id = item.get("id", "")
        if item_id in glosses:
            item = dict(item)
            item["contextual_gloss"] = glosses[item_id]
            item["display_meaning"] = glosses[item_id]
            patch_count += 1
        patched_items.append(item)

    logger.info(
        "apply_gloss_enrichments: enriched %d/%d study items with contextual glosses",
        patch_count,
        len(patched_items),
    )

    result = dict(annotation_plan)
    result["items"] = patched_items
    return result
