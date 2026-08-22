from __future__ import annotations

import copy
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from furiganalyse.adaptive_epub import (
    DC,
    FIXED_TIME,
    MEMBER_ORDER,
    OPF,
    PACKAGE_PATH,
    TEXT_PATHS,
    X,
    build_package_metadata,
    package_adaptive_epub,
    safe_package_adaptive_epub,
    serialize_report,
)
from furiganalyse.adaptive_rendering import directory_hash
from furiganalyse.assistance_density import stable_hash

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/phase7/epub/run-a.epub"
ADAPTIVE = ROOT / "artifacts/phase8/rendered/run-a"
RENDERING_REPORT = ROOT / "artifacts/phase8/rendered/run-a-report.json"
METADATA = ROOT / "tests/fixtures/phase8-adaptive-epub-metadata-v1.json"
GOLDEN = ROOT / "tests/phase8_golden/adaptive-epub-v1.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def rehash(value: dict) -> None:
    value.pop("hash", None)
    value["hash"] = stable_hash(value)


def adaptive_files(directory: Path = ADAPTIVE) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*.xhtml"))
    }


def package(tmp_path: Path, name: str = "adaptive") -> tuple[Path, dict]:
    output = tmp_path / f"{name}.epub"
    report = package_adaptive_epub(
        BASE, load(RENDERING_REPORT), ADAPTIVE, load(METADATA), output,
    )
    return output, report


def test_metadata_fixture_is_deterministic():
    assert build_package_metadata(BASE, load(RENDERING_REPORT), ADAPTIVE) == load(METADATA)


def test_epub_and_report_are_deterministic_and_match_golden(tmp_path):
    first, report_a = package(tmp_path, "run-a")
    second, report_b = package(tmp_path, "run-b")
    assert first.read_bytes() == second.read_bytes()
    assert serialize_report(report_a) == serialize_report(report_b)
    assert report_a == load(GOLDEN)
    assert report_a["output_epub_sha256"] == hashlib.sha256(first.read_bytes()).hexdigest()


def test_archive_container_package_spine_navigation_and_xhtml(tmp_path):
    output, report = package(tmp_path)
    summary = report["structural_summary"]
    assert summary["archive_member_order"] == MEMBER_ORDER
    assert summary["container_rootfile"] == PACKAGE_PATH
    assert summary["package_metadata"] == {
        "identifier": "urn:uuid:furiganalyse-phase-8-synthetic-adaptive",
        "title": "Furiganalyse Phase 8 Synthetic Adaptive Assistance Fixture",
        "language": "ja",
        "modified": "2026-08-22T00:00:00Z",
    }
    assert summary["spine"] == [
        "grammar-ch1", "grammar-ch2", "furiganalyse-study-notes",
        "furiganalyse-grammar-notes",
    ]
    assert summary["navigation"] == [
        {"label": "Synthetic Grammar Chapter 1", "href": "text/grammar-01.xhtml"},
        {"label": "Synthetic Grammar Chapter 2", "href": "text/grammar-02.xhtml"},
        {"label": "Study Notes", "href": "text/study-notes.xhtml"},
        {"label": "Grammar Study Notes", "href": "text/grammar-notes.xhtml"},
    ]
    source = adaptive_files()
    with zipfile.ZipFile(output) as archive:
        infos = archive.infolist()
        assert [info.filename for info in infos] == MEMBER_ORDER
        assert archive.read("mimetype") == b"application/epub+zip"
        assert infos[0].compress_type == zipfile.ZIP_STORED
        assert all(info.compress_type == zipfile.ZIP_DEFLATED for info in infos[1:])
        assert all(info.date_time == FIXED_TIME for info in infos)
        assert all(info.create_system == 3 for info in infos)
        assert all(info.external_attr == 0o100644 << 16 for info in infos)
        assert all(archive.read(path) == source[path] for path in TEXT_PATHS)
        package_root = ET.fromstring(archive.read(PACKAGE_PATH))
        assert package_root.get("version") == "3.0"
        assert package_root.find(f".//{{{DC}}}identifier").text == (
            "urn:uuid:furiganalyse-phase-8-synthetic-adaptive"
        )
        assert len(package_root.findall(f".//{{{OPF}}}item")) == 5


