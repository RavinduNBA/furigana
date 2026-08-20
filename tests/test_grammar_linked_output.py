import copy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from furiganalyse.grammar_analysis import load_json, stable_hash
from furiganalyse.grammar_linked_output import (
    X, LINKABLE, _validate_links, create_grammar_linked_output,
)
from furiganalyse.linked_output import LinkedOutputError, _leaf_blocks, _ruby_snapshot, _visible_map
from scripts.build_phase7_fixture import build, write_source_fixture

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inputs(tmp_path):
    spec = load_json(ROOT / "tests/fixtures/phase7-passages-v1.json")
    book, _, annotation = build(spec)
    plan = load_json(ROOT / "tests/phase7_golden/grammar-plan-v1.json")
    dataset = load_json(ROOT / "tests/fixtures/phase7-grammar-rules-v1.json")
    source = tmp_path / "source"
    write_source_fixture(spec, annotation, source)
    return source, book, plan, dataset


def roots(output):
    return {path: ET.fromstring(data) for path, data in output.files.items()}


def test_three_forward_links_backlinks_and_seven_contexts(inputs):
    output = create_grammar_linked_output(*inputs)
    documents = roots(output)
    forwards = [
        link for path, root in documents.items() if path != output.notes_path
        for link in root.findall(".//" + X + "a[@class='grammar-link']")
    ]
    notes = documents[output.notes_path]
    backlinks = notes.findall(".//" + X + "a[@class='grammar-study-note__backlink']")
    contexts = notes.findall(".//" + X + "blockquote[@class='grammar-study-note__context']")
    assert len(forwards) == len(backlinks) == 3
    assert len(contexts) == 7 and len(_validate_links(output.files)) == 6
    assert [link.attrib["id"] for link in forwards] == [
        "grammar-src-grammar-occurrence-0002",
        "grammar-src-grammar-occurrence-0005",
        "grammar-src-grammar-occurrence-0008",
    ]


def test_contexts_and_dispositions_follow_plan_without_recalculation(inputs):
    _, book, plan, _ = inputs
    output = create_grammar_linked_output(*inputs)
    note = roots(output)[output.notes_path]
    records = note.findall(".//" + X + "div[@class='grammar-study-note__occurrence']")
    assert [x.attrib["data-occurrence-id"] for x in records] == [
        ref for item in plan["items"] for ref in item["occurrence_ids"]
    ]
    occurrence = {x["id"]: x for x in plan["occurrences"]}
    sentence = {
        x["id"]: x for chapter in book["chapters"] for block in chapter["blocks"]
        for x in block["sentences"]
    }
    for record in records:
        source = occurrence[record.attrib["data-occurrence-id"]]
        quote = record.find(X + "blockquote")
        assert "".join(quote.itertext()) == sentence[source["sentence_id"]]["text"]
        assert quote.find(X + "mark").text == source["surface"]
        assert record.attrib["data-disposition"] == source["link_disposition"]
        assert (record.find(".//" + X + "a") is not None) == (source["link_disposition"] in LINKABLE)


def test_repeated_teiru_has_reference_linked_and_publisher_statuses(inputs):
    output = create_grammar_linked_output(*inputs)
    note = roots(output)[output.notes_path]
    section = note.find(".//" + X + "section[@data-grammar-item-id='grammar-item-0001']")
    records = section.findall(".//" + X + "div[@class='grammar-study-note__occurrence']")
    assert [x.attrib["data-disposition"] for x in records] == [
        "grammar-note-reference-only", "grammar-link", "publisher-ruby-preserved"
    ]
    assert [x.find(X + "p").text for x in records] == [
        "reference only", "linked", "publisher ruby preserved"
    ]
    assert records[0].find(".//" + X + "a") is None
    assert records[1].find(".//" + X + "a") is not None
    assert records[2].find(".//" + X + "a") is None


