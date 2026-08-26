
from furiganalyse.bilingual_context import (
    BookContextData,
    CharacterProfile,
    GlossaryItem,
    ChapterOutline,
    build_book_context,
)
from furiganalyse.llm_provider import MockLLMProvider


def test_book_context_serialization_and_deserialization(tmp_path):
    ctx = BookContextData(
        title="Test Light Novel",
        characters={
            "達也": CharacterProfile(
                kanji="達也",
                romanized="Tatsuya Shiba",
                role="Protagonist",
                gender="male",
                aliases=["Onii-sama"],
                relationships={"深雪": "Younger sister"},
            )
        },
        glossary={
            "起動式": GlossaryItem(
                japanese="起動式",
                preferred_translation="Activation Sequence",
                definition="Spell formula stored in CAD",
                category="magic",
            )
        },
        chapter_outlines={
            "ch-0001": ChapterOutline(
                chapter_id="ch-0001",
                title="Enrollment",
                summary="Tatsuya and Miyuki arrive at First High.",
                active_characters=["達也", "深雪"],
            )
        },
    )

    path = tmp_path / "book_context.json"
    ctx.save(path)
    loaded = BookContextData.load(path)

    assert loaded.title == "Test Light Novel"
    assert loaded.characters["達也"].romanized == "Tatsuya Shiba"
    assert loaded.glossary["起動式"].preferred_translation == "Activation Sequence"
    assert loaded.chapter_outlines["ch-0001"].active_characters == ["達也", "深雪"]


def test_build_book_context_with_mock_llm():
    mock_data = {
        "title": "The Irregular at Magic High School",
        "characters": {
            "司波達也": {
                "kanji": "司波達也",
                "romanized": "Tatsuya Shiba",
                "role": "Protagonist / Course 2 Student",
                "gender": "male",
                "aliases": ["Tatsuya"],
                "relationships": {"司波深雪": "Sister"},
            }
        },
        "glossary": {
            "魔法師": {
                "japanese": "魔法師",
                "preferred_translation": "Magician",
                "definition": "Modern magic practitioner",
                "category": "magic",
            }
        },
        "chapter_outlines": {
            "ch-0001": {
                "chapter_id": "ch-0001",
                "title": "Prologue",
                "summary": "Introduction to magic in 2095.",
                "active_characters": ["司波達也"],
            }
        },
    }

    provider = MockLLMProvider(default_response=mock_data)

    canonical_book = {
        "schema_version": 2,
        "title": "魔法科高校の劣等生",
        "chapters": [
            {
                "id": "ch-0001",
                "title": "Chapter 1",
                "blocks": [{"sentences": [{"text": "達也は歩いた。"}]}],
            }
        ],
    }
    vocabulary_report = {
        "schema_version": 4,
        "tokens": [],
        "candidates": [{"token_id": "t1", "surface": "達也", "part_of_speech": "名詞,人名"}],
        "expressions": [{"surface": "魔法師"}],
    }

    context = build_book_context(canonical_book, vocabulary_report, provider=provider)

    assert context.characters["司波達也"].romanized == "Tatsuya Shiba"
    assert context.glossary["魔法師"].preferred_translation == "Magician"
    assert len(provider.call_history) == 1


def test_build_book_context_fallback_without_llm():
    canonical_book = {
        "schema_version": 2,
        "title": "Fallback Novel",
        "chapters": [{"id": "ch-0001", "title": "Ch 1", "blocks": []}],
    }
    vocabulary_report = {
        "schema_version": 4,
        "tokens": [],
        "candidates": [{"token_id": "t1", "surface": "美雪", "part_of_speech": "名詞,固有名詞,人名"}],
        "expressions": [{"surface": "魔法大学"}],
    }

    context = build_book_context(canonical_book, vocabulary_report, provider=None)

    assert "美雪" in context.characters
    assert "魔法大学" in context.glossary