def test_assistance_links_contexts_ruby_and_suppression(tmp_path):
    output, report = package(tmp_path)
    summary = report["structural_summary"]
    assert summary["rendering_result_count"] == 12
    assert summary["generated_reading_count"] == 1
    assert summary["displayed_meaning_count"] == 1
    assert (summary["study_forward_links"], summary["study_backlinks"]) == (5, 5)
    assert (summary["grammar_forward_links"], summary["grammar_backlinks"]) == (2, 2)
    assert (summary["grammar_notes"], summary["grammar_contexts"]) == (3, 3)
    assert summary["rendering_diagnostic_references"] == [{
        "id": "adaptive-rendering-diagnostic-0001",
        "reason": "missing-approved-reading",
        "source_id": "study-item-0002-occ-0001",
    }]
    with zipfile.ZipFile(output) as archive:
        chapter = ET.fromstring(archive.read("EPUB/text/grammar-01.xhtml"))
        ruby = chapter.find(f".//{X}ruby[@id='publisher-ruby-1-8-1']")
        generated = chapter.find(
            f".//{X}ruby[@id='adaptive-reading-study-item-0005-occ-0001']"
        )
        assert ruby is not None and ruby.find(X + "rt").text == "おもてぶたい"
        assert generated is not None and generated.find(X + "rt").text == "まえ"
        blob = b"\n".join(archive.read(name) for name in archive.namelist()).lower()
        assert b"to read" in blob
        for value in (
            "よん", "まいにちよむ", "to forget completely", "to read every day",
            "Mae (synthetic name)",
        ):
            assert value.lower().encode() not in blob
        assert all(value not in blob for value in (
            b"display:none", b"visibility:hidden", b"learner-identity",
            b"provider", b"source-path", b"override-note",
        ))


