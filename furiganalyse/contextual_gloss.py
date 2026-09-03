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
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CACHE_SCHEMA_VERSION = 2
MAX_ITEMS_PER_BATCH = 6   # 6 items per batch ensures reasoning models finish within token and timeout budgets

SYSTEM_PROMPT = """You are a Japanese light novel terminology expert and literary translator.
You will receive vocabulary items extracted from a novel, each with its surface form, reading, candidate dictionary senses, and in-book context sentences (with the target word marked in 【brackets】).

For each item:
1. Disambiguate the meaning: select the most accurate dictionary sense from "candidate_senses" that fits the sentence context.
2. Write a precise, natural in-universe contextual gloss (1-2 sentences, max 120 chars) explaining its exact meaning in this context.
   Avoid single-word or literal dictionary artifacts (e.g., for 建前 in institutional contexts, write "Official stance / pretense (as in the facade of equal educational opportunity)", NOT "face").

Respond ONLY with a valid JSON array. Each element must have exactly these keys:
  id (the item id from input), gloss (the context-aware explanation), selected_sense_id (optional matching sense id from candidate_senses)

Do NOT add any text outside the JSON array.

Example output:
[
  {
    "id": "item-001",
    "gloss": "Official stance / pretense (referring to the public facade of equal educational opportunity).",
    "selected_sense_id": "jmdict-1524230-sense-0002"
  },
  {
    "id": "item-002",
    "gloss": "Course 2 reserve student at First High (Weed), subject to social hierarchy and discrimination."
  }
]
"""


