import pytest
from furiganalyse.ruby_override import (
    extract_publisher_ruby_map,
    apply_publisher_ruby_propagation,
)


def test_extract_publisher_ruby_map_basic():
    book = {
        "chapters": [
            {
                "blocks": [
                    {
                        "publisher_ruby": [
                            {"surface": "魔法式", "reading": "まほうしき"},
                            {"surface": "司波", "reading": "しば"},
                        ]
                    },
                    {
                        "publisher_ruby": [
                            {"surface": "魔法式", "reading": "まほうしき"},
                            {"surface": "深雪", "reading": "みゆき"},
                        ]
                    }
                ]
            }
        ]
    }
    ruby_map = extract_publisher_ruby_map(book)
    assert ruby_map["魔法式"] == "まほうしき"
    assert ruby_map["司波"] == "しば"
    assert ruby_map["深雪"] == "みゆき"


def test_extract_publisher_ruby_map_majority_vote():
    book = {
        "chapters": [
            {
                "blocks": [
                    {
                        "publisher_ruby": [
                            {"surface": "術式", "reading": "じゅつしき"},
                            {"surface": "術式", "reading": "じゅつしき"},
                            {"surface": "術式", "reading": "スペル"},
                        ]
                    }
                ]
            }
        ]
    }
    ruby_map = extract_publisher_ruby_map(book)
    assert ruby_map["術式"] == "じゅつしき"


def test_apply_publisher_ruby_propagation():
    ruby_map = {"魔法式": "まほうしき", "達也": "たつや"}
    vocabulary = {
        "candidates": [
            {"id": "c1", "surface": "魔法式", "reading": None, "publisher_ruby_id": None},
            {"id": "c2", "surface": "魔法式", "reading": "まほうしき", "publisher_ruby_id": "r1"},
            {"id": "c3", "surface": "学校", "reading": "がっこう", "publisher_ruby_id": None},
        ],
        "name_occurrences": [
            {"id": "n1", "surface": "達也", "reading": "みちや", "publisher_ruby_id": None},
        ]
    }
    patched, count = apply_publisher_ruby_propagation(vocabulary, ruby_map)
    assert count == 2
    # c1 was patched from None to まほうしき
    assert patched["candidates"][0]["reading"] == "まほうしき"
    assert patched["candidates"][0]["reading_source"] == "publisher-ruby-propagation"
    # c2 had publisher_ruby_id so it was not modified
    assert patched["candidates"][1]["reading"] == "まほうしき"
    assert "reading_source" not in patched["candidates"][1]
    # n1 was patched to author reading
    assert patched["name_occurrences"][0]["reading"] == "たつや"