def copy_adaptive(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(ADAPTIVE, target)
    return target


def synchronize(report: dict, metadata: dict, directory: Path) -> None:
    files = adaptive_files(directory)
    for document in report["document_results"]:
        document["output_sha256"] = hashlib.sha256(files[document["path"]]).hexdigest()
        rehash(document)
    rehash(report)
    metadata["adaptive_rendering_report_hash"] = report["hash"]
    metadata["adaptive_xhtml_directory_hash"] = directory_hash(files)
    rehash(metadata)


@pytest.mark.parametrize(
    ("name", "mutator", "reason"),
    [
        (
            "broken-fragment",
            lambda text: text.replace(
                "grammar-notes.xhtml#grammar-note-0002",
                "grammar-notes.xhtml#missing-note",
                1,
            ),
            "broken-fragment",
        ),
        (
            "hidden-content",
            lambda text: text.replace(
                "</body>", '<span style="display:none">hidden</span></body>', 1,
            ),
            "unsafe-hidden-content",
        ),
        (
            "suppressed-content",
            lambda text: text.replace("</body>", "to forget completely</body>", 1),
            "suppressed-content-restoration",
        ),
        (
            "publisher-conflict",
            lambda text: text.replace("おもてぶたい", "おもて", 1),
            "publisher-ruby-mismatch",
        ),
        (
            "grammar-conflict",
            lambda text: text.replace('class="grammar-link"', 'class="grammar-link-removed"', 1),
            "grammar-link-mismatch",
        ),
        (
            "study-conflict",
            lambda text: text.replace('class="study-link"', 'class="study-link-removed"', 1),
            "study-link-mismatch",
        ),
    ],
)
def test_safe_xhtml_failures_restore_base(tmp_path, name, mutator, reason):
    directory = copy_adaptive(tmp_path, name)
    chapter = directory / "EPUB/text/grammar-01.xhtml"
    chapter.write_text(mutator(chapter.read_text(encoding="utf-8")), encoding="utf-8")
    rendering = load(RENDERING_REPORT)
    metadata = load(METADATA)
    synchronize(rendering, metadata, directory)
    output = tmp_path / f"{name}.epub"
    report = safe_package_adaptive_epub(
        BASE, rendering, directory, metadata, output, enabled=True,
    )
    assert [item["reason"] for item in report["diagnostics"]] == [reason]
    assert report["archive_members"] == [] and report["structural_summary"] is None
    assert output.read_bytes() == BASE.read_bytes()


@pytest.mark.parametrize(
    ("relative", "old", "new", "reason"),
    [
        (
            "EPUB/text/grammar-01.xhtml",
            "adaptive-reading-study-item-0005-occ-0001",
            "removed-adaptive-reading",
            "missing-presented-reading",
        ),
        (
            "EPUB/text/study-notes.xhtml",
            "adaptive-meaning-assistance",
            "removed-meaning-assistance",
            "missing-approved-meaning",
        ),
    ],
)
def test_missing_presented_assistance_is_rejected(tmp_path, relative, old, new, reason):
    directory = copy_adaptive(tmp_path, reason)
    target = directory / relative
    target.write_text(
        target.read_text(encoding="utf-8").replace(old, new, 1),
        encoding="utf-8",
    )
    rendering = load(RENDERING_REPORT)
    metadata = load(METADATA)
    synchronize(rendering, metadata, directory)
    output = tmp_path / f"{reason}.epub"
    report = safe_package_adaptive_epub(
        BASE, rendering, directory, metadata, output, enabled=True,
    )
    assert [item["reason"] for item in report["diagnostics"]] == [reason]
    assert output.read_bytes() == BASE.read_bytes()


def test_disabled_stale_directory_document_duplicate_and_corrupt_are_reversible(tmp_path):
    rendering = load(RENDERING_REPORT)
    metadata = load(METADATA)
    cases: list[tuple[str, dict | None, Path | None, dict | None, str | None]] = []
    cases.append(("disabled", rendering, ADAPTIVE, metadata, None))

    stale = copy.deepcopy(rendering)
    stale["configuration"]["enabled"] = False
    rehash(stale["configuration"])
    rehash(stale)
    cases.append(("stale", stale, ADAPTIVE, metadata, None))

    changed = copy_adaptive(tmp_path, "directory-mismatch")
    path = changed / "EPUB/text/grammar-02.xhtml"
    path.write_bytes(path.read_bytes() + b"\n")
    cases.append(("directory-mismatch", rendering, changed, metadata, None))

    changed_metadata = copy.deepcopy(metadata)
    changed_metadata["adaptive_xhtml_directory_hash"] = directory_hash(adaptive_files(changed))
    rehash(changed_metadata)
    cases.append(("document-mismatch", rendering, changed, changed_metadata, None))

    duplicate = copy.deepcopy(rendering)
    duplicate["document_results"][1]["path"] = duplicate["document_results"][0]["path"]
    rehash(duplicate["document_results"][1])
    rehash(duplicate)
    duplicate_metadata = copy.deepcopy(metadata)
    duplicate_metadata["adaptive_rendering_report_hash"] = duplicate["hash"]
    rehash(duplicate_metadata)
    cases.append(("duplicate", duplicate, ADAPTIVE, duplicate_metadata, None))
    cases.append(("corrupt", None, None, None, "corrupt-input"))

    expected = {
        "disabled": "disabled",
        "stale": "rendering-report-mismatch",
        "directory-mismatch": "adaptive-directory-hash-mismatch",
        "document-mismatch": "adaptive-document-hash-mismatch",
        "duplicate": "duplicate-archive-path",
        "corrupt": "corrupt-input",
    }
    for name, current_report, directory, current_metadata, failure in cases:
        output = tmp_path / f"fallback-{name}.epub"
        result = safe_package_adaptive_epub(
            BASE, current_report, directory, current_metadata, output,
            enabled=name != "disabled", failure_reason=failure,
        )
        assert [item["reason"] for item in result["diagnostics"]] == [expected[name]]
        assert output.read_bytes() == BASE.read_bytes()


def test_prior_phase_compatibility_is_unchanged():
    assert hashlib.sha256(BASE.read_bytes()).hexdigest() == (
        "df4c4bf0f072c01ac0a8d8aff316ee92613760c1822274cecd7ec9ce409a9619"
    )
    assert (ROOT / "artifacts/phase4/epub/run-a.epub").read_bytes() == (
        ROOT / "artifacts/phase4/epub/run-b.epub"
    ).read_bytes()
    phase5 = load(ROOT / "tests/phase5_golden/enriched-epub-v2.json")
    assert hashlib.sha256(
        (ROOT / "artifacts/phase5/rendered/run-a.epub").read_bytes()
    ).hexdigest() == phase5["sha256"]
    assert load(ROOT / "artifacts/phase8/rendered/run-a-report.json") == load(
        ROOT / "tests/phase8_golden/adaptive-rendering-report-v1.json"
    )
