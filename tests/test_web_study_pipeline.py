import json
import hashlib
from pathlib import Path
from xml.etree import ElementTree as ET

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

X = "{http://www.w3.org/1999/xhtml}"


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
            note_name = next(
                name for name in archive.namelist()
                if name.endswith("/study-notes.xhtml")
            )
            note_root = ET.fromstring(archive.read(note_name))
            note_style = note_root.find(
                f"{X}head/{X}style[@id='furiganalyse-web-note-style']"
            )
            page_note_names = sorted(
                name
                for name in archive.namelist()
                if "/study-notes-page-" in name and name.endswith(".xhtml")
            )
            page_note_roots = [
                ET.fromstring(archive.read(name)) for name in page_note_names
            ]
            source_roots = [
                ET.fromstring(archive.read(name))
                for name in archive.namelist()
                if name.endswith(("chapter-01.xhtml", "chapter-02.xhtml"))
            ]
        assert "furiganalyse-web-link-style" in xhtml
        assert note_root.get("lang") == "ja"
        assert note_root.get("{http://www.w3.org/XML/1998/namespace}lang") == "ja"
        assert note_style is not None
        assert "writing-mode: horizontal-tb !important" in note_style.text
        assert "max-width: 100%; margin: .5em 0" in note_style.text
        assert "not sentence translation" in xhtml
        assert page_note_names
        assert note_root.findall(f".//{X}section") == []
        assert all(
            1 <= len(root.findall(f".//{X}section")) <= 25
            for root in page_note_roots
        )
        assert all(
            "study-notes-page-" in link.get("href", "")
            for root in source_roots
            for link in root.findall(f".//{X}a[@class='study-link']")
        )
        if experimental:
            assert xhtml.count('class="adaptive-meaning-assistance"') == summaries[0][
                "study_items"
            ]

    capped_count = summaries[0]["study_items"]
    all_work = tmp_path / "work-all"
    all_output = tmp_path / "all.epub"
    all_summary = run_dictionary_study_pipeline(
        source,
        all_output,
        all_work,
        WebStudyOptions(per_chapter_item_limit=0),
    )
    assert validate_epub(all_output) == []
    assert all_summary["study_items"] > capped_count
    all_plan = json.loads(
        (all_work / "annotation-plan.json").read_text(encoding="utf-8")
    )
    assert not any(
        diagnostic["reason"] == "chapter-item-limit"
        for diagnostic in all_plan["diagnostics"]
    )

    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash


def test_combined_mode_preserves_study_navigation_and_adds_broad_furigana(
    tmp_path, monkeypatch
):
    from furiganalyse.app import decode_filepath, furiganalyse_task

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
    outputs = []

    for run in ("a", "b"):
        task = tmp_path / run
        task.mkdir()
        source = task / "source.epub"
        build_fixture(source)
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        result = furiganalyse_task(
            task,
            source.name,
            "epub",
            "add",
            "horizontal-tb",
            pipeline_mode="combined",
            per_chapter_item_limit=2,
        )
        output = Path(decode_filepath(result))
        outputs.append(output.read_bytes())
        assert validate_epub(output) == []
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash

        with __import__("zipfile").ZipFile(output) as archive:
            roots = [
                ET.fromstring(archive.read(name))
                for name in archive.namelist()
                if name.endswith(".xhtml")
            ]
        study_links = sum(
            "study-link" in node.get("class", "").split()
            for root in roots
            for node in root.iter()
        )
        backlinks = sum(
            "study-note__backlink" in node.get("class", "").split()
            for root in roots
            for node in root.iter()
        )
        ruby_count = sum(
            node.tag == X + "ruby" for root in roots for node in root.iter()
        )
        assert study_links == backlinks > 0
        assert ruby_count > 2

    assert outputs[0] == outputs[1]


