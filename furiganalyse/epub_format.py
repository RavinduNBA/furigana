import logging
import os
import re
import zipfile
from pathlib import Path
from typing import Callable, Dict, Optional, Set
from xml.etree import ElementTree as ET

from furiganalyse.params import OutputFormat, WritingMode
from furiganalyse.parsing import process_html, convert_html_to_txt

# Register XHTML namespace with empty prefix (default namespace)
# This prevents ElementTree from adding 'html:' prefix to all elements when serializing
ET.register_namespace('', 'http://www.w3.org/1999/xhtml')

ProgressCallback = Callable[[Dict[str, int | str]], None]
_NON_VISIBLE_ELEMENTS = {"script", "style", "rt", "rp"}


def _visible_character_count(tree: ET.ElementTree) -> int:
    """Count source characters without copying text into progress telemetry."""
    def text_count(value: Optional[str]) -> int:
        return sum(1 for character in value or "" if not character.isspace())

    def count(element: ET.Element, hidden: bool = False) -> int:
        hidden = hidden or element.tag.rsplit("}", 1)[-1] in _NON_VISIBLE_ELEMENTS
        subtotal = 0 if hidden else text_count(element.text)
        for child in element:
            subtotal += count(child, hidden)
            if not hidden:
                subtotal += text_count(child.tail)
        return subtotal

    return count(tree.getroot())


def collect_epub_progress_metrics(unzipped_input_fpath: str) -> list[dict[str, int | str]]:
    """Return deterministic aggregate metrics for processable EPUB documents."""
    documents = []
    root = Path(unzipped_input_fpath)
    for path in sorted(
        candidate
        for candidate in root.rglob("*")
        if candidate.is_file() and candidate.suffix.lower() in {".html", ".xhtml"}
    ):
        tree = ET.parse(path)
        documents.append({
            "document": path.relative_to(root).as_posix(),
            "characters": _visible_character_count(tree),
        })
    return documents


def process_epub_file(
    unzipped_input_fpath,
    mode,
    writing_mode,
    output_format,
    exclude_words: Optional[Set[str]] = None,
    progress_callback: Optional[ProgressCallback] = None,
):
    if writing_mode is not None and str(getattr(writing_mode, "value", writing_mode)) != "auto":
        update_writing_mode(unzipped_input_fpath, writing_mode)
    _ensure_ruby_css_rules(unzipped_input_fpath)

    documents = collect_epub_progress_metrics(unzipped_input_fpath)
    total_characters = sum(int(value["characters"]) for value in documents)
    if progress_callback:
        progress_callback({
            "stage": "processing",
            "sections_total": len(documents),
            "sections_completed": 0,
            "characters_total": total_characters,
            "characters_processed": 0,
            "log": f"Furigana Engine: Loaded {len(documents)} XHTML sections ({total_characters:,} visible characters) for annotation",
        })

    processed_characters = 0
    for index, document in enumerate(documents, start=1):
        html_filepath = os.path.join(unzipped_input_fpath, str(document["document"]))
        logging.info("    Processing section %d of %d", index, len(documents))
        tree = process_html(html_filepath, mode, exclude_words)
        if output_format in {OutputFormat.many_txt, OutputFormat.single_txt, OutputFormat.apkg}:
            txt_outputfile = os.path.splitext(html_filepath)[0] + '.txt'
            convert_html_to_txt(tree, txt_outputfile)
        else:
            tree.write(html_filepath, encoding="utf-8")
        chars_in_doc = int(document["characters"])
        processed_characters += chars_in_doc
        if progress_callback:
            event = {
                "stage": "processing",
                "sections_total": len(documents),
                "sections_completed": index,
                "characters_total": total_characters,
                "characters_processed": processed_characters,
            }
            if chars_in_doc > 0:
                doc_name = os.path.basename(str(document["document"]))
                event["log"] = f"Furigana Pass: Section {index}/{len(documents)} ({doc_name}) annotated [{chars_in_doc:,} chars]"
            progress_callback(event)


def _ensure_ruby_css_rules(unzipped_input_fpath: str):
    """Add subtle ruby typography and link rules to ensure clean spacing, alignment, and reading flow."""
    ruby_css = """
/* Furiganalyse Ruby & Link Typography */
ruby {
    ruby-align: space-around;
    ruby-position: over;
    -webkit-ruby-position: before;
}
ruby rt {
    font-size: 0.55em;
    text-align: center;
    letter-spacing: 0.05em;
    padding: 0 0.08em;
}
a.study-link, a.guided-link {
    text-decoration: none !important;
    border-bottom: 1px dotted rgba(80, 120, 200, 0.45);
    color: inherit !important;
}
a.study-link:hover, a.guided-link:hover {
    border-bottom: 1px solid rgba(80, 120, 200, 0.85);
}
"""
    for css_filepath in Path(unzipped_input_fpath).glob('**/*.css'):
        try:
            with open(css_filepath, "r", encoding="utf-8") as fd:
                content = fd.read()
            if "Furiganalyse Ruby" not in content and "space-around" not in content:
                with open(css_filepath, "a", encoding="utf-8") as fd:
                    fd.write(ruby_css)
        except Exception:
            pass


def update_writing_mode(unzipped_input_fpath: str, writing_mode: WritingMode):
    mode_value = getattr(writing_mode, "value", str(writing_mode))
    for css_filepath in Path(unzipped_input_fpath).glob('**/*.css'):
        with open(css_filepath) as fd:
            css_content = fd.read()

        pattern = re.compile(r"(-webkit-writing-mode|-epub-writing-mode|writing-mode):\s*[^;\n]+")
        css_content = pattern.sub(rf"\1: {mode_value}", css_content)

        with open(css_filepath, "w") as fd:
            fd.write(css_content)

    # content.opf has a tag like this: <meta name="primary-writing-mode" content="vertical-rl"/>
    # content_opf_path: Path = Path(unzipped_input_fpath) / "content.opf"
    # if content_opf_path.exists():
    #     from xml.etree import ElementTree as ET
    #     tree = ET.parse(content_opf_path)
    #     # import ipdb; ipdb.set_trace()
    #     x: ET.Element = tree.find(".//{http://www.idpf.org/2007/opf}meta[@name='primary-writing-mode']")
    #     x.attrib["content"] = writing_mode.value
    #     tree.write(content_opf_path, encoding="utf-8")


def write_epub_archive(unzipped_input_fpath: str, outputfile: str):
    """
    Write the modified extracted EPUB archive to a new archive file.
    """
    with zipfile.ZipFile(outputfile, 'w') as zip_out:
        root = Path(unzipped_input_fpath)
        members_added = 0
        mimetype_path = root / "mimetype"
        if mimetype_path.is_file():
            zip_out.writestr("mimetype", mimetype_path.read_bytes(),
                             compress_type=zipfile.ZIP_STORED)
            members_added += 1
        for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
            rel_file = file_path.relative_to(root).as_posix()
            if rel_file == "mimetype":
                continue
            zip_out.write(file_path, rel_file,
                          compress_type=zipfile.ZIP_DEFLATED)
            members_added += 1
        logging.info("    Added %d archive members", members_added)
