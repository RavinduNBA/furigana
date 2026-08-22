from __future__ import annotations

import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from furiganalyse.adaptive_rendering import (
    XML_NS,
    XHTML_NS,
    render_adaptive_output,
    safe_render_adaptive_output,
    serialize_report,
)
from furiganalyse.assistance_density import stable_hash

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/phase8_rendering"
SOURCE = FIXTURE / "source"
X = f"{{{XHTML_NS}}}"


def load(name: str):
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


def inputs():
    return tuple(load(name) for name in (
        "book.json", "annotation-plan.json", "grammar-plan.json",
        "assistance.json", "density.json",
    ))


def rehash(value: dict) -> None:
    value.pop("hash", None)
    value["hash"] = stable_hash(value)


def rendered(density=None):
    book, annotation, grammar, assistance, baseline = inputs()
    return render_adaptive_output(
        SOURCE, book, annotation, grammar, assistance,
        baseline if density is None else density, enabled=True,
    )


def test_baseline_is_deterministic_and_matches_golden():
    report_a, files_a = rendered()
    report_b, files_b = rendered()
    assert serialize_report(report_a) == serialize_report(report_b)
    assert files_a == files_b
    assert len(report_a["occurrence_results"]) == 12
    assert len(report_a["document_results"]) == 4
    assert [item["reason"] for item in report_a["diagnostics"]] == [
        "missing-approved-reading"
    ]
    assert report_a == json.loads(
        (ROOT / "tests/phase8_golden/adaptive-rendering-report-v1.json").read_text()
    )
    golden = ROOT / "tests/phase8_golden/adaptive-linked-v1"
    assert files_a == {
        path.relative_to(golden).as_posix(): path.read_bytes()
        for path in sorted(golden.rglob("*.xhtml"))
    }


def test_actions_and_kind_separation():
    report, files = rendered()
    actions = {
        result["source_occurrence_id"]: (
            result["reading_action"], result["meaning_action"], result["grammar_action"]
        )
        for result in report["occurrence_results"]
    }
    assert actions["study-item-0005-occ-0001"][:2] == (
        "reading-presented", "meaning-suppressed"
    )
    assert actions["study-item-0002-occ-0001"][0] == "reading-unavailable"
    assert actions["study-item-0001-occ-0001"][:2] == (
        "reading-suppressed", "meaning-presented"
    )
    assert actions["study-item-0003-occ-0001"][:2] == (
        "reading-suppressed", "meaning-suppressed"
    )
    assert actions["grammar-plan-occurrence-0002"][2] == "grammar-presented"
    assert actions["grammar-plan-occurrence-0003"][2] == "grammar-partial-overlap-rejected"
    assert actions["grammar-plan-occurrence-0006"][2] == "publisher-adjacent-protected"
    notes = ET.fromstring(files["EPUB/text/study-notes.xhtml"])
    classes = {section.get("data-item-id"): section.get("class") for section in notes.findall(f".//{X}section")}
    assert "expression" in classes["study-item-0002"]
    assert "name" in classes["study-item-0005"]


@pytest.mark.parametrize(
    ("reading", "meaning", "expected"),
    [
        ("present-reading", "present-meaning", ("reading-presented", "meaning-presented")),
        ("present-reading", "suppress-meaning", ("reading-presented", "meaning-suppressed")),
        ("suppress-reading", "present-meaning", ("reading-suppressed", "meaning-presented")),
        ("suppress-reading", "suppress-meaning", ("reading-suppressed", "meaning-suppressed")),
    ],
)
def test_all_four_reading_meaning_combinations(reading, meaning, expected):
    density = load("density.json")
    plan = density["occurrence_plans"][2]
    plan["planned_assistance"].update(reading=reading, meaning=meaning)
    plan["input_assistance"].update(
        reading="show-reading" if reading.startswith("present") else "hide-reading",
        meaning="show-meaning" if meaning.startswith("present") else "hide-meaning",
    )
    plan["density_decisions"].update(
        reading="selected-within-budget" if reading.startswith("present") else "suppressed-input-state",
        meaning="selected-within-budget" if meaning.startswith("present") else "suppressed-input-state",
    )
    rehash(plan)
    rehash(density)
    report, _ = rendered(density)
    result = report["occurrence_results"][2]
    assert (result["reading_action"], result["meaning_action"]) == expected


