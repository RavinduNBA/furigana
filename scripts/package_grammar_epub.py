#!/usr/bin/env python3
"""Package validated linked grammar XHTML into a deterministic EPUB."""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.grammar_epub import (  # noqa: E402
    GrammarEpubError,
    build_grammar_epub,
    validate_archive,
)


def _report(path: Path | None, packaged: bool, reason: str | None):
    if path is None:
        return
    value = {
        "schema_version": 1,
        "packaged": packaged,
        "diagnostics": [] if reason is None else [
            {"id": "grammar-epub-diagnostic-0001", "reason": reason}
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fallback(source: Path, output: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-epub", required=True, type=Path)
    parser.add_argument("--linked-dir", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enabled", action="store_true")
    args = parser.parse_args()
    if not args.enabled:
        _fallback(args.input_epub, args.output)
        _report(args.report, False, "disabled")
        return
    try:
        if args.linked_dir is None:
            raise GrammarEpubError("invalid-input")
        files = build_grammar_epub(args.input_epub, args.linked_dir, args.output)
        validate_archive(args.output, grammar=True)
    except GrammarEpubError as error:
        if args.output.exists():
            args.output.unlink()
        _fallback(args.input_epub, args.output)
        _report(args.report, False, error.reason)
        return
    _report(args.report, True, None)
    print(f"Wrote deterministic grammar EPUB with {len(files)} members")


if __name__ == "__main__":
    main()