def _items_hash(items: list[dict[str, Any]], series_context: str = "") -> str:
    key = json.dumps([sorted(i["id"] for i in items), series_context], sort_keys=True)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def collect_gloss_candidates(
    annotation_plan: dict[str, Any],
    canonical_book: dict[str, Any],
    *,
    max_items: int = 200,
) -> list[dict[str, Any]]:
    """Build a list of study items with multi-sense definitions and highlighted context sentences.

    Returns a list of dicts: { id, surface, reading, candidate_senses, jmdict_gloss, context_sentences }
    """
    # Build sentence_id -> text lookup
    sentence_lookup: dict[str, str] = {}
    block_sentences: dict[str, str] = {}
    for chapter in canonical_book.get("chapters", []):
        for block in chapter.get("blocks", []):
            bid = block.get("id", "")
            sentences = block.get("sentences", [])
            for s in sentences:
                sid = s.get("id", "")
                if sid:
                    sentence_lookup[sid] = s.get("text", "")
            block_sentences[bid] = " ".join(s.get("text", "") for s in sentences)[:200]

    results = []
    for item in annotation_plan.get("items", [])[:max_items]:
        item_id = item.get("id", "")
        surface = item.get("surface", "")
        reading = item.get("reading", "")

        # Extract all candidate senses
        candidate_senses = []
        if item.get("dictionary_senses"):
            for idx, ds in enumerate(item["dictionary_senses"]):
                s_id = item.get("source_sense_ids", [])[idx] if idx < len(item.get("source_sense_ids", [])) else f"{item_id}-sense-{idx+1}"
                candidate_senses.append({"sense_id": s_id, "gloss": ds})
        elif item.get("meanings"):
            for m in item.get("meanings", []):
                for s in m.get("senses", []):
                    s_id = s.get("id", "")
                    glosses = s.get("glosses", [])
                    g_text = "; ".join(g.get("text", "") for g in glosses if g.get("text"))
                    if g_text:
                        candidate_senses.append({"sense_id": s_id, "gloss": g_text})

        # Primary baseline gloss
        primary_gloss = candidate_senses[0]["gloss"] if candidate_senses else item.get("display_meaning", "")

        # Collect up to 3 unique context sentences from occurrences with target word highlighted
        context_sentences = []
        for occ in item.get("occurrences", [])[:5]:
            sid = occ.get("sentence_id", "")
            stext = sentence_lookup.get(sid, "")
            if stext:
                start = occ.get("sentence_start")
                end = occ.get("sentence_end")
                if start is not None and end is not None and 0 <= start < end <= len(stext):
                    highlighted = f"{stext[:start]}【{stext[start:end]}】{stext[end:]}"
                else:
                    highlighted = stext
            else:
                bid = occ.get("block_id", "")
                highlighted = block_sentences.get(bid, "")

            if highlighted and highlighted not in context_sentences:
                context_sentences.append(highlighted)
            if len(context_sentences) >= 3:
                break

        results.append({
            "id": item_id,
            "surface": surface,
            "reading": reading,
            "candidate_senses": candidate_senses,
            "jmdict_gloss": primary_gloss,
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
    series_profile: dict[str, Any] | None = None,
    cache_dir: Path | None = None,
    progress_callback: Any = None,
) -> dict[str, str]:
    """Send study item candidates to the LLM for contextual gloss generation.

    Returns a dict mapping item_id -> contextual_gloss string.
    """
    from furiganalyse.llm_provider import LLMMessage, LLMRequest
    from furiganalyse.series_glossary import build_series_prompt_context

    if not candidates:
        return {}

    series_ctx_str = build_series_prompt_context(series_profile)
    active_system_prompt = (
        f"{SYSTEM_PROMPT}\n\nSERIES CONTEXT & LORE (from Series Memory):\n{series_ctx_str}\n"
        if series_ctx_str
        else SYSTEM_PROMPT
    )

    items_hash = _items_hash(candidates, series_ctx_str)
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

    # Check Series Memory glossary first to avoid unnecessary LLM calls
    series_glosses: dict[str, Any] = {}
    if series_profile and series_profile.get("glossary"):
        glossary_data = series_profile["glossary"]
        for c in candidates:
            s = c.get("surface", "")
            if s in glossary_data:
                entry = glossary_data[s]
                pref = entry.get("preferred_translation") or entry.get("definition") or entry.get("translation")
                if pref:
                    series_glosses[c["id"]] = {
                        "gloss": pref,
                        "selected_sense_id": None,
                        "source": "series_memory",
                    }

    if series_glosses:
        logger.info("enrich_glosses: pre-resolved %d/%d study items from Series Memory glossary", len(series_glosses), len(candidates))
        if progress_callback:
            try:
                progress_callback({
                    "log": f"Module 3: Pre-resolved {len(series_glosses)} glosses directly from Series Memory (zero LLM calls needed)",
                })
            except Exception:
                pass

    remaining_candidates = [c for c in candidates if c["id"] not in series_glosses]
    if not remaining_candidates:
        if progress_callback:
            try:
                progress_callback({
                    "log": f"Module 3 complete: All {len(candidates)} study note glosses resolved from Series Memory — zero LLM calls needed!",
                })
            except Exception:
                pass
        if cache_path:
            _save_cache(cache_path, series_glosses)
        return series_glosses

    from concurrent.futures import ThreadPoolExecutor, as_completed

    MAX_WORKERS = 3
    all_glosses: dict[str, Any] = dict(series_glosses)
    batches = [
        (idx // MAX_ITEMS_PER_BATCH + 1, remaining_candidates[idx:idx + MAX_ITEMS_PER_BATCH])
        for idx in range(0, len(remaining_candidates), MAX_ITEMS_PER_BATCH)
    ]
    total_batches = len(batches)

    context_backup_dir = (cache_dir / "context_backups") if cache_dir else Path("data/context_backups")
    context_backup_dir.mkdir(parents=True, exist_ok=True)

    def _process_single_batch(batch_info: tuple[int, list[dict[str, Any]]]) -> tuple[int, dict[str, Any], float, str]:
        batch_num, batch = batch_info
        ctx_file = context_backup_dir / f"module3_batch_{batch_num}_{items_hash}.json"
        
        # Save local context file to disk for fault tolerance and debugging
        try:
            ctx_payload = {
                "module": "module_3_contextual_glosses",
                "batch_num": batch_num,
                "total_batches": total_batches,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "status": "pending_llm",
                "items": [
                    {
                        "id": c["id"],
                        "surface": c["surface"],
                        "reading": c["reading"],
                        "context_sentences": c.get("context_sentences", []),
                    }
                    for c in batch
                ],
                "system_prompt": active_system_prompt,
            }
            ctx_file.write_text(json.dumps(ctx_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug("Could not save batch context file: %s", e)

        user_content = json.dumps(
            [
                {
                    "id": c["id"],
                    "surface": c["surface"],
                    "reading": c["reading"],
                    "candidate_senses": c.get("candidate_senses") or ([{"sense_id": "sense-1", "gloss": c.get("jmdict_gloss", "")}] if c.get("jmdict_gloss") else []),
                    "context_sentences": c["context_sentences"],
                }
                for c in batch
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

        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                start_t = time.time()
                resp = provider.generate(req)
                elapsed = time.time() - start_t
                raw = (resp.content or "").strip()
                if not raw and isinstance(getattr(resp, "raw", None), dict):
                    choices = resp.raw.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        raw = (msg.get("content") or msg.get("reasoning") or "").strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", raw)
                    raw = re.sub(r"\n?```$", "", raw.strip())
                json_match = re.search(r"\[\s*\{.*\}\s*\]", raw, re.DOTALL)
                if json_match:
                    raw = json_match.group(0)
                parsed = json.loads(raw)
                batch_results: dict[str, Any] = {}
                if isinstance(parsed, list):
                    for item in parsed:
                        item_id = item.get("id", "")
                        gloss = item.get("gloss", "")
                        selected_sense_id = item.get("selected_sense_id")
                        if item_id and gloss:
                            batch_results[item_id] = {
                                "gloss": gloss,
                                "selected_sense_id": selected_sense_id,
                            }
                if batch_results:
                    try:
                        ctx_file.write_text(json.dumps({
                            "module": "module_3_contextual_glosses",
                            "batch_num": batch_num,
                            "status": "completed",
                            "elapsed_seconds": round(elapsed, 2),
                            "results": batch_results,
                        }, ensure_ascii=False, indent=2), encoding="utf-8")
                    except Exception:
                        pass
                    return batch_num, batch_results, elapsed, raw
                raise ValueError(f"Parsed JSON produced 0 valid gloss items (raw: {raw[:100]})")
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "enrich_glosses: batch %d attempt %d/3 failed (%s)",
                    batch_num,
                    attempt,
                    exc,
                )
                if attempt < 3:
                    time.sleep(1.5 * attempt)

        raise last_exc or RuntimeError(f"Batch {batch_num} failed after 3 attempts")

    completed_batches = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(_process_single_batch, b_info): b_info
            for b_info in batches
        }

        for future in as_completed(future_map):
            b_info = future_map[future]
            batch_num = b_info[0]
            try:
                b_num, batch_results, elapsed, raw = future.result()
                all_glosses.update(batch_results)
                completed_batches += 1
                logger.info(
                    "Module 3: Batch %d/%d LLM response (%d glosses in %.1fs):\n%s",
                    b_num,
                    total_batches,
                    len(batch_results),
                    elapsed,
                    raw,
                )
                if progress_callback:
                    try:
                        progress_callback({
                            "log": f"Module 3: Batch {b_num}/{total_batches} enriched ({len(batch_results)} glosses in {elapsed:.1f}s)",
                        })
                        for item_id, res in list(batch_results.items())[:3]:
                            progress_callback({
                                "log": f"  ↳ [{item_id}] {res.get('gloss')}",
                            })
                    except Exception:
                        pass
            except Exception as exc:
                completed_batches += 1
                logger.warning("enrich_glosses: batch %d failed after 3 retries (%s)", batch_num, exc)
                if progress_callback:
                    try:
                        progress_callback({
                            "log": f"Module 3 warning: Batch {batch_num}/{total_batches} failed after 3 retries ({exc}). Using standard JMdict definitions.",
                        })
                    except Exception:
                        pass

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
    glosses: dict[str, Any],
) -> dict[str, Any]:
    """Patch annotation plan items with contextual glosses and dictionary senses.

    Returns a modified copy of the annotation plan.
    """
    if not glosses:
        return annotation_plan

    patched_items = []
    patch_count = 0
    sense_update_count = 0
    for item in annotation_plan.get("items", []):
        item_id = item.get("id", "")
        if item_id in glosses:
            item = dict(item)
            val = glosses[item_id]
            if isinstance(val, dict):
                gloss = val.get("gloss", "")
                selected_sense_id = val.get("selected_sense_id")
            else:
                gloss = str(val)
                selected_sense_id = None

            # Extract up to 3 dictionary senses from meanings if available
            dict_senses = item.get("dictionary_senses") or []
            if not dict_senses and item.get("meanings"):
                for m in item.get("meanings", []):
                    for s in m.get("senses", []):
                        g_texts = [g.get("text", "") for g in s.get("glosses", []) if g.get("text")]
                        if g_texts:
                            dict_senses.append("; ".join(g_texts))
                        if len(dict_senses) >= 3:
                            break
                    if len(dict_senses) >= 3:
                        break

            if gloss:
                item["contextual_gloss"] = gloss
                if dict_senses and item.get("kind") != "name":
                    dict_str = "\n".join(f"  {i}. {s}" for i, s in enumerate(dict_senses[:3], 1))
                    item["display_meaning"] = (
                        f"✦ Story Context:\n{gloss}\n\n"
                        f"📖 Standard Dictionary:\n{dict_str}"
                    )
                    item["dictionary_senses"] = dict_senses[:3]
                else:
                    item["display_meaning"] = f"✦ Story Context:\n{gloss}"
                patch_count += 1

            # Update selected_sense_id if a valid matching sense was disambiguated
            if selected_sense_id and selected_sense_id in item.get("source_sense_ids", []):
                item["selected_sense_id"] = selected_sense_id
                sense_update_count += 1

        patched_items.append(item)

    logger.info(
        "apply_gloss_enrichments: enriched %d/%d study items with contextual glosses (%d senses disambiguated)",
        patch_count,
        len(patched_items),
        sense_update_count,
    )

    result = dict(annotation_plan)
    result["items"] = patched_items
    return result
