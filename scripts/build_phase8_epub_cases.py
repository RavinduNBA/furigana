#!/usr/bin/env python3
"""Build deterministic safe-failure inputs for Phase 8 adaptive EPUB packaging."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path

from furiganalyse.adaptive_rendering import directory_hash
from furiganalyse.assistance_density import stable_hash


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def rehash(value: dict) -> None:
    value.pop("hash", None)
    value["hash"] = stable_hash(value)


def files(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*.xhtml"))
    }


def synchronize(report: dict, metadata: dict, directory: Path) -> None:
    current = files(directory)
    for document in report["document_results"]:
        document["output_sha256"] = hashlib.sha256(current[document["path"]]).hexdigest()
        rehash(document)
    rehash(report)
    metadata["adaptive_rendering_report_hash"] = report["hash"]
    metadata["adaptive_xhtml_directory_hash"] = directory_hash(current)
    rehash(metadata)


def copy_source(source: Path, output: Path, name: str) -> Path:
    target = output / name / "xhtml"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rendering-report", required=True, type=Path)
    parser.add_argument("--adaptive-dir", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    baseline_report = load(args.rendering_report)
    baseline_metadata = load(args.metadata)

    stale = copy.deepcopy(baseline_metadata)
    stale["base_epub_sha256"] = "0" * 64
    rehash(stale)
    write(args.output_dir / "stale" / "metadata.json", stale)

    rendering_mismatch = copy.deepcopy(baseline_report)
    rendering_mismatch["configuration"]["enabled"] = False
    rehash(rendering_mismatch["configuration"])
    rehash(rendering_mismatch)
    write(
        args.output_dir / "rendering-mismatch" / "rendering-report.json",
        rendering_mismatch,
    )

    invalid = copy.deepcopy(baseline_metadata)
    invalid["schema_version"] = 2
    rehash(invalid)
    write(args.output_dir / "invalid" / "metadata.json", invalid)
    (args.output_dir / "corrupt").mkdir(parents=True, exist_ok=True)
    (args.output_dir / "corrupt" / "rendering-report.json").write_text(
        "{not-json\n", encoding="utf-8",
    )

    mismatched = copy_source(args.adaptive_dir, args.output_dir, "mismatched")
    target = mismatched / "EPUB/text/grammar-02.xhtml"
    target.write_bytes(target.read_bytes() + b"\n")

    unsafe = copy_source(args.adaptive_dir, args.output_dir, "unsafe")
    (unsafe / "unsafe\\member.xhtml").write_text("unsafe\n", encoding="utf-8")

    duplicate = copy.deepcopy(baseline_report)
    duplicate["document_results"][1]["path"] = duplicate["document_results"][0]["path"]
    rehash(duplicate["document_results"][1])
    rehash(duplicate)
    duplicate_metadata = copy.deepcopy(baseline_metadata)
    duplicate_metadata["adaptive_rendering_report_hash"] = duplicate["hash"]
    rehash(duplicate_metadata)
    write(args.output_dir / "duplicate-path" / "rendering-report.json", duplicate)
    write(args.output_dir / "duplicate-path" / "metadata.json", duplicate_metadata)

    mutations = {
        "broken-fragment": (
            "grammar-notes.xhtml#grammar-note-0002",
            "grammar-notes.xhtml#missing-note",
        ),
        "hidden-content": (
            "</body>",
            '<span style="display:none">hidden</span></body>',
        ),
        "publisher-conflict": ("おもてぶたい", "おもて"),
        "grammar-conflict": ('class="grammar-link"', 'class="grammar-link-removed"'),
    }
    for name, (old, new) in mutations.items():
        directory = copy_source(args.adaptive_dir, args.output_dir, name)
        chapter = directory / "EPUB/text/grammar-01.xhtml"
        chapter.write_text(
            chapter.read_text(encoding="utf-8").replace(old, new, 1),
            encoding="utf-8",
        )
        report = copy.deepcopy(baseline_report)
        metadata = copy.deepcopy(baseline_metadata)
        synchronize(report, metadata, directory)
        write(args.output_dir / name / "rendering-report.json", report)
        write(args.output_dir / name / "metadata.json", metadata)


if __name__ == "__main__":
    main()
