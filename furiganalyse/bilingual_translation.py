"""Pass 2 Context-Injected Stateful Translation Engine with Cache and Schema Validation."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from furiganalyse.bilingual_context import BookContextData
from furiganalyse.llm_provider import BaseLLMProvider, LLMMessage, LLMRequest

logger = logging.getLogger(__name__)

TRANSLATION_PROMPT_VERSION = "v1.0"


@dataclass
class TranslationParagraph:
    block_id: str
    japanese_sentences: list[str]
    english_translation: str
    footnotes: list[str] = field(default_factory=list)


@dataclass
class TranslationChapter:
    chapter_id: str
    title: str
    paragraphs: list[TranslationParagraph] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_hits: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter_id": self.chapter_id,
            "title": self.title,
            "paragraphs": [asdict(p) for p in self.paragraphs],
            "stats": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "cache_hits": self.cache_hits,
            },
        }


class TranslationCache:
    """Persistent on-disk cache for translated paragraph batches."""

    def __init__(self, cache_dir: str | Path = "/tmp/furiganalyse_translation_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, source_text: str, context_hash: str, model_name: str) -> str:
        payload = f"{TRANSLATION_PROMPT_VERSION}:{model_name}:{context_hash}:{source_text}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, source_text: str, context_hash: str, model_name: str) -> list[dict[str, Any]] | None:
        key = self._cache_key(source_text, context_hash, model_name)
        target = self.cache_dir / f"{key}.json"
        if target.exists():
            try:
                return json.loads(target.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def set(self, source_text: str, context_hash: str, model_name: str, result: list[dict[str, Any]]) -> None:
        key = self._cache_key(source_text, context_hash, model_name)
        target = self.cache_dir / f"{key}.json"
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


TRANSLATION_SYSTEM_PROMPT = """You are a professional literary translator specializing in Japanese light novels.
Translate the provided Japanese paragraph batch into smooth, engaging, and faithful English prose.

TRANSLATION RULES:
1. Subject & Pronoun Resolution: In Japanese, subjects and pronouns are often omitted. Use the provided Cast Sheet to correctly resolve who is speaking and acting.
2. Terminology Consistency: Strictly adhere to the provided World Glossary for magic, ranks, fictional terms, and character names.
3. Natural Literary Flow: Produce high-quality prose with appropriate dialogue cadence and emotional nuance without adding unprompted exposition.
4. Schema Adherence: Return a valid JSON array of objects corresponding 1-to-1 with the provided paragraph blocks.

