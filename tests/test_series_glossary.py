import pytest
from pathlib import Path
import tempfile
import furiganalyse.series_glossary as sg


def test_series_glossary_lifecycle(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(sg, "DEFAULT_STORAGE_DIR", Path(tmpdir))

        # Save new profile
        saved = sg.save_series_profile(
            series_id="mahouka",
            title="The Irregular at Magic High School",
            characters={
                "司波達也": {"kanji": "司波達也", "reading": "しばたつや", "romanized": "Tatsuya Shiba"},
                "司波深雪": {"kanji": "司波深雪", "reading": "しばみゆき", "romanized": "Miyuki Shiba"},
            },
            glossary={
                "魔法式": {"japanese": "魔法式", "preferred_translation": "Magic Activation Sequence"}
            },
            ruby_overrides={"十師族": "じゅうしぞく"},
            volume_name="Volume 1"
        )
        assert saved["series_id"] == "mahouka"
        assert len(saved["characters"]) == 2

        # List profiles
        profiles = sg.list_series_profiles()
        assert len(profiles) == 1
        assert profiles[0]["series_id"] == "mahouka"
        assert profiles[0]["character_count"] == 2
        assert profiles[0]["glossary_count"] == 1

        # Load profile
        loaded = sg.load_series_profile("mahouka")
        assert loaded is not None
        assert "司波達也" in loaded["characters"]

        # Merge update from Volume 2
        sg.save_series_profile(
            series_id="mahouka",
            title="The Irregular at Magic High School",
            characters={
                "七草真由美": {"kanji": "七草真由美", "reading": "さえぐさまゆみ", "romanized": "Mayumi Saegusa"}
            },
            volume_name="Volume 2"
        )
        loaded2 = sg.load_series_profile("mahouka")
        assert len(loaded2["characters"]) == 3
        assert "Volume 1" in loaded2["volumes_processed"]
        assert "Volume 2" in loaded2["volumes_processed"]

        # Apply to vocabulary
        vocab = {
            "candidates": [
                {"id": "c1", "surface": "十師族", "reading": "じゅっしぞく", "publisher_ruby_id": None},
                {"id": "c2", "surface": "学校", "reading": "がっこう", "publisher_ruby_id": None},
            ],
            "name_occurrences": [
                {"id": "n1", "surface": "司波達也", "reading": None, "publisher_ruby_id": None},
            ]
        }
        patched, count = sg.apply_series_profile_to_vocabulary(loaded2, vocab)
        assert count == 2
        assert patched["candidates"][0]["reading"] == "じゅうしぞく"
        assert patched["name_occurrences"][0]["reading"] == "しばたつや"

        # Prompt Injection Context Builder test
        prompt_ctx = sg.build_series_prompt_context(loaded2)
        assert "SERIES TITLE: The Irregular at Magic High School" in prompt_ctx
        assert "司波達也 (しばたつや / Tatsuya Shiba)" in prompt_ctx
        assert "魔法式" in prompt_ctx
        assert "十師族 【じゅうしぞく】" in prompt_ctx

        # Delete
        assert sg.delete_series_profile("mahouka") is True
        assert sg.load_series_profile("mahouka") is None


def test_series_prompt_context_empty():
    assert sg.build_series_prompt_context(None) == ""
    assert sg.build_series_prompt_context({}) == ""


def test_suggest_series_name():
    res1 = sg.suggest_series_name("魔法科高校の劣等生 3.epub")
    assert res1["clean_title"] == "魔法科高校の劣等生"
    assert res1["volume"] == "Volume 3"
    assert res1["slug"] == "魔法科高校の劣等生"

    res2 = sg.suggest_series_name("[Novel] Sword Art Online - Vol 03 (JAP).epub")
    assert res2["clean_title"] == "Sword Art Online"
    assert res2["volume"] == "Volume 3"
    assert res2["slug"] == "sword-art-online"

    res3 = sg.suggest_series_name("ダンジョンに出会いを求めるのは間違っているだろうか 第14巻 - Guided.epub")
    assert res3["clean_title"] == "ダンジョンに出会いを求めるのは間違っているだろうか"
    assert res3["volume"] == "Volume 14"


def test_find_matching_series_profile():
    profiles = [
        {"series_id": "mahouka", "title": "魔法科高校の劣等生", "character_count": 20, "glossary_count": 30},
        {"series_id": "sao", "title": "Sword Art Online", "character_count": 10, "glossary_count": 15},
    ]

    # Substring / title match
    matched = sg.find_matching_series_profile("魔法科高校の劣等生 04.epub", existing_profiles=profiles)
    assert matched["is_existing"] is True
    assert matched["series_id"] == "mahouka"
    assert matched["volume_name"] == "Volume 4"

    # New series suggestion
    unmatched = sg.find_matching_series_profile("Overlord Vol. 01.epub", existing_profiles=profiles)
    assert unmatched["is_existing"] is False
    assert unmatched["series_id"] == "overlord"
    assert unmatched["title"] == "Overlord"
    assert unmatched["volume_name"] == "Volume 1"
