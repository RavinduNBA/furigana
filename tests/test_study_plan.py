import json
from dataclasses import replace
from pathlib import Path

import pytest

from furiganalyse.study_plan import (
    StudyPlanConfig,
    StudyPlanError,
    _preferred_occurrence_reading,
    create_annotation_plan,
    serialize_annotation_plan,
    validate_annotation_plan,
)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "artifacts/phase3/jmnedict/run-a/vocabulary.json"
)


@pytest.fixture(scope="module")
def source_report():
    if not SOURCE.exists():
        pytest.fail("run scripts/phase3-regression.sh first")
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def test_selected_items_and_dictionary_baseline(source_report):
    plan = create_annotation_plan(source_report)
    assert plan.schema_version == 1 and plan.source_report_schema_version == 4
    assert [(x.kind, x.surface, x.display_meaning) for x in plan.items] == [
        ("expression", "良い天気だ", "fine weather"),
        ("vocabulary", "言葉", "language"),
        ("vocabulary", "表舞台", "public stage"),
        ("name", "雪乃", "Yukino (person; female given name)"),
        ("vocabulary", "振り返っ", "to turn around"),
    ]
    assert (
        plan.items[0].normalized_form == "良い天気"
        and plan.items[4].lemma == "振り返る"
    )


def test_personal_book_mode_uses_occurrence_reading(source_report):
    plan = create_annotation_plan(source_report, prefer_occurrence_reading=True)
    inflected = next(item for item in plan.items if item.surface == "振り返っ")

    assert inflected.reading == "ふりかえっ"


def test_numeric_year_uses_deterministic_counter_reading():
    candidate = {
        "surface": "年",
        "reading": "トシ",
        "sentence_id": "sentence",
        "sentence_start": 4,
    }
    tokens = {
        "previous": {
            "surface": "１９ＸＸ",
            "sentence_id": "sentence",
            "sentence_end": 4,
        }
    }

    assert _preferred_occurrence_reading(candidate, tokens) == (
        "ねん",
        "deterministic-context-rule",
    )


def test_publisher_ruby_deduplication_and_name_separation(source_report):
    plan = create_annotation_plan(source_report)
    ruby = next(x for x in plan.items if x.surface == "表舞台")
    assert ruby.reading == "おもてぶたい" and ruby.reading_source == "publisher"
    assert [x.occurrence_number for x in ruby.occurrences] == [1, 2]
    assert all(
        x.publisher_ruby_id and x.annotation_target == "preserved_publisher_ruby"
        for x in ruby.occurrences
    )
    name = next(x for x in plan.items if x.kind == "name")
    assert (
        name.surface == "雪乃"
        and name.selected_translation_id
        and name.selected_sense_id is None
    )
    assert name.dictionary_dataset_id == plan.name_dictionary["dataset_id"]


def test_offsets_anchors_exclusions_and_order(source_report):
    plan = create_annotation_plan(source_report)
    keys = []
    for index, item in enumerate(plan.items, 1):
        assert (
            item.id == f"study-item-{index:04d}"
            and item.note_anchor_id == f"note-{item.id}"
        )
        for number, occurrence in enumerate(item.occurrences, 1):
            assert (
                occurrence.id == f"{item.id}-occ-{number:04d}"
                and occurrence.source_anchor_id == f"src-{occurrence.id}"
            )
            assert (
                occurrence.sentence_start < occurrence.sentence_end
                and occurrence.block_start < occurrence.block_end
            )
        first = item.occurrences[0]
        keys.append(
            (first.chapter_id, first.block_id, first.sentence_id, first.sentence_start)
        )
    assert keys == sorted(keys) and len(plan.diagnostics) == 52
    assert any(x.reason == "no-compatible-dictionary-match" for x in plan.diagnostics)
    assert any(x.reason.startswith("phase3-name-") for x in plan.diagnostics)


def test_limit_and_serialization_are_deterministic(source_report):
    plan = create_annotation_plan(
        source_report, StudyPlanConfig(per_chapter_item_limit=1)
    )
    assert [(x.kind, x.surface) for x in plan.items] == [
        ("expression", "良い天気だ"),
        ("name", "雪乃"),
    ]
    assert sum(x.reason == "chapter-item-limit" for x in plan.diagnostics) == 4
    assert serialize_annotation_plan(
        create_annotation_plan(source_report)
    ) == serialize_annotation_plan(create_annotation_plan(source_report))


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda p: replace(p, schema_version=99), "Unsupported annotation-plan schema"),
        (
            lambda p: replace(p, items=[replace(p.items[0], display_meaning="")]),
            "Incomplete study item",
        ),
        (
            lambda p: replace(
                p, items=[replace(p.items[0], selected_sense_id="missing")]
            ),
            "Invalid JMdict references",
        ),
        (
            lambda p: replace(
                p,
                items=[
                    replace(
                        p.items[0],
                        occurrences=[
                            replace(p.items[0].occurrences[0], sentence_end=0)
                        ],
                    )
                ],
            ),
            "Invalid occurrence offsets",
        ),
    ],
)
def test_validation_rejects_invalid_plans(source_report, mutation, message):
    plan = create_annotation_plan(source_report)
    with pytest.raises(StudyPlanError, match=message):
        validate_annotation_plan(source_report, mutation(plan))


def test_rejects_wrong_schema_and_invalid_limit(source_report):
    with pytest.raises(StudyPlanError, match="schema v4"):
        create_annotation_plan({**source_report, "schema_version": 3})
    with pytest.raises(StudyPlanError, match="must be positive"):
        create_annotation_plan(source_report, StudyPlanConfig(per_chapter_item_limit=0))
