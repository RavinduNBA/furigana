import copy
import hashlib
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from furiganalyse.linked_output import (
    X,
    LinkedOutputError,
    _leaf_blocks,
    _ruby_snapshot,
    _validate_links,
    _visible_map,
    create_linked_output,
    write_linked_output,
)

ROOT = Path(__file__).resolve().parents[1]
EPUB = ROOT / "artifacts/phase2/fixture.epub"
BOOK = ROOT / "artifacts/phase2/run-a/book.json"
PLAN = ROOT / "tests/phase4_golden/annotation-plan-v1.json"


@pytest.fixture
def inputs():
    if not EPUB.exists() or not BOOK.exists():
        pytest.fail("run scripts/phase3-regression.sh first")
    return (
        json.loads(BOOK.read_text(encoding="utf-8")),
        json.loads(PLAN.read_text(encoding="utf-8")),
    )


def roots(output):
    return {path: ET.fromstring(data) for path, data in output.files.items()}


def test_legal_fixture_has_six_resolving_forward_links_and_backlinks(inputs):
    book, plan = inputs
    output = create_linked_output(EPUB, book, plan)
    documents = roots(output)
    assert sorted(documents) == [
        "EPUB/text/chapter-01.xhtml",
        "EPUB/text/chapter-02.xhtml",
        "EPUB/text/study-notes.xhtml",
    ]
    forwards = [
        link
        for path, root in documents.items()
        if path != output.notes_path
        for link in root.findall(".//" + X + "a")
        if "study-link" in link.attrib.get("class", "").split()
    ]
    backlinks = documents[output.notes_path].findall(
        ".//" + X + "a[@class='study-note__backlink']"
    )
    assert len(forwards) == len(backlinks) == 6
    assert len(_validate_links(output.files)) == 12
    assert [link.attrib["id"] for link in forwards] == [
        occurrence["source_anchor_id"]
        for item in plan["items"]
        for occurrence in item["occurrences"]
    ]


def test_contexts_are_exact_canonical_sentences_in_occurrence_order(inputs):
    book, plan = inputs
    output = create_linked_output(EPUB, book, plan)
    note_root = roots(output)[output.notes_path]
    sentences = {
        sentence["id"]: sentence
        for chapter in book["chapters"]
        for block in chapter["blocks"]
        for sentence in block["sentences"]
    }
    records = note_root.findall(".//" + X + "div[@class='study-note__occurrence']")
    expected = [
        occurrence for item in plan["items"] for occurrence in item["occurrences"]
    ]
    assert [record.attrib["data-occurrence-id"] for record in records] == [
        occurrence["id"] for occurrence in expected
    ]
    for occurrence, record in zip(expected, records):
        quote = record.find(X + "blockquote")
        assert "".join(quote.itertext()) == sentences[occurrence["sentence_id"]]["text"]
        assert (
            quote.find(X + "mark").text
            == sentences[occurrence["sentence_id"]]["text"][
                occurrence["sentence_start"] : occurrence["sentence_end"]
            ]
        )
        assert "おもてぶたい" not in "".join(quote.itertext())
        assert "ゆきの" not in "".join(quote.itertext())


def test_source_text_markup_links_and_publisher_ruby_are_preserved(inputs):
    book, plan = inputs
    before_hash = hashlib.sha256(EPUB.read_bytes()).hexdigest()
    output = create_linked_output(EPUB, book, plan)
    assert hashlib.sha256(EPUB.read_bytes()).hexdigest() == before_hash
    documents = roots(output)
    with zipfile.ZipFile(EPUB) as archive:
        originals = {
            chapter["source_path"]: ET.fromstring(archive.read(chapter["source_path"]))
            for chapter in book["chapters"]
        }
    for chapter in book["chapters"]:
        original = originals[chapter["source_path"]]
        linked = documents[chapter["source_path"]]
        assert [_visible_map(x)[0] for x in _leaf_blocks(linked)] == [
            block["text"] for block in chapter["blocks"]
        ]
        original_ruby = {
            ruby.attrib["id"]: _ruby_snapshot(ruby)
            for ruby in original.findall(".//" + X + "ruby")
        }
        linked_ruby = {
            ruby.attrib["id"]: _ruby_snapshot(ruby)
            for ruby in linked.findall(".//" + X + "ruby")
        }
        assert linked_ruby == original_ruby
    chapter_1 = documents["EPUB/text/chapter-01.xhtml"]
    assert chapter_1.find(".//" + X + "em/" + X + "a").text == "言葉"
    assert (
        chapter_1.find(".//" + X + "a[@href='#chapter-01']/" + X + "ruby") is not None
    )
    chapter_2 = documents["EPUB/text/chapter-02.xhtml"]
    fallback = chapter_2.find(".//" + X + "ruby[@id='publisher-fallback']")
    assert [child.tag for child in fallback] == [X + "rb", X + "rp", X + "rt", X + "rp"]
    assert all(
        not ruby.findall(".//" + X + "ruby")
        for document in documents.values()
        for ruby in document.findall(".//" + X + "ruby")
    )


