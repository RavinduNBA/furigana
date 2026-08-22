#!/usr/bin/env python3
"""Build deterministic malformed inputs for Phase 8 rendering safe paths."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

from furiganalyse.assistance_density import stable_hash


def rehash(value: dict) -> None:
    value.pop("hash", None)
    value["hash"] = stable_hash(value)


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    density = json.loads((args.fixture / "density.json").read_text())
    assistance = json.loads((args.fixture / "assistance.json").read_text())

    stale = copy.deepcopy(density)
    stale["source_hashes"]["canonical_book"] = "0" * 64
    rehash(stale)
    write(args.output / "stale-density.json", stale)

    offset = copy.deepcopy(density)
    offset["occurrence_plans"][0]["sentence_start"] = 1
    rehash(offset["occurrence_plans"][0])
    rehash(offset)
    write(args.output / "offset-density.json", offset)

    publisher = copy.deepcopy(density)
    publisher["occurrence_plans"][9]["planned_assistance"]["reading"] = "suppress-reading"
    rehash(publisher["occurrence_plans"][9])
    rehash(publisher)
    write(args.output / "publisher-density.json", publisher)

    grammar = copy.deepcopy(density)
    grammar["occurrence_plans"][5]["planned_assistance"]["grammar"] = "present-grammar"
    rehash(grammar["occurrence_plans"][5])
    rehash(grammar)
    write(args.output / "grammar-density.json", grammar)

    invalid = copy.deepcopy(assistance)
    invalid["schema_version"] = 99
    rehash(invalid)
    write(args.output / "invalid-assistance.json", invalid)
    (args.output / "corrupt.json").write_text("{corrupt\n", encoding="utf-8")

    shutil.copytree(args.fixture / "source", args.output / "ambiguous-source", dirs_exist_ok=True)
    (args.output / "ambiguous-source/EPUB/text/extra.xhtml").write_text(
        "<?xml version='1.0' encoding='utf-8'?><html xmlns='http://www.w3.org/1999/xhtml' lang='ja'><body/></html>\n",
        encoding="utf-8",
    )
    shutil.copytree(args.fixture / "source", args.output / "broken-source", dirs_exist_ok=True)
    note = args.output / "broken-source/EPUB/text/study-notes.xhtml"
    note.write_text(
        note.read_text(encoding="utf-8").replace(
            "grammar-01.xhtml#src-study-item-0001-occ-0001",
            "grammar-01.xhtml#missing-fragment",
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