def test_publisher_ruby_visible_text_emphasis_and_links_are_preserved():
    _, files = rendered()
    source = ET.fromstring((SOURCE / "EPUB/text/grammar-01.xhtml").read_bytes())
    output = ET.fromstring(files["EPUB/text/grammar-01.xhtml"])
    source_ruby = source.find(f".//{X}ruby[@id='publisher-ruby-1-8-1']")
    output_ruby = output.find(f".//{X}ruby[@id='publisher-ruby-1-8-1']")
    assert ET.tostring(source_ruby) == ET.tostring(output_ruby)
    assert output_ruby.find(X + "rt").text == "おもてぶたい"
    assert output.find(f".//{X}em/{X}a[@id='src-study-item-0001-occ-0001']") is not None
    assert output.find(f".//{X}a[@id='grammar-src-grammar-occurrence-0005']") is None
    assert output.find(".//*[@id='grammar-src-grammar-occurrence-0005']").tag == X + "span"


def test_suppressed_content_is_absent_not_hidden():
    _, files = rendered()
    combined = b"".join(files.values())
    assert b"to forget completely" not in combined
    assert b"to read every day" not in combined
    assert b"Mae (synthetic name)" not in combined
    assert b"display:none" not in combined
    assert b"data-meaning" not in combined
    assert b"<!--" not in combined


def test_xhtml_is_safe_and_all_fragments_resolve():
    _, files = rendered()
    roots = {path: ET.fromstring(data) for path, data in files.items()}
    ids = {path: {node.get("id") for node in root.iter() if node.get("id")} for path, root in roots.items()}
    assert all(
        root.get("lang") == "ja" and root.get(f"{{{XML_NS}}}lang") == "ja"
        for root in roots.values()
    )
    for path, root in roots.items():
        values = [node.get("id") for node in root.iter() if node.get("id")]
        assert len(values) == len(set(values))
        assert not root.findall(f".//{X}script")
        for link in root.findall(f".//{X}a"):
            target, fragment = link.get("href").split("#", 1)
            target_path = str(Path(path).parent / target)
            assert fragment in ids[target_path]


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (lambda value: value["source_hashes"].update(canonical_book="0" * 64), "source-hash-mismatch"),
        (lambda value: value["occurrence_plans"][0].update(source_occurrence_id="unknown-occurrence"), "unknown-occurrence"),
        (lambda value: value["occurrence_plans"][0].update(sentence_start=1), "invalid-source-offset"),
        (lambda value: value["occurrence_plans"][9]["planned_assistance"].update(reading="suppress-reading"), "publisher-ruby-suppression-attempt"),
        (lambda value: value["occurrence_plans"][5]["planned_assistance"].update(grammar="present-grammar"), "grammar-disposition-conflict"),
    ],
)
def test_safe_failures_copy_input_byte_for_byte(mutator, reason):
    book, annotation, grammar, assistance, density = inputs()
    mutator(density)
    for plan in density["occurrence_plans"]:
        rehash(plan)
    rehash(density)
    report, files = safe_render_adaptive_output(
        SOURCE, book, annotation, grammar, assistance, density, enabled=True
    )
    assert [item["reason"] for item in report["diagnostics"]] == [reason]
    assert report["occurrence_results"] == []
    assert files == {
        path.relative_to(SOURCE).as_posix(): path.read_bytes()
        for path in sorted(SOURCE.rglob("*.xhtml"))
    }


def test_disabled_and_explicit_corrupt_paths_are_reversible():
    book, annotation, grammar, assistance, density = inputs()
    disabled, files = safe_render_adaptive_output(
        SOURCE, book, annotation, grammar, assistance, density, enabled=False
    )
    corrupt, _ = safe_render_adaptive_output(
        SOURCE, book, annotation, grammar, assistance, density,
        enabled=True, failure_reason="corrupt-input",
    )
    assert [item["reason"] for item in disabled["diagnostics"]] == ["disabled"]
    assert [item["reason"] for item in corrupt["diagnostics"]] == ["corrupt-input"]
    assert hashlib.sha256(b"".join(files.values())).hexdigest()
