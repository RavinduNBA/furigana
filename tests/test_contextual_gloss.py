import pytest
from unittest.mock import MagicMock
from furiganalyse.contextual_gloss import (
    collect_gloss_candidates,
    enrich_glosses,
    apply_gloss_enrichments,
)
from furiganalyse.llm_provider import LLMResponse


def test_collect_gloss_candidates():
    plan = {
        "items": [
            {
                "id": "item-001",
                "surface": "劣等生",
                "reading": "れっとうせい",
                "meanings": [{"senses": [{"glosses": [{"text": "poor student"}]}]}],
                "occurrences": [{"block_id": "b1"}],
            }
        ]
    }
    canonical_book = {
        "chapters": [
            {
                "blocks": [
                    {
                        "id": "b1",
                        "sentences": [{"text": "彼は魔法科高校の劣等生だ。"}],
                    }
                ]
            }
        ]
    }

    candidates = collect_gloss_candidates(plan, canonical_book)
    assert len(candidates) == 1
    assert candidates[0]["id"] == "item-001"
    assert candidates[0]["surface"] == "劣等生"
    assert candidates[0]["jmdict_gloss"] == "poor student"
    assert "彼は魔法科高校の劣等生だ。" in candidates[0]["context_sentences"][0]


def test_enrich_glosses_with_mock_provider(tmp_path):
    mock_provider = MagicMock()
    mock_provider.generate.return_value = LLMResponse(
        content='[{"id": "item-001", "gloss": "Course 2 student at First High (Weed), subject to discrimination despite exceptional practical capabilities."}]',
        prompt_tokens=50,
        completion_tokens=25,
        model="test-model",
    )

    candidates = [
        {
            "id": "item-001",
            "surface": "劣等生",
            "reading": "れっとうせい",
            "jmdict_gloss": "poor student",
            "context_sentences": ["彼は魔法科高校の劣等生だ。"],
        }
    ]

    glosses = enrich_glosses(candidates, mock_provider, model="test-model", cache_dir=tmp_path)
    assert "item-001" in glosses
    assert "Weed" in glosses["item-001"]


def test_apply_gloss_enrichments():
    plan = {
        "items": [
            {
                "id": "item-001",
                "surface": "劣等生",
                "display_meaning": "poor student",
            }
        ]
    }
    glosses = {
        "item-001": "Course 2 reserve student (Weed)."
    }

    enriched = apply_gloss_enrichments(plan, glosses)
    assert enriched["items"][0]["contextual_gloss"] == "Course 2 reserve student (Weed)."
    assert enriched["items"][0]["display_meaning"] == "Course 2 reserve student (Weed)."
