"""Book-wide context discovery: Cast sheet, World glossary, and Chapter outlines."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from furiganalyse.llm_provider import BaseLLMProvider, LLMMessage, LLMRequest

SCHEMA_VERSION = 1


@dataclass
class CharacterProfile:
    kanji: str
    romanized: str
    role: str = "Supporting Character"
    gender: str = "unknown"  # male, female, neutral, unknown
    aliases: list[str] = field(default_factory=list)
    relationships: dict[str, str] = field(default_factory=dict)


@dataclass
class GlossaryItem:
    japanese: str
    preferred_translation: str
    definition: str = ""
    category: str = "general"  # magic, tech, organization, rank, general


@dataclass
class ChapterOutline:
    chapter_id: str
    title: str = ""
    summary: str = ""
    active_characters: list[str] = field(default_factory=list)


@dataclass
class BookContextData:
    schema_version: int = SCHEMA_VERSION
    title: str = ""
    characters: dict[str, CharacterProfile] = field(default_factory=dict)
    glossary: dict[str, GlossaryItem] = field(default_factory=dict)
    chapter_outlines: dict[str, ChapterOutline] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "title": self.title,
            "characters": {k: asdict(v) for k, v in self.characters.items()},
            "glossary": {k: asdict(v) for k, v in self.glossary.items()},
            "chapter_outlines": {k: asdict(v) for k, v in self.chapter_outlines.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BookContextData:
        characters = {
            k: CharacterProfile(**v) for k, v in data.get("characters", {}).items()
        }
        glossary = {
            k: GlossaryItem(**v) for k, v in data.get("glossary", {}).items()
        }
        chapter_outlines = {
            k: ChapterOutline(**v) for k, v in data.get("chapter_outlines", {}).items()
        }
        return cls(
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            title=data.get("title", ""),
            characters=characters,
            glossary=glossary,
            chapter_outlines=chapter_outlines,
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> BookContextData:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)


def extract_context_candidates(canonical_book: dict[str, Any], vocabulary_report: dict[str, Any]) -> dict[str, Any]:
    """Deterministically extracts candidate characters, publisher terms, and frequent compounds."""
    name_counts = Counter()
    ruby_terms = Counter()
    compound_counts = Counter()

    candidates = vocabulary_report.get("candidates", [])

    # Extract name candidates
    for c in candidates:
        pos = c.get("part_of_speech") or ""
        if "人名" in pos or "固有名詞" in pos:
            name_counts[c["surface"]] += 1
        elif c.get("publisher_ruby_id"):
            ruby_terms[c["surface"]] += 1

    # Extract expressions
    expressions = vocabulary_report.get("expressions", [])
    for expr in expressions:
        compound_counts[expr["surface"]] += 1

    return {
        "candidate_names": [name for name, _ in name_counts.most_common(50)],
        "ruby_terms": [term for term, _ in ruby_terms.most_common(50)],
        "frequent_expressions": [expr for expr, _ in compound_counts.most_common(50)],
    }


DISCOVERY_SYSTEM_PROMPT = """You are an expert literary Japanese-to-English translator and world-building analyst specializing in light novels.
Analyze the provided Japanese text samples, proper names, and specialized terminology to synthesize a structured Book Context Sheet.

