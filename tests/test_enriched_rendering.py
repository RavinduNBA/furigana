import copy
import hashlib
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from furiganalyse.epub_packaging import build_study_epub
from furiganalyse.linked_output import X, create_linked_output
from furiganalyse.study_notes import StudyNoteError, render_study_notes
from tests.phase0_epub import validate_epub

ROOT = Path(__file__).resolve().parents[1]
EPUB = ROOT / "artifacts/phase2/fixture.epub"
BOOK = json.loads((ROOT / "artifacts/phase2/run-a/book.json").read_text())
V1 = json.loads((ROOT / "artifacts/phase4/run-a/annotation-plan.json").read_text())
V2 = json.loads(
    (ROOT / "artifacts/phase5/enriched-plan/run-a/annotation-plan.json").read_text()
)
FORBIDDEN = (
    "openai-compatible",
    "fake-enrichment-v1",
    "validated-model",
    "context_hash",
    "cache_key",
    "prompt_version",
    "plan-enrichment-",
)


def note_meanings(data):
    root = ET.fromstring(data)
    return [
        section.find(X + "p[@class='study-note__meaning']").text
        for section in root.findall(".//" + X + "section")
    ]


def test_schema_v2_standalone_notes_match_golden_and_hide_audit_metadata():
    data = render_study_notes(V2)
    assert (
        data
        == (ROOT / "tests/phase5_golden/rendered-v2/study-notes.xhtml").read_bytes()
    )
    assert note_meanings(data) == [
        "pleasant weather",
        "word",
        "public stage",
        "Yukino (female given name)",
        "to turn around",
    ]
    text = data.decode()
    assert all(value not in text for value in FORBIDDEN)
    assert (
        "fine weather" not in text and "Yukino (person; female given name)" not in text
    )


def test_schema_v1_standalone_and_linked_outputs_remain_byte_identical():
    assert (
        render_study_notes(V1)
        == (ROOT / "tests/phase4_golden/study-notes-v1.xhtml").read_bytes()
    )
    linked = create_linked_output(EPUB, BOOK, V1)
    for path, data in linked.files.items():
        assert data == (ROOT / "tests/phase4_golden/linked-v1" / path).read_bytes()


def test_schema_v2_linked_output_matches_golden_and_preserves_sources():
    enriched = create_linked_output(EPUB, BOOK, V2)
    baseline = create_linked_output(EPUB, BOOK, V1)
    assert len(enriched.files) == 3
    for path, data in enriched.files.items():
        assert data == (ROOT / "tests/phase5_golden/linked-v2" / path).read_bytes()
        ET.fromstring(data)
        assert all(value not in data.decode() for value in FORBIDDEN)
        if not path.endswith("study-notes.xhtml"):
            assert data == baseline.files[path]
    notes = ET.fromstring(enriched.files[enriched.notes_path])
    assert len(notes.findall(".//" + X + "section")) == 5
    assert len(notes.findall(".//" + X + "a[@class='study-note__backlink']")) == 6
    assert len(notes.findall(".//" + X + "blockquote")) == 6


def test_schema_v2_publisher_ruby_links_and_anchors_are_preserved():
    output = create_linked_output(EPUB, BOOK, V2)
    roots = {path: ET.fromstring(data) for path, data in output.files.items()}
    forwards = [
        link
        for path, root in roots.items()
        if path != output.notes_path
        for link in root.findall(".//" + X + "a[@class='study-link']")
    ]
    assert len(forwards) == 6
    assert len({x.attrib["id"] for x in forwards}) == 6
    rubies = [
        ruby for root in roots.values() for ruby in root.findall(".//" + X + "ruby")
    ]
    assert any("表舞台おもてぶたい" in "".join(x.itertext()) for x in rubies)
    assert any("雪乃（ゆきの）" in "".join(x.itertext()) for x in rubies)
    assert all(not ruby.findall(".//" + X + "ruby") for ruby in rubies)


def test_schema_v2_epub_is_deterministic_valid_and_matches_checksum(tmp_path):
    a, b = tmp_path / "a.epub", tmp_path / "b.epub"
    build_study_epub(EPUB, BOOK, V2, a)
    build_study_epub(EPUB, BOOK, V2, b)
    expected = json.loads(
        (ROOT / "tests/phase5_golden/enriched-epub-v2.json").read_text()
    )
    assert a.read_bytes() == b.read_bytes()
    assert hashlib.sha256(a.read_bytes()).hexdigest() == expected["sha256"]
    assert validate_epub(a) == []
    with zipfile.ZipFile(a) as archive:
        assert len(archive.infolist()) == expected["member_count"] == 9
        notes = archive.read("EPUB/text/study-notes.xhtml")
        assert note_meanings(notes) == list(
            json.loads(
                (
                    ROOT / "tests/phase5_golden/enriched-rendering-review-cases-v2.json"
                ).read_text()
            )["meanings"].values()
        )
        all_text = "".join(
            archive.read(name).decode("utf-8", "ignore") for name in archive.namelist()
        )
        assert all(value not in all_text for value in FORBIDDEN)


@pytest.mark.parametrize("name", ["disabled.json", "failure.json"])
def test_phase5_fallback_plans_render_exact_phase4_outputs(name, tmp_path):
    fallback = json.loads((ROOT / "artifacts/phase5/enriched-plan" / name).read_text())
    assert fallback == V1
    assert render_study_notes(fallback) == render_study_notes(V1)
    assert create_linked_output(EPUB, BOOK, fallback) == create_linked_output(
        EPUB, BOOK, V1
    )
    a, b = tmp_path / f"{name}-a.epub", tmp_path / f"{name}-b.epub"
    build_study_epub(EPUB, BOOK, fallback, a)
    build_study_epub(EPUB, BOOK, V1, b)
    assert a.read_bytes() == b.read_bytes()


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda p: p.pop("enrichments"), "schema"),
        (
            lambda p: p["enrichments"][0].update(display_meaning="changed"),
            "mismatch",
        ),
        (
            lambda p: p["enrichments"][0].update(cache_key="invalid"),
            "provenance",
        ),
    ],
)
def test_malformed_schema_v2_is_rejected(mutate, message):
    plan = copy.deepcopy(V2)
    mutate(plan)
    with pytest.raises(StudyNoteError, match=message):
        render_study_notes(plan)
