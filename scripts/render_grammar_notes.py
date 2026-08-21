#!/usr/bin/env python3
"""Render deterministic standalone grammar-note XHTML."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.grammar_notes import (  # noqa: E402
    GrammarNoteError,
    load_json,
    write_grammar_notes,
)


def _diagnostic(reason: str) -> dict:
    return {"schema_version": 1, "rendered": False, "diagnostics": [{"id": "grammar-note-diagnostic-0001", "reason": reason}]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--title", default="Grammar Study Notes")
    parser.add_argument("--test-only-allow-synthetic-mechanics", action="store_true")
    parser.add_argument("--disabled", action="store_true")
    parser.add_argument("--safe-report", type=Path)
    args = parser.parse_args()
    reason = None
    if args.disabled:
        reason = "disabled"
    elif not args.plan or not args.dataset or not args.output:
        reason = "invalid-input"
    else:
        try:
            plan = load_json(args.plan)
            dataset = load_json(args.dataset)
            write_grammar_notes(
                plan, dataset, args.output, title=args.title,
                allow_synthetic_mechanics=args.test_only_allow_synthetic_mechanics,
            )
        except (OSError, json.JSONDecodeError):
            reason = "corrupt-input"
        except (GrammarNoteError, KeyError, TypeError, ValueError) as error:
            reason = "stale-input" if "stale" in str(error).lower() else "invalid-input"
    if reason:
        if not args.safe_report:
            raise SystemExit(reason)
        args.safe_report.parent.mkdir(parents=True, exist_ok=True)
        args.safe_report.write_text(json.dumps(_diagnostic(reason), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return
    if args.safe_report:
        args.safe_report.parent.mkdir(parents=True, exist_ok=True)
        args.safe_report.write_text(json.dumps({"schema_version": 1, "rendered": True, "diagnostics": []}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
