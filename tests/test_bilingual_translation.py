from furiganalyse.bilingual_context import (
    BookContextData,
    CharacterProfile,
    GlossaryItem,
)
from furiganalyse.bilingual_translation import (
    TranslationCache,
    translate_chapter,
)
from furiganalyse.llm_provider import MockLLMProvider


def test_translate_chapter_with_context_and_caching(tmp_path):
    cache = TranslationCache(cache_dir=tmp_path / "cache")

    mock_translation_response = [
        {
            "block_id": "ch-0001-b-0001",
            "english_translation": "Tatsuya activated his CAD with precision.",
            "footnotes": ["CAD stands for Casting Assistant Device."],
        },
        {
            "block_id": "ch-0001-b-0002",
            "english_translation": "“As expected of my brother,” Miyuki whispered.",
            "footnotes": [],
        },
    ]

    provider = MockLLMProvider(default_response=mock_translation_response)

    context = BookContextData(
        title="Magic High School",
        characters={
            "達也": CharacterProfile(kanji="達也", romanized="Tatsuya Shiba", gender="male"),
            "深雪": CharacterProfile(kanji="深雪", romanized="Miyuki Shiba", gender="female"),
        },
        glossary={
            "ＣＡＤ": GlossaryItem(japanese="ＣＡＤ", preferred_translation="CAD"),
        },
    )

    chapter_dict = {
        "id": "ch-0001",
        "title": "Chapter 1",
        "blocks": [
            {
                "id": "ch-0001-b-0001",
                "sentences": [{"text": "達也はＣＡＤを正確に起動した。"}],
            },
            {
                "id": "ch-0001-b-0002",
                "sentences": [{"text": "「さすがはお兄様」と深雪は囁いた。"}],
            },
        ],
    }

    # 1. First translation call (should call provider and cache)
    trans_ch1 = translate_chapter(chapter_dict, context, provider=provider, cache=cache, batch_size=5)

    assert len(trans_ch1.paragraphs) == 2
    assert trans_ch1.paragraphs[0].english_translation == "Tatsuya activated his CAD with precision."
    assert trans_ch1.paragraphs[0].footnotes == ["CAD stands for Casting Assistant Device."]
    assert trans_ch1.cache_hits == 0
    assert len(provider.call_history) == 1

    # 2. Second translation call (should hit cache without provider call)
    trans_ch2 = translate_chapter(chapter_dict, context, provider=provider, cache=cache, batch_size=5)

    assert len(trans_ch2.paragraphs) == 2
    assert trans_ch2.cache_hits == 1
    assert len(provider.call_history) == 1  # No additional API call made!
