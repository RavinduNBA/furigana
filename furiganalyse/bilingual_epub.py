"""EPUB Companion Chapter Renderer for Phase 10 Bilingual Output."""

from __future__ import annotations

import html
import posixpath
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from furiganalyse.bilingual_translation import TranslationChapter

CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
XHTML_NS = "http://www.w3.org/1999/xhtml"
OPF_NS = "http://www.idpf.org/2007/opf"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"


def find_opf_path(file_map: dict[str, bytes]) -> str:
    """Finds the package OPF file path from container.xml or by extension."""
    if "META-INF/container.xml" in file_map:
        container = ET.fromstring(file_map["META-INF/container.xml"])
        rootfile = container.find(f".//{{{CONTAINER_NS}}}rootfile")
        if rootfile is not None and rootfile.attrib.get("full-path"):
            full_path = rootfile.attrib["full-path"]
            if full_path in file_map:
                return full_path
    for name in file_map:
        if name.endswith(".opf"):
            return name
    raise ValueError("Could not find OPF package document in EPUB")

BILINGUAL_CSS = """
/* Bilingual Companion Chapter Styles */
.bilingual-chapter {
  font-family: "Georgia", "Times New Roman", serif;
  line-height: 1.7;
  margin: 1.5em auto;
  max-width: 42em;
  padding: 0 1em;
  color: #1a1a1a;
}
.bilingual-header {
  border-bottom: 2px solid #e0e0e0;
  margin-bottom: 2em;
  padding-bottom: 0.8em;
  text-align: center;
}
.bilingual-title {
  font-size: 1.6em;
  font-weight: 700;
  margin: 0.2em 0;
  color: #2c3e50;
}
.bilingual-subtitle {
  font-size: 0.95em;
  color: #7f8c8d;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.bilingual-paragraph {
  margin: 1em 0;
  text-indent: 1.5em;
  text-align: justify;
}
.bilingual-dialogue {
  margin: 0.8em 0;
  padding-left: 0.5em;
}
.bilingual-backlink {
  display: inline-block;
  font-size: 0.8em;
  color: #3498db;
  text-decoration: none;
  margin-left: 0.5em;
}
.bilingual-footnote {
  font-size: 0.85em;
  color: #666;
  background-color: #f8f9fa;
  border-left: 3px solid #3498db;
  padding: 0.5em 1em;
  margin: 0.8em 0;
}
"""


def render_translation_xhtml(chapter: TranslationChapter, orig_xhtml_name: str | None = None) -> str:
    """Renders a TranslationChapter into a clean XHTML document."""
    paragraphs_html = []

    for p in chapter.paragraphs:
        eng_text = html.escape(p.english_translation).strip()
        if not eng_text:
            continue

        is_dialogue = eng_text.startswith(('"', "“", "'", "‘"))
        p_class = "bilingual-dialogue" if is_dialogue else "bilingual-paragraph"

        backlink_html = ""
        if orig_xhtml_name and p.block_id:
            backlink_html = f' <a class="bilingual-backlink" href="{orig_xhtml_name}#{p.block_id}" title="Jump to Japanese text">🇯🇵</a>'

        paragraphs_html.append(f'  <p class="{p_class}" id="trans-{p.block_id}">{eng_text}{backlink_html}</p>')

        for fn in p.footnotes:
            fn_text = html.escape(fn).strip()
            if fn_text:
                paragraphs_html.append(f'  <div class="bilingual-footnote"><em>Note:</em> {fn_text}</div>')

    content = "\n".join(paragraphs_html)

    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="{XHTML_NS}" xml:lang="en" lang="en">
<head>
  <meta charset="utf-8"/>
  <title>{html.escape(chapter.title)} (English Translation)</title>
  <style type="text/css">
{BILINGUAL_CSS}
  </style>
</head>
<body class="bilingual-chapter">
  <header class="bilingual-header">
    <div class="bilingual-subtitle">English Companion Translation</div>
    <h1 class="bilingual-title">{html.escape(chapter.title)}</h1>
  </header>
  <main>
{content}
  </main>
</body>
</html>
"""


def package_bilingual_epub(
    input_epub_path: str | Path,
    output_epub_path: str | Path,
    translation_chapters: list[TranslationChapter],
) -> None:
    """Injects translation companion chapters into an EPUB without altering original Japanese documents."""
    input_epub = Path(input_epub_path)
    output_epub = Path(output_epub_path)

    with zipfile.ZipFile(input_epub, "r") as src:
        file_map = {name: src.read(name) for name in src.namelist()}

    opf_path = find_opf_path(file_map)
    opf_dir = posixpath.dirname(opf_path)
    opf_root = ET.fromstring(file_map[opf_path])

    # Find manifest and spine
    manifest = opf_root.find(f"{{{OPF_NS}}}manifest")
    spine = opf_root.find(f"{{{OPF_NS}}}spine")

    if manifest is None or spine is None:
        raise ValueError("Invalid EPUB OPF: missing manifest or spine")

    # Map existing spine items to their hrefs
    item_by_id = {item.get("id"): item.get("href") for item in manifest.findall(f"{{{OPF_NS}}}item")}
    spine_items = [itemref.get("idref") for itemref in spine.findall(f"{{{OPF_NS}}}itemref")]

    # Render each translation chapter
    for idx, trans_ch in enumerate(translation_chapters, start=1):
        ch_id = trans_ch.chapter_id
        # Determine matching original xhtml file from spine
        raw_orig_href = None
        insert_pos = len(spine)

        # Look for matching chapter ID in spine
        for s_idx, s_id in enumerate(spine_items):
            href = item_by_id.get(s_id, "")
            if ch_id in s_id or ch_id in href:
                raw_orig_href = href
                insert_pos = s_idx + 1
                break

        trans_filename = f"ch-{idx:04d}-translation.xhtml"
        orig_subdir = posixpath.dirname(raw_orig_href) if raw_orig_href else ""
        trans_href = posixpath.join(orig_subdir, trans_filename) if orig_subdir else trans_filename
        trans_rel_path = posixpath.join(opf_dir, trans_href) if opf_dir else trans_href
        orig_basename = posixpath.basename(raw_orig_href) if raw_orig_href else None

        xhtml_content = render_translation_xhtml(trans_ch, orig_xhtml_name=orig_basename)
        file_map[trans_rel_path] = xhtml_content.encode("utf-8")

        trans_item_id = f"trans-item-{idx:04d}"

        # Add to manifest
        item_elem = ET.Element(f"{{{OPF_NS}}}item", {
            "id": trans_item_id,
            "href": trans_href,
            "media-type": "application/xhtml+xml",
        })
        manifest.append(item_elem)

        # Add to spine immediately after original chapter
        itemref_elem = ET.Element(f"{{{OPF_NS}}}itemref", {
            "idref": trans_item_id,
        })
        spine.insert(insert_pos, itemref_elem)

    # Serialize updated OPF
    file_map[opf_path] = ET.tostring(opf_root, encoding="utf-8", xml_declaration=True)

    # Write output EPUB with uncompressed mimetype first
    with zipfile.ZipFile(output_epub, "w") as dst:
        if "mimetype" in file_map:
            dst.writestr("mimetype", file_map["mimetype"], compress_type=zipfile.ZIP_STORED)
        for name, data in file_map.items():
            if name != "mimetype":
                dst.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