def test_vocabulary_links_visible_text_emphasis_and_ruby_are_preserved(inputs):
    source, book, _, _ = inputs
    output = create_grammar_linked_output(*inputs)
    documents = roots(output)
    for chapter in book["chapters"]:
        before = ET.fromstring((source / chapter["source_path"]).read_bytes())
        after = documents[chapter["source_path"]]
        assert [_visible_map(x)[0] for x in _leaf_blocks(after)] == [x["text"] for x in chapter["blocks"]]
        before_links = {x.get("id"): "".join(x.itertext()) for x in before.findall(".//" + X + "a[@class='study-link']")}
        after_links = {x.get("id"): "".join(x.itertext()) for x in after.findall(".//" + X + "a[@class='study-link']")}
        assert before_links == after_links
        assert {x.get("id"): _ruby_snapshot(x) for x in before.findall(".//" + X + "ruby")} == {
            x.get("id"): _ruby_snapshot(x) for x in after.findall(".//" + X + "ruby")
        }
    assert documents["EPUB/text/grammar-01.xhtml"].find(".//" + X + "em/" + X + "a[@class='study-link']").text == "読ん"
    assert output.files["EPUB/text/study-notes.xhtml"] == (source / "EPUB/text/study-notes.xhtml").read_bytes()


def test_reference_partial_exact_and_publisher_cases_have_no_source_anchor(inputs):
    _, _, plan, _ = inputs
    output = create_grammar_linked_output(*inputs)
    documents = roots(output)
    ids = {x.get("id") for root in documents.values() for x in root.iter() if x.get("id")}
    for occurrence in plan["occurrences"]:
        assert (occurrence["source_anchor_id"] in ids) == (occurrence["link_disposition"] in LINKABLE)


def test_two_runs_are_byte_identical_and_no_unsafe_markup(inputs):
    first = create_grammar_linked_output(*inputs)
    assert first == create_grammar_linked_output(*inputs)
    for data in first.files.values():
        root = ET.fromstring(data)
        assert not root.findall(".//" + X + "script")
        assert all(not link.findall(".//" + X + "a") for link in root.findall(".//" + X + "a"))


def test_rejects_stale_offsets_ambiguous_mapping_and_nested_anchor(inputs, tmp_path):
    source, book, plan, dataset = inputs
    stale = copy.deepcopy(book)
    stale["chapters"][0]["blocks"][4]["text"] = "違う。"
    with pytest.raises(LinkedOutputError, match="Stale"):
        create_grammar_linked_output(source, stale, plan, dataset)
    offset_mismatch = copy.deepcopy(plan)
    occurrence = offset_mismatch["occurrences"][4]
    occurrence["block_start"] += 1
    occurrence["block_end"] += 1
    occurrence["hash"] = stable_hash({k: v for k, v in occurrence.items() if k != "hash"})
    with pytest.raises(LinkedOutputError, match="offset mismatch"):
        create_grammar_linked_output(source, book, offset_mismatch, dataset)
    bad = tmp_path / "bad"
    write_source_fixture(load_json(ROOT / "tests/fixtures/phase7-passages-v1.json"), build(load_json(ROOT / "tests/fixtures/phase7-passages-v1.json"))[2], bad)
    chapter = bad / "EPUB/text/grammar-01.xhtml"
    root = ET.fromstring(chapter.read_bytes())
    paragraph = root.find(".//" + X + "p[@id='grammar-block-1-5']")
    span = paragraph.find(X + "span")
    span.text = "また読ん"
    split = ET.SubElement(span, X + "em")
    split.text = "でいる"
    split.tail = "。"
    ET.ElementTree(root).write(chapter, encoding="utf-8", xml_declaration=True)
    with pytest.raises(LinkedOutputError, match="Canonical|Ambiguous"):
        create_grammar_linked_output(bad, book, plan, dataset)


def test_phase4_and_phase5_linked_outputs_remain_byte_identical():
    for phase, golden in (
        (ROOT / "artifacts/phase4/linked/run-a", ROOT / "tests/phase4_golden/linked-v1"),
        (ROOT / "artifacts/phase5/rendered/run-a/linked", ROOT / "tests/phase5_golden/linked-v2"),
    ):
        assert {x.relative_to(phase).as_posix(): x.read_bytes() for x in phase.rglob("*.xhtml")} == {
            x.relative_to(golden).as_posix(): x.read_bytes() for x in golden.rglob("*.xhtml")
        }