Your response MUST be a valid JSON object matching this schema:
{
  "title": "Novel Title in English",
  "characters": {
    "KanjiName": {
      "kanji": "KanjiName",
      "romanized": "English Romanized Name",
      "role": "Role / Description (e.g. Protagonist, younger sister, student council president)",
      "gender": "male | female | unknown",
      "aliases": ["Nickname", "Honorific form"],
      "relationships": {"OtherCharacter": "Relationship description"}
    }
  },
  "glossary": {
    "JapaneseTerm": {
      "japanese": "JapaneseTerm",
      "preferred_translation": "Standard English translation",
      "definition": "Brief 1-sentence world-building definition or usage context",
      "category": "magic | tech | organization | rank | general"
    }
  },
  "chapter_outlines": {
    "ch-0001": {
      "chapter_id": "ch-0001",
      "title": "Chapter Title",
      "summary": "1-2 sentence overview of key events and setting",
      "active_characters": ["Character1", "Character2"]
    }
  }
}
"""


def build_book_context(
    canonical_book: dict[str, Any],
    vocabulary_report: dict[str, Any],
    provider: BaseLLMProvider | None = None,
    overrides: dict[str, Any] | None = None,
    model: str | None = None,
    progress_callback: Any = None,
    series_profile: dict[str, Any] | None = None,
) -> BookContextData:
    """Builds a structured BookContextData using LLM discovery with fallback to rule-based indexing."""
    from furiganalyse.series_glossary import build_series_prompt_context

    candidates = extract_context_candidates(canonical_book, vocabulary_report)
    title = canonical_book.get("title", "Japanese Novel")
    series_ctx_str = build_series_prompt_context(series_profile) if series_profile else ""

    context_data: BookContextData | None = None

    if provider is not None:
        # Sample first 3 chapters for synopsis & scene outline
        sample_texts = []
        for ch in canonical_book.get("chapters", [])[:5]:
            ch_text = []
            for b in ch.get("blocks", [])[:10]:
                for s in b.get("sentences", []):
                    ch_text.append(s.get("text", ""))
            sample_texts.append(f"--- Chapter: {ch.get('id')} ({ch.get('title', '')}) ---\n" + "\n".join(ch_text[:15]))

        sample_names = ", ".join(candidates["candidate_names"][:10])
        sample_terms = ", ".join(candidates["ruby_terms"][:10])
        if progress_callback:
            try:
                progress_callback({
                    "stage": "bilingual-translation",
                    "translation_current_chapter": "Pass 1: Cast & Terminology Discovery",
                    "translation_latest_japanese": f"Candidate Names: {sample_names}\nSpecialized Terms: {sample_terms}",
                    "translation_latest_english": "Extracting character roles, romanization, and world terminology…",
                    "log": f"Pass 1: Analyzing {len(candidates['candidate_names'])} names and {len(candidates['ruby_terms'])} ruby terms with {model or 'LLM'}…",
                })
            except Exception:
                pass

        user_content_parts = [f"Title: {title}\n"]
        if series_ctx_str:
            user_content_parts.append(f"ESTABLISHED SERIES CONTEXT & CAST (from Series Memory):\n{series_ctx_str}\n")
        user_content_parts.extend([
            f"Candidate Proper Names: {', '.join(candidates['candidate_names'][:30])}\n",
            f"Publisher Ruby / Specialized Terms: {', '.join(candidates['ruby_terms'][:30])}\n",
            f"Frequent Expressions: {', '.join(candidates['frequent_expressions'][:30])}\n\n",
            f"Text Excerpts:\n" + "\n\n".join(sample_texts),
        ])
        user_content = "\n".join(user_content_parts)

        accumulated_stream: list[str] = []
        import time
        last_update = [time.monotonic()]

        def on_token(delta: str) -> None:
            accumulated_stream.append(delta)
            now = time.monotonic()
            if progress_callback and (now - last_update[0] >= 0.3 or any(c in delta for c in "}\n")):
                last_update[0] = now
                raw_str = "".join(accumulated_stream)
                try:
                    progress_callback({
                        "stage": "bilingual-translation",
                        "translation_current_chapter": "Pass 1: Cast & Terminology Discovery",
                        "translation_latest_japanese": f"Candidate Names: {sample_names}\nSpecialized Terms: {sample_terms}",
                        "translation_latest_english": raw_str[-300:] or "Analyzing context…",
                    })
                except Exception:
                    pass

        try:
            req = LLMRequest(
                messages=[
                    LLMMessage(role="system", content=DISCOVERY_SYSTEM_PROMPT),
                    LLMMessage(role="user", content=user_content),
                ],
                temperature=0.2,
                model=model,
                response_json=True,
            )
            resp = provider.generate(req, stream_callback=on_token)
            raw_json = resp.json_data()
            context_data = BookContextData.from_dict(raw_json)
            context_data.title = title
        except Exception:
            # Fall back to rule-based below
            context_data = None

    if context_data is None:
        # Rule-based fallback
        characters = {}
        for name in candidates["candidate_names"][:20]:
            characters[name] = CharacterProfile(kanji=name, romanized=name)

        glossary = {}
        for term in candidates["ruby_terms"][:30] + candidates["frequent_expressions"][:30]:
            glossary[term] = GlossaryItem(japanese=term, preferred_translation=term)

        chapter_outlines = {}
        for ch in canonical_book.get("chapters", []):
            cid = ch.get("id", "")
            chapter_outlines[cid] = ChapterOutline(
                chapter_id=cid,
                title=ch.get("title", cid),
                summary="Chapter content",
                active_characters=[],
            )

        context_data = BookContextData(
            schema_version=SCHEMA_VERSION,
            title=title,
            characters=characters,
            glossary=glossary,
            chapter_outlines=chapter_outlines,
        )

    # Pre-seed / merge series profile cast & terms if provided
    if series_profile:
        for name, char in series_profile.get("characters", {}).items():
            if isinstance(char, dict) and name not in context_data.characters:
                context_data.characters[name] = CharacterProfile(
                    kanji=name,
                    romanized=char.get("romanized") or char.get("reading") or name,
                    role=char.get("role") or "Character",
                    gender=char.get("gender") or "unknown",
                    aliases=char.get("aliases") or [],
                )
        for term, item in series_profile.get("glossary", {}).items():
            if isinstance(item, dict) and term not in context_data.glossary:
                context_data.glossary[term] = GlossaryItem(
                    japanese=term,
                    preferred_translation=item.get("preferred_translation") or item.get("translation") or term,
                    definition=item.get("definition") or "",
                    category=item.get("category") or "general",
                )

    # Apply manual user overrides if supplied
    if overrides:
        for k, v in overrides.get("characters", {}).items():
            if k in context_data.characters:
                for attr, val in v.items():
                    setattr(context_data.characters[k], attr, val)
            else:
                context_data.characters[k] = CharacterProfile(**v)
        for k, v in overrides.get("glossary", {}).items():
            if k in context_data.glossary:
                for attr, val in v.items():
                    setattr(context_data.glossary[k], attr, val)
            else:
                context_data.glossary[k] = GlossaryItem(**v)

    return context_data
