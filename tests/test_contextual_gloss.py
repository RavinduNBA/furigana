import pytest
from unittest.mock import MagicMock
from furiganalyse.contextual_gloss import (
    collect_gloss_candidates,
    enrich_glosses,
    apply_gloss_enrichments,
)
from furiganalyse.llm_provider import LLMResponse


def test_collect_gloss_candidates_with_highlighting_and_senses():
    plan = {
        "items": [
            {
                "id": "item-tatemae",
                "surface": "建前",
                "reading": "たてまえ",
                "source_sense_ids": ["jmdict-1524230-sense-0001", "jmdict-1524230-sense-0002"],
                "selected_sense_id": "jmdict-1524230-sense-0001",
                "meanings": [
                    {
                        "senses": [
                            {
                                "id": "jmdict-1524230-sense-0001",
                                "glosses": [{"text": "framework of a building; framing ceremony"}],
                            },
                            {
                                "id": "jmdict-1524230-sense-0002",
                                "glosses": [{"text": "official stance; public position; stated principle; pretense"}],
                            },
                        ]
                    }
                ],
                "occurrences": [
                    {
                        "sentence_id": "s-001",
                        "sentence_start": 18,
                        "sentence_end": 20,
                    }
                ],
            }
        ]
    }
    canonical_book = {
        "chapters": [
            {
                "blocks": [
                    {
                        "id": "b1",
                        "sentences": [
                            {
                                "id": "s-001",
                                "text": "魔法教育に、教育機会の均等などという建前は存在しない。",
                            }
                        ],
                    }
                ]
            }
        ]
    }

    candidates = collect_gloss_candidates(plan, canonical_book)
    assert len(candidates) == 1
    c = candidates[0]
    assert c["id"] == "item-tatemae"
    assert c["surface"] == "建前"
    assert len(c["candidate_senses"]) == 2
    assert c["candidate_senses"][0]["sense_id"] == "jmdict-1524230-sense-0001"
    assert c["candidate_senses"][1]["sense_id"] == "jmdict-1524230-sense-0002"
    assert "魔法教育に、教育機会の均等などという【建前】は存在しない。" in c["context_sentences"]


def test_enrich_glosses_with_mock_provider(tmp_path):
    mock_provider = MagicMock()
    mock_provider.generate.return_value = LLMResponse(
        content='[{"id": "item-tatemae", "gloss": "Official stance / pretense (the facade of equal educational opportunity).", "selected_sense_id": "jmdict-1524230-sense-0002"}]',
        prompt_tokens=50,
        completion_tokens=25,
        model="test-model",
    )

    candidates = [
        {
            "id": "item-tatemae",
            "surface": "建前",
            "reading": "たてまえ",
            "candidate_senses": [
                {"sense_id": "jmdict-1524230-sense-0001", "gloss": "framework of a building"},
                {"sense_id": "jmdict-1524230-sense-0002", "gloss": "official stance; public position; stated principle; pretense"},
            ],
            "jmdict_gloss": "framework of a building",
            "context_sentences": ["魔法教育に、教育機会の均等などという【建前】は存在しない。"],
        }
    ]

    glosses = enrich_glosses(candidates, mock_provider, model="test-model", cache_dir=tmp_path)
    assert "item-tatemae" in glosses
    assert glosses["item-tatemae"]["gloss"] == "Official stance / pretense (the facade of equal educational opportunity)."
    assert glosses["item-tatemae"]["selected_sense_id"] == "jmdict-1524230-sense-0002"


def test_apply_gloss_enrichments_with_sense_disambiguation():
    plan = {
        "items": [
            {
                "id": "item-tatemae",
                "surface": "建前",
                "source_sense_ids": ["jmdict-1524230-sense-0001", "jmdict-1524230-sense-0002"],
                "selected_sense_id": "jmdict-1524230-sense-0001",
                "display_meaning": "framework of a building",
            }
        ]
    }
    glosses = {
        "item-tatemae": {
            "gloss": "Official stance / pretense (the facade of equal educational opportunity).",
            "selected_sense_id": "jmdict-1524230-sense-0002",
        }
    }

    enriched = apply_gloss_enrichments(plan, glosses)
    item = enriched["items"][0]
    assert item["contextual_gloss"] == "Official stance / pretense (the facade of equal educational opportunity)."
    assert item["display_meaning"] == "Official stance / pretense (the facade of equal educational opportunity)."
    assert item["selected_sense_id"] == "jmdict-1524230-sense-0002"
