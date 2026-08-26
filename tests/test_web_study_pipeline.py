import json
import hashlib
from pathlib import Path

from furiganalyse.assistance_density import validate_density_policy_dataset
from furiganalyse.enriched_plan import promote_dictionary_only_plan
from furiganalyse.jmdict import build_jmdict_index
from furiganalyse.jmnedict import build_jmnedict_index
from furiganalyse.learner_profile import validate_preset_dataset
from furiganalyse.study_notes import validate_annotation_plan_for_notes
from furiganalyse.web_study_pipeline import (
    WebStudyOptions,
    build_web_density_dataset,
    build_web_preset_dataset,
    run_dictionary_study_pipeline,
)
from tests.phase0_epub import build_fixture, validate_epub


def test_web_presets_and_density_policies_are_valid_deterministic_fixtures():
    first_presets = build_web_preset_dataset()
    second_presets = build_web_preset_dataset()
    first_density = build_web_density_dataset()
    second_density = build_web_density_dataset()

    assert first_presets == second_presets
    assert first_density == second_density
    validate_preset_dataset(first_presets)
    validate_density_policy_dataset(first_density)
    assert [value["level"] for value in first_presets["presets"]] == ["N5", "N4", "N3"]
    assert [value["preset_id"] for value in first_density["policies"]] == [
        "phase8-preset-n5", "phase8-preset-n4", "phase8-preset-n3",
    ]
    assert [
        value["maximum_per_chapter"]["reading"]
        for value in first_density["policies"]
    ] == [500, 300, 150]
    all_meanings = build_web_density_dataset(all_selected_meanings=True)
    validate_density_policy_dataset(all_meanings)
    assert all(
        value["maximum_per_chapter"]["meaning"] == 10_000
        for value in all_meanings["policies"]
    )


def test_dictionary_only_plan_promotion_preserves_phase4_items():
    source = json.loads(
        open("tests/phase4_golden/annotation-plan-v1.json", encoding="utf-8").read()
    )
    promoted = promote_dictionary_only_plan(source)

    assert promoted["schema_version"] == 2
    assert promoted["source_annotation_plan_schema_version"] == 1
    assert promoted["items"] == source["items"]
    assert promoted["enrichments"] == []
    assert promoted["enrichment_diagnostics"] == []
    validate_annotation_plan_for_notes(promoted)


def test_dictionary_study_and_experimental_epubs_are_deterministic(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.epub"
    build_fixture(source)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    jmdict_index = tmp_path / "jmdict.sqlite"
    jmnedict_index = tmp_path / "jmnedict.sqlite"
    build_jmdict_index(
        Path("tests/fixtures/jmdict-expressions-mini.xml"), jmdict_index
    )
    build_jmnedict_index(
        Path("tests/fixtures/jmnedict-mini.xml"), jmnedict_index
    )
    monkeypatch.setenv("FURIGANALYSE_JMDICT_INDEX", str(jmdict_index))
    monkeypatch.setenv("FURIGANALYSE_JMNEDICT_INDEX", str(jmnedict_index))

    for experimental in (False, True):
        outputs = []
        summaries = []
        for run in ("a", "b"):
            output = tmp_path / f"{experimental}-{run}.epub"
            summaries.append(
                run_dictionary_study_pipeline(
                    source,
                    output,
                    tmp_path / f"work-{experimental}-{run}",
                    WebStudyOptions(
                        per_chapter_item_limit=2,
                        experimental_adaptive=experimental,
                    ),
                )
            )
            outputs.append(output.read_bytes())
            assert validate_epub(output) == []
        assert outputs[0] == outputs[1]
        assert summaries[0] == summaries[1]
        assert summaries[0]["provider_calls"] == 0
        assert summaries[0]["network_dictionary_lookups"] == 0
        assert (summaries[0]["adaptive_occurrences"] > 0) is experimental
        with __import__("zipfile").ZipFile(tmp_path / f"{experimental}-a.epub") as archive:
            xhtml = "\n".join(
                archive.read(name).decode("utf-8")
                for name in archive.namelist()
                if name.endswith(".xhtml")
            )
        assert "furiganalyse-web-link-style" in xhtml
        assert "not sentence translation" in xhtml
        if experimental:
            assert xhtml.count('class="adaptive-meaning-assistance"') == summaries[0][
                "study_items"
            ]

    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