def test_two_runs_and_extracted_input_are_byte_identical(inputs, tmp_path):
    book, plan = inputs
    first = create_linked_output(EPUB, book, plan)
    second = create_linked_output(EPUB, book, plan)
    assert first == second
    extracted = tmp_path / "fixture"
    with zipfile.ZipFile(EPUB) as archive:
        archive.extractall(extracted)
    third = create_linked_output(extracted, book, plan)
    assert third == first
    target = tmp_path / "linked"
    write_linked_output(first, target)
    assert {
        path.relative_to(target).as_posix(): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file()
    } == first.files


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda book, plan: plan.update(book_id="wrong"), "identity mismatch"),
        (
            lambda book, plan: plan["items"][0]["occurrences"][0].update(
                chapter_id="missing"
            ),
            "Unknown sentence|chapter",
        ),
        (
            lambda book, plan: plan["items"][0]["occurrences"][0].update(block_start=0),
            "Block offset mismatch",
        ),
        (
            lambda book, plan: book["chapters"][0].update(
                source_path="../unsafe.xhtml"
            ),
            "Unsafe output path",
        ),
    ],
)
def test_rejects_invalid_references_offsets_and_paths(inputs, mutation, message):
    book, plan = copy.deepcopy(inputs)
    mutation(book, plan)
    with pytest.raises(LinkedOutputError, match=message):
        create_linked_output(EPUB, book, plan)


def test_rejects_selection_inside_existing_anchor(inputs, tmp_path):
    book, plan = inputs
    extracted = tmp_path / "fixture"
    with zipfile.ZipFile(EPUB) as archive:
        archive.extractall(extracted)
    path = extracted / "EPUB/text/chapter-01.xhtml"
    root = ET.fromstring(path.read_bytes())
    paragraph = _leaf_blocks(root)[1]
    paragraph.text = "「今日は"
    existing = ET.Element(X + "a", {"href": "#chapter-01"})
    existing.text = "良い天気だ"
    existing.tail = "ね」と彼女は言った。"
    paragraph.append(existing)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    with pytest.raises(LinkedOutputError, match="inside an existing link"):
        create_linked_output(extracted, book, plan)


def test_rejects_selection_crossing_dom_text_slots(inputs, tmp_path):
    book, plan = inputs
    extracted = tmp_path / "fixture"
    with zipfile.ZipFile(EPUB) as archive:
        archive.extractall(extracted)
    path = extracted / "EPUB/text/chapter-01.xhtml"
    root = ET.fromstring(path.read_bytes())
    paragraph = _leaf_blocks(root)[1]
    paragraph.text = "「今日は"
    span = ET.Element(X + "span")
    span.text = "良い"
    span.tail = "天気だね」と彼女は言った。"
    paragraph.append(span)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    with pytest.raises(LinkedOutputError, match="Ambiguous text insertion"):
        create_linked_output(extracted, book, plan)


def test_generated_link_validator_rejects_broken_or_escaping_href(inputs):
    book, plan = inputs
    output = create_linked_output(EPUB, book, plan)
    files = dict(output.files)
    root = ET.fromstring(files[output.notes_path])
    link = root.find(".//" + X + "a[@class='study-note__backlink']")
    link.attrib["href"] = "../../../outside.xhtml#missing"
    files[output.notes_path] = ET.tostring(root, encoding="utf-8")
    with pytest.raises(LinkedOutputError, match="Unsafe or unresolved"):
        _validate_links(files)
