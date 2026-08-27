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

        # Delete
        assert sg.delete_series_profile("mahouka") is True
        assert sg.load_series_profile("mahouka") is None
