"""Publisher ruby extraction and book-wide propagation.

In Japanese light novels, authors frequently assign canonical pronunciation or
world-specific readings via <ruby> tags (e.g. <ruby>魔法式<rt>まほうしき</rt></ruby>),
but typically only for the first occurrence of a term in a chapter.

This module extracts all author-assigned ruby pairs from the canonical book model
and propagates those readings across all unannotated occurrences of the same
surface text in the book.

Design goals:
- 100% deterministic and instantaneous (<0.1s)
- Resolves conflicts by selecting the most frequent author reading for each surface
- Preserves existing publisher_ruby_id tags where present
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)

# Valid kana reading pattern
KANA_PATTERN = re.compile(r"^[ぁ-ゖァ-ヺー\s]+$")


def extract_publisher_ruby_map(
    canonical_book: dict[str, Any],
) -> dict[str, str]:
    """Extract a dominant (surface -> reading) map from all publisher ruby spans in the book.

    If an author uses different readings for the same surface text, the most
    frequently occurring reading is chosen.
    """
    pair_counts: dict[str, Counter[str]] = {}

    for chapter in canonical_book.get("chapters", []):
        for block in chapter.get("blocks", []):
            for ruby in block.get("publisher_ruby", []):
                surface = (ruby.get("surface") or "").strip()
                reading = (ruby.get("reading") or "").strip()
                if not surface or not reading:
                    continue
                # Normalize reading: remove excessive whitespace
                reading = re.sub(r"\s+", "", reading)
                if not reading:
                    continue

                if surface not in pair_counts:
                    pair_counts[surface] = Counter()
                pair_counts[surface][reading] += 1

    ruby_map: dict[str, str] = {}
    for surface, counts in pair_counts.items():
        # Select the most common author-assigned reading
        most_common_reading, _ = counts.most_common(1)[0]
        ruby_map[surface] = most_common_reading

    logger.info(
        "extract_publisher_ruby_map: extracted %d unique publisher ruby pairs from book",
        len(ruby_map),
    )
    return ruby_map


def apply_publisher_ruby_propagation(
    vocabulary: dict[str, Any],
    ruby_map: dict[str, str],
) -> tuple[dict[str, Any], int]:
    """Propagate author ruby readings to all unannotated candidate instances.

    Returns (updated_vocabulary_dict, patch_count).
    """
    if not ruby_map:
        return vocabulary, 0

    patch_count = 0
    patched_candidates = []

    for cand in vocabulary.get("candidates", []):
        surface = cand.get("surface", "")
        # Only override if this candidate didn't already have publisher ruby
        if surface in ruby_map and not cand.get("publisher_ruby_id"):
            target_reading = ruby_map[surface]
            if cand.get("reading") != target_reading:
                cand = dict(cand)
                cand["reading"] = target_reading
                cand["reading_source"] = "publisher-ruby-propagation"
                patch_count += 1
        patched_candidates.append(cand)

    patched_names = []
    for occ in vocabulary.get("name_occurrences", []):
        surface = occ.get("surface", "")
        if surface in ruby_map and not occ.get("publisher_ruby_id"):
            target_reading = ruby_map[surface]
            if occ.get("reading") != target_reading:
                occ = dict(occ)
                occ["reading"] = target_reading
                patch_count += 1
        patched_names.append(occ)

    logger.info(
        "apply_publisher_ruby_propagation: patched %d occurrences using %d publisher ruby terms",
        patch_count,
        len(ruby_map),
    )

    result = dict(vocabulary)
    result["candidates"] = patched_candidates
    result["name_occurrences"] = patched_names
    result["publisher_ruby_overrides"] = ruby_map
    return result, patch_count
