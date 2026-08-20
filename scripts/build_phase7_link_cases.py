#!/usr/bin/env python3
"""Build deterministic ambiguous XHTML input for the Phase 7 grammar-link gate."""

import argparse
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET

X = "{http://www.w3.org/1999/xhtml}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--ambiguous-dir", required=True)
    args = parser.parse_args()
    source, target = Path(args.source_dir), Path(args.ambiguous_dir)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    chapter = target / "EPUB/text/grammar-01.xhtml"
    root = ET.fromstring(chapter.read_bytes())
    paragraph = root.find(".//" + X + "p[@id='grammar-block-1-5']")
    span = paragraph.find(X + "span")
    span.text = "また読ん"
    split = ET.SubElement(span, X + "em")
    split.text = "でいる"
    split.tail = "。"
    ET.ElementTree(root).write(chapter, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    main()
