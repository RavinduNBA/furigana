#!/usr/bin/env python3
"""Build deterministic safe-failure linked-XHTML cases for Phase 7 packaging."""

import argparse
from pathlib import Path, PurePosixPath

FILES = (
    "EPUB/text/grammar-01.xhtml",
    "EPUB/text/grammar-02.xhtml",
    "EPUB/text/study-notes.xhtml",
    "EPUB/text/grammar-notes.xhtml",
)


def copy_case(source: Path, target: Path, *, skip=()):
    for relative in FILES:
        destination = target / PurePosixPath(relative)
        if relative in skip:
            if destination.exists():
                destination.unlink()
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((source / PurePosixPath(relative)).read_bytes())


def replace(path: Path, old: bytes, new: bytes):
    value = path.read_bytes()
    if old not in value:
        raise ValueError("fixture replacement target missing")
    path.write_bytes(value.replace(old, new, 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--linked-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    for name in ("stale", "invalid", "corrupt", "ambiguous", "unsafe", "broken-fragment"):
        copy_case(
            args.linked_dir,
            args.output_dir / name,
            skip={"EPUB/text/grammar-notes.xhtml"} if name == "invalid" else set(),
        )
    stale = args.output_dir / "stale/EPUB/text/study-notes.xhtml"
    stale.write_bytes(stale.read_bytes() + b"\n")
    (args.output_dir / "corrupt/EPUB/text/grammar-notes.xhtml").write_bytes(b"<not-xhtml")
    replace(
        args.output_dir / "ambiguous/EPUB/text/grammar-01.xhtml",
        "</a>。</span>".encode(),
        "</a>！</span>".encode(),
    )
    replace(
        args.output_dir / "unsafe/EPUB/text/grammar-notes.xhtml",
        b"grammar-01.xhtml#grammar-src-grammar-occurrence-0005",
        b"../../mimetype",
    )
    replace(
        args.output_dir / "broken-fragment/EPUB/text/grammar-notes.xhtml",
        b"#grammar-src-grammar-occurrence-0005",
        b"#missing-fragment",
    )
    print("Wrote deterministic Phase 7 EPUB failure cases")


if __name__ == "__main__":
    main()
