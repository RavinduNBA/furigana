#!/usr/bin/env python3
"""Build a local deterministic JMdict SQLite lookup index."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.jmdict import build_jmdict_index  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jmdict_xml", type=Path)
    parser.add_argument("output_index", type=Path)
    parser.add_argument("--dataset-id", help="Pinned local dataset identity")
    parser.add_argument("--dataset-version", help="Pinned dataset release/version")
    args = parser.parse_args()
    build_jmdict_index(
        args.jmdict_xml,
        args.output_index,
        dataset_id=args.dataset_id,
        dataset_version=args.dataset_version,
    )
    print(f"Wrote JMdict index to {args.output_index}")


if __name__ == "__main__":
    main()