RESPONSE JSON FORMAT:
[
  {
    "block_id": "ch-0001-b-0001",
    "english_translation": "English translated paragraph...",
    "footnotes": []
  }
]
"""


def translate_chapter(
    chapter_dict: dict[str, Any],
    book_context: BookContextData,
    provider: BaseLLMProvider,
    cache: TranslationCache | None = None,
    batch_size: int = 8,
    model: str = "gpt-4o-mini",
) -> TranslationChapter:
    """Translates an entire canonical chapter in coherent paragraph batches with context injection."""
    chapter_id = chapter_dict.get("id", "ch-0001")
    title = chapter_dict.get("title", chapter_id)
    blocks = chapter_dict.get("blocks", [])

    outline = book_context.chapter_outlines.get(chapter_id)
    active_characters = outline.active_characters if outline else []

    # Filter glossary & cast relevant to this chapter or general
    relevant_characters = {
        k: v for k, v in book_context.characters.items()
        if not active_characters or k in active_characters
    }
    relevant_glossary = book_context.glossary

    # Build context snapshot string & hash
    cast_str = "\n".join(
        f"- {k} ({v.romanized}): {v.role}, gender: {v.gender}. Aliases: {', '.join(v.aliases)}"
        for k, v in list(relevant_characters.items())[:15]
    )
    glossary_str = "\n".join(
        f"- {k} -> {v.preferred_translation} ({v.definition})"
        for k, v in list(relevant_glossary.items())[:25]
    )
    context_text = f"CAST SHEET:\n{cast_str}\n\nWORLD GLOSSARY:\n{glossary_str}"
    context_hash = hashlib.sha256(context_text.encode("utf-8")).hexdigest()[:16]

    translated_paragraphs: list[TranslationParagraph] = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    cache_hits = 0

    previous_buffer = ""

    # Process in batches
    for i in range(0, len(blocks), batch_size):
        batch_blocks = blocks[i : i + batch_size]
        batch_input_list = []
        raw_text_combined = ""

        for b in batch_blocks:
            bid = b.get("id", "")
            s_texts = [s.get("text", "") for s in b.get("sentences", [])]
            combined = "".join(s_texts).strip()
            if combined:
                batch_input_list.append({"block_id": bid, "japanese": combined, "sentences": s_texts})
                raw_text_combined += f"[{bid}] {combined}\n"

        if not batch_input_list:
            continue

        # Check Cache
        cached_result = cache.get(raw_text_combined, context_hash, model) if cache else None
        if cached_result is not None:
            cache_hits += 1
            for item in cached_result:
                # Find matching original sentences
                matched_b = next((x for x in batch_input_list if x["block_id"] == item.get("block_id")), None)
                orig_sentences = matched_b["sentences"] if matched_b else []
                translated_paragraphs.append(
                    TranslationParagraph(
                        block_id=item.get("block_id", ""),
                        japanese_sentences=orig_sentences,
                        english_translation=item.get("english_translation", ""),
                        footnotes=item.get("footnotes", []),
                    )
                )
            if cached_result:
                previous_buffer = cached_result[-1].get("english_translation", "")[-200:]
            continue

        # Construct User Prompt
        user_prompt = (
            f"{context_text}\n\n"
            f"PREVIOUS SCENE CONTEXT:\n{previous_buffer or '(Beginning of scene)'}\n\n"
            f"PARAGRAPHS TO TRANSLATE:\n"
            f"{json.dumps(batch_input_list, ensure_ascii=False, indent=2)}"
        )

        req = LLMRequest(
            messages=[
                LLMMessage(role="system", content=TRANSLATION_SYSTEM_PROMPT),
                LLMMessage(role="user", content=user_prompt),
            ],
            temperature=0.3,
            model=model,
            response_json=True,
        )

        try:
            resp = provider.generate(req)
            total_prompt_tokens += resp.prompt_tokens
            total_completion_tokens += resp.completion_tokens
            raw_data = resp.json_data()

            batch_results = []
            if isinstance(raw_data, list):
                batch_results = raw_data
            elif isinstance(raw_data, dict):
                # Check for wrapped lists e.g. {"translations": [...]}
                for v in raw_data.values():
                    if isinstance(v, list):
                        batch_results = v
                        break

            # Cache the raw result
            if cache and batch_results:
                cache.set(raw_text_combined, context_hash, model, batch_results)

            for item in batch_results:
                bid = item.get("block_id", "")
                eng = item.get("english_translation", "")
                fns = item.get("footnotes", [])
                matched_b = next((x for x in batch_input_list if x["block_id"] == bid), None)
                orig_sentences = matched_b["sentences"] if matched_b else []
                translated_paragraphs.append(
                    TranslationParagraph(
                        block_id=bid,
                        japanese_sentences=orig_sentences,
                        english_translation=eng,
                        footnotes=fns,
                    )
                )

            if batch_results:
                previous_buffer = batch_results[-1].get("english_translation", "")[-200:]

        except Exception as exc:
            logger.warning(f"Translation batch failed for chapter {chapter_id}, block range {i}-{i+batch_size}: {exc}")
            # Fallback to plain placeholder so whole book doesn't fail
            for b_in in batch_input_list:
                translated_paragraphs.append(
                    TranslationParagraph(
                        block_id=b_in["block_id"],
                        japanese_sentences=b_in["sentences"],
                        english_translation=f"[{b_in['japanese']}]",
                        footnotes=["Translation fallback"],
                    )
                )

    return TranslationChapter(
        chapter_id=chapter_id,
        title=title,
        paragraphs=translated_paragraphs,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        cache_hits=cache_hits,
    )
