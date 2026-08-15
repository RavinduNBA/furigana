#!/usr/bin/env python3
"""Build, convert, validate, and retain the Phase 0 EPUB artifacts."""

from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.__main__ import main
from furiganalyse.params import FuriganaMode, OutputFormat
from tests.phase0_epub import build_fixture, validate_epub


def check(path):
    errors = validate_epub(path)
    if errors:
        raise SystemExit("\n".join(f"{path}: {error}" for error in errors))


def unpack(path, destination):
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    with zipfile.ZipFile(path) as archive:
        archive.extractall(destination)


def run():
    artifacts = ROOT / "artifacts" / "phase0"
    source = artifacts / "fixture.epub"
    output = artifacts / "fixture-converted.epub"
    build_fixture(source)
    check(source)
    main(str(source), str(output), FuriganaMode.add, OutputFormat.epub)
    check(output)
    unpack(source, artifacts / "fixture-unpacked")
    unpack(output, artifacts / "fixture-converted-unpacked")
    print(f"Phase 0 regression passed. Artifacts: {artifacts}")


if __name__ == "__main__":
    run()