def test_guided_reading_covers_function_words_without_nested_links(
    tmp_path, monkeypatch
):
    from furiganalyse.app import decode_filepath, furiganalyse_task

    source = tmp_path / "source.epub"
    build_fixture(source)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    jmdict_index = tmp_path / "jmdict.sqlite"
    jmnedict_index = tmp_path / "jmnedict.sqlite"
    build_jmdict_index(
        Path("tests/fixtures/jmdict-expressions-mini.xml"), jmdict_index
    )
    build_jmnedict_index(Path("tests/fixtures/jmnedict-mini.xml"), jmnedict_index)
    monkeypatch.setenv("FURIGANALYSE_JMDICT_INDEX", str(jmdict_index))
    monkeypatch.setenv("FURIGANALYSE_JMNEDICT_INDEX", str(jmnedict_index))
    outputs = []

    for run in ("a", "b"):
        output = tmp_path / f"guided-{run}.epub"
        run_work = tmp_path / f"guided-work-{run}"
        summary = run_dictionary_study_pipeline(
            source,
            output,
            run_work,
            WebStudyOptions(per_chapter_item_limit=0, guided_reading=True),
        )
        outputs.append(output.read_bytes())
        assert validate_epub(output) == []
        assert summary["guided_items"] > 0
        assert summary["guided_occurrences"] > 0
        assert summary["guided_note_pages"] > 0
        guided_plan = json.loads(
            (run_work / "guided-reading-plan.json").read_text(encoding="utf-8")
        )
        assert {item["kind"] for item in guided_plan["items"]} <= {
            "function", "unmatched",
        }
        assert any(
            item["surface"] == "は"
            and item["kind"] == "function"
            and "marker" in item["display_assistance"]
            for item in guided_plan["items"]
        )
        assert all(
            item["kind"] == "function"
            for item in guided_plan["items"]
            if item["surface"] == "に"
        )
        assert guided_plan["expression_components"]
        with __import__("zipfile").ZipFile(output) as archive:
            names = archive.namelist()
            guided_pages = [
                name for name in names if "/guided-notes-page-" in name
            ]
            roots = {
                name: ET.fromstring(archive.read(name))
                for name in names
                if name.endswith(".xhtml")
            }
            package = "\n".join(
                archive.read(name).decode("utf-8")
                for name in names
                if name.endswith((".opf", "nav.xhtml"))
            )
        guided_links = [
            node
            for root in roots.values()
            for node in root.findall(f".//{X}a[@class='guided-link']")
        ]
        backlinks = [
            node
            for root in roots.values()
            for node in root.findall(f".//{X}a[@class='guided-note__backlink']")
        ]
        guided_text = "".join(
            "".join(roots[name].itertext()) for name in guided_pages
        )
        assert all(
            len(roots[name].findall(f".//{X}section[@class]")) <= 25
            for name in guided_pages
        )
        assert len(guided_links) == len(backlinks) == summary["guided_occurrences"]
        assert "particle" in guided_text or "marker" in guided_text
        assert "Guided Reading Notes" in package
        assert "furiganalyse-guided-notes" in package
        assert all(
            not link.findall(f".//{X}a")
            for link in guided_links
        )

    assert outputs[0] == outputs[1]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash

    task = tmp_path / "guided-app"
    task.mkdir()
    app_source = task / "source.epub"
    build_fixture(app_source)
    result = furiganalyse_task(
        task,
        app_source.name,
        "epub",
        "add",
        "horizontal-tb",
        pipeline_mode="guided",
    )
    app_output = Path(decode_filepath(result))
    assert validate_epub(app_output) == []
    with __import__("zipfile").ZipFile(app_output) as archive:
        app_roots = [
            ET.fromstring(archive.read(name))
            for name in archive.namelist()
            if name.endswith(".xhtml")
        ]
    assert any(
        node.get("class") == "guided-link"
        for root in app_roots for node in root.iter()
    )


def test_bilingual_companion_pipeline_end_to_end(tmp_path, monkeypatch):
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

    source = tmp_path / "source.epub"
    output = tmp_path / "bilingual.epub"
    work = tmp_path / "work"

    build_fixture(source)

    run_dictionary_study_pipeline(
        source,
        output,
        work,
        WebStudyOptions(
            bilingual_companion=True,
            bilingual_provider="mock",
        ),
    )

    assert output.exists()
    assert validate_epub(output) == []

    companion_epub = tmp_path / "bilingual - Bilingual Companion.epub"
    assert companion_epub.exists()
    assert validate_epub(companion_epub) == []

    with __import__("zipfile").ZipFile(companion_epub) as z:
        names = z.namelist()
        trans_docs = [n for n in names if "translation.xhtml" in n]
        assert len(trans_docs) > 0
        content = z.read(trans_docs[0]).decode("utf-8")
        assert "English Companion Translation" in content
