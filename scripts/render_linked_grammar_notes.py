#!/usr/bin/env python3
"""Render deterministic grammar links and contexts without packaging an EPUB."""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.grammar_linked_output import (  # noqa: E402
    create_grammar_linked_output,
    write_grammar_linked_output,
)
from furiganalyse.grammar_notes import GrammarNoteError, load_json  # noqa: E402
from furiganalyse.linked_output import LinkedOutputError  # noqa: E402


def _copy_source(source, output):
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(source, output)


def _report(path, rendered, reason=None):
    value = {"schema_version": 1, "rendered": rendered, "diagnostics": []}
    if reason:
        value["diagnostics"] = [{"id": "grammar-linked-diagnostic-0001", "reason": reason}]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--book", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--disabled", action="store_true")
    args = parser.parse_args()
    if args.disabled:
        _copy_source(args.source_dir, args.output_dir)
        _report(args.report, False, "disabled")
        return
    reason = None
    try:
        if not args.book or not args.plan or not args.dataset:
            raise GrammarNoteError("Invalid input")
        output = create_grammar_linked_output(
            args.source_dir, load_json(args.book), load_json(args.plan), load_json(args.dataset)
        )
    except (OSError, json.JSONDecodeError):
        reason = "corrupt-input"
    except (GrammarNoteError, LinkedOutputError, KeyError, TypeError, ValueError) as error:
        message = str(error).lower()
        reason = "stale-input" if "stale" in message else "ambiguous-input" if "ambiguous" in message else "invalid-input"
    if reason:
        _copy_source(args.source_dir, args.output_dir)
        _report(args.report, False, reason)
        return
    if args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    write_grammar_linked_output(output, args.output_dir)
    _report(args.report, True)


if __name__ == "__main__":
    main()
