import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from furiganalyse.grammar_epub import (
    BASE_MEMBERS,
    GRAMMAR_MEMBERS,
    GRAMMAR_NOTES_ID,
    GrammarEpubError,
    STUDY_NOTES_ID,
    build_grammar_epub,
    build_vocabulary_fixture,
    validate_archive,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/phase7-linked-source-v1"
LINKED = ROOT / "tests/phase7_golden/grammar-linked-v1"
CLI = ROOT / "scripts/package_grammar_epub.py"
OPF = "{http://www.idpf.org/2007/opf}"
X = "{http://www.w3.org/1999/xhtml}"


@pytest.fixture
def fixture(tmp_path):
    base = tmp_path / "vocabulary.epub"
    build_vocabulary_fixture(SOURCE, base)
    return base


def test_vocabulary_fixture_and_grammar_epub_are_deterministic(fixture, tmp_path):
    other_base = tmp_path / "vocabulary-b.epub"
    build_vocabulary_fixture(SOURCE, other_base)
    assert fixture.read_bytes() == other_base.read_bytes()
    first = tmp_path / "grammar-a.epub"
    second = tmp_path / "grammar-b.epub"
    build_grammar_epub(fixture, LINKED, first)
    build_grammar_epub(fixture, LINKED, second)
    assert first.read_bytes() == second.read_bytes()
    assert validate_archive(fixture, grammar=False)["member_count"] == 7
    assert validate_archive(first, grammar=True)["member_count"] == 8


def test_archive_metadata_manifest_spine_navigation_and_xhtml_bytes(fixture, tmp_path):
    output = tmp_path / "grammar.epub"
    build_grammar_epub(fixture, LINKED, output)
    report = validate_archive(output, grammar=True)
    assert json.dumps(report, indent=2, sort_keys=True) + "\n" == (
        ROOT / "tests/phase7_golden/grammar-epub-v1.json"
    ).read_text()
    assert set(report["archive_members"]) == GRAMMAR_MEMBERS
    assert report["archive_members"][0] == "mimetype"
    assert report["compression"] == ["stored", *("deflated" for _ in range(7))]
    assert set(report["permissions"]) == {"0o100644"}
    assert set(map(tuple, report["timestamps"])) == {(1980, 1, 1, 0, 0, 0)}
    assert report["spine"] == ["grammar-ch1", "grammar-ch2", STUDY_NOTES_ID, GRAMMAR_NOTES_ID]
    assert report["navigation"] == [
        "Synthetic Grammar Chapter 1",
        "Synthetic Grammar Chapter 2",
        "Study Notes",
        "Grammar Study Notes",
    ]
    assert report["navigation_hrefs"] == [
        "text/grammar-01.xhtml",
        "text/grammar-02.xhtml",
        "text/study-notes.xhtml",
        "text/grammar-notes.xhtml",
    ]
    assert report["package_metadata"] == {
        "identifier": "urn:uuid:furiganalyse-phase-7-synthetic",
        "title": "Furiganalyse Phase 7 Synthetic Grammar Fixture",
        "language": "ja",
        "modified": "2026-08-20T00:00:00Z",
    }
    with zipfile.ZipFile(output) as archive:
        for name in sorted(GRAMMAR_MEMBERS):
            if name.endswith(".xhtml") and name.startswith("EPUB/text/"):
                assert archive.read(name) == (LINKED / name).read_bytes()
        package = ET.fromstring(archive.read("EPUB/package.opf"))
        items = package.findall(".//" + OPF + "item")
        assert sum(item.get("id") == STUDY_NOTES_ID for item in items) == 1
        grammar = [item for item in items if item.get("id") == GRAMMAR_NOTES_ID]
        assert len(grammar) == 1
        assert grammar[0].get("href") == "text/grammar-notes.xhtml"
        assert grammar[0].get("media-type") == "application/xhtml+xml"


def test_link_counts_contexts_dispositions_ruby_and_metadata_exclusion(fixture, tmp_path):
    output = tmp_path / "grammar.epub"
    build_grammar_epub(fixture, LINKED, output)
    report = validate_archive(output, grammar=True)
    assert (report["grammar_notes"], report["grammar_contexts"]) == (5, 7)
    assert (report["grammar_forward_links"], report["grammar_backlinks"]) == (3, 3)
    assert report["study_links"] == 5
    with zipfile.ZipFile(output) as archive:
        notes = ET.fromstring(archive.read("EPUB/text/grammar-notes.xhtml"))
        records = notes.findall(".//" + X + "div[@class='grammar-study-note__occurrence']")
        nonlinked = {
            "grammar-plan-occurrence-0001",
            "grammar-plan-occurrence-0003",
            "grammar-plan-occurrence-0004",
            "grammar-plan-occurrence-0006",
        }
        assert all(
            record.find(".//" + X + "a") is None
            for record in records
            if record.get("data-occurrence-id") in nonlinked
        )
        chapter = ET.fromstring(archive.read("EPUB/text/grammar-01.xhtml"))
        ruby = chapter.find(".//" + X + "ruby[@id='publisher-ruby-1-8-1']")
        assert ruby is not None and ruby.find(X + "rt").text == "おもてぶたい"
        blob = b"\n".join(archive.read(name) for name in archive.namelist()).lower()
        assert all(value not in blob for value in (b"provider-id", b"model-id", b"cache-key", b"context-hash", b"prompt-version"))


def _copy_linked(tmp_path, name):
    target = tmp_path / name
    shutil.copytree(LINKED, target)
    return target


def _safe_cli(base, linked, output, report, *, enabled=True):
    command = [
        sys.executable,
        str(CLI),
        "--input-epub",
        str(base),
        "--output",
        str(output),
        "--report",
        str(report),
    ]
    if linked is not None:
        command.extend(("--linked-dir", str(linked)))
    if enabled:
        command.append("--enabled")
    subprocess.run(command, check=True, cwd=ROOT)
    return json.loads(report.read_text())


def test_disabled_and_safe_failures_preserve_vocabulary_epub(fixture, tmp_path):
    cases = []
    stale = _copy_linked(tmp_path, "stale")
    study = stale / "EPUB/text/study-notes.xhtml"
    study.write_bytes(study.read_bytes() + b"\n")
    cases.append(("stale-input", stale))
    invalid = _copy_linked(tmp_path, "invalid")
    (invalid / "EPUB/text/grammar-notes.xhtml").unlink()
    cases.append(("invalid-input", invalid))
    corrupt = _copy_linked(tmp_path, "corrupt")
    (corrupt / "EPUB/text/grammar-notes.xhtml").write_bytes(b"<not-xhtml")
    cases.append(("corrupt-input", corrupt))
    ambiguous = _copy_linked(tmp_path, "ambiguous")
    chapter = ambiguous / "EPUB/text/grammar-01.xhtml"
    chapter.write_text(chapter.read_text().replace("</a>。</span>", "</a>！</span>", 1))
    cases.append(("ambiguous-input", ambiguous))
    unsafe = _copy_linked(tmp_path, "unsafe")
    notes = unsafe / "EPUB/text/grammar-notes.xhtml"
    notes.write_text(notes.read_text().replace("grammar-01.xhtml#grammar-src-grammar-occurrence-0005", "../../mimetype"))
    cases.append(("unsafe-input", unsafe))
    broken = _copy_linked(tmp_path, "broken")
    notes = broken / "EPUB/text/grammar-notes.xhtml"
    notes.write_text(notes.read_text().replace("#grammar-src-grammar-occurrence-0005", "#missing-fragment"))
    cases.append(("invalid-input", broken))
    disabled_output = tmp_path / "disabled.epub"
    disabled = _safe_cli(fixture, None, disabled_output, tmp_path / "disabled.json", enabled=False)
    assert disabled["diagnostics"][0]["reason"] == "disabled"
    assert disabled_output.read_bytes() == fixture.read_bytes()
    for index, (reason, linked) in enumerate(cases):
        output = tmp_path / f"fallback-{index}.epub"
        report = _safe_cli(fixture, linked, output, tmp_path / f"report-{index}.json")
        assert report["packaged"] is False and report["diagnostics"] == [
            {"id": "grammar-epub-diagnostic-0001", "reason": reason}
        ]
        assert output.read_bytes() == fixture.read_bytes()
        assert validate_archive(output, grammar=False)["archive_members"] == validate_archive(fixture, grammar=False)["archive_members"]


def test_rejects_duplicate_archive_paths(fixture, tmp_path):
    duplicate = tmp_path / "duplicate.epub"
    with zipfile.ZipFile(fixture) as source, zipfile.ZipFile(duplicate, "w") as target:
        for info in source.infolist():
            target.writestr(info, source.read(info.filename))
        with pytest.warns(UserWarning, match="Duplicate name"):
            target.writestr("EPUB/nav.xhtml", source.read("EPUB/nav.xhtml"))
    with pytest.raises(GrammarEpubError, match="invalid-input"):
        validate_archive(duplicate, grammar=False)


def test_phase4_and_phase5_packaging_and_xhtml_compatibility():
    assert (ROOT / "artifacts/phase4/epub/run-a.epub").read_bytes() == (ROOT / "artifacts/phase4/epub/run-b.epub").read_bytes()
    phase5 = ROOT / "artifacts/phase5/rendered/run-a.epub"
    expected = json.loads((ROOT / "tests/phase5_golden/enriched-epub-v2.json").read_text())
    assert hashlib.sha256(phase5.read_bytes()).hexdigest() == expected["sha256"]
    assert phase5.read_bytes() == (ROOT / "artifacts/phase5/rendered/run-b.epub").read_bytes()
    for phase, golden in (
        (ROOT / "artifacts/phase4/linked/run-a", ROOT / "tests/phase4_golden/linked-v1"),
        (ROOT / "artifacts/phase5/rendered/run-a/linked", ROOT / "tests/phase5_golden/linked-v2"),
    ):
        assert {path.relative_to(phase): path.read_bytes() for path in phase.rglob("*.xhtml")} == {
            path.relative_to(golden): path.read_bytes() for path in golden.rglob("*.xhtml")
        }
