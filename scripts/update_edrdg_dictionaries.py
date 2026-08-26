#!/usr/bin/env python3
"""Explicitly download, verify, and index official EDRDG dictionary releases."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from furiganalyse.jmdict import build_jmdict_index  # noqa: E402
from furiganalyse.jmnedict import build_jmnedict_index  # noqa: E402


SOURCES = {
    "jmdict": "https://www.edrdg.org/pub/Nihongo/JMdict_e.gz",
    "jmnedict": "https://www.edrdg.org/pub/Nihongo/JMnedict.xml.gz",
}
DATE_PATTERN = re.compile(rb"(?:JMdict|JMnedict) created: (\d{4}-\d{2}-\d{2})")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Furiganalyse dictionary updater"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as target:
        if response.geturl() != url:
            raise RuntimeError("Unexpected dictionary download redirect")
        shutil.copyfileobj(response, target)


def extract(source: Path, destination: Path) -> None:
    with gzip.open(source, "rb") as compressed, destination.open("wb") as target:
        shutil.copyfileobj(compressed, target)


def release_date(path: Path) -> str:
    with path.open("rb") as source:
        header = source.read(128 * 1024)
    match = DATE_PATTERN.search(header)
    if not match:
        raise RuntimeError("Official dictionary release date was not found")
    return match.group(1).decode("ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/edrdg"))
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Atomically replace existing local release files and indexes",
    )
    args = parser.parse_args()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    targets = {
        "jmdict": (output / "JMdict_e.gz", output / "JMdict_e", output / "JMdict.sqlite"),
        "jmnedict": (output / "JMnedict.xml.gz", output / "JMnedict.xml", output / "JMnedict.sqlite"),
    }
    if not args.replace and any(path.exists() for values in targets.values() for path in values):
        parser.error("local EDRDG files already exist; use --replace for an explicit update")

    staged = output / ".update"
    if staged.exists():
        shutil.rmtree(staged)
    staged.mkdir()
    records = []
    try:
        versions = {}
        for source_id, url in SOURCES.items():
            archive = staged / targets[source_id][0].name
            xml = staged / targets[source_id][1].name
            download(url, archive)
            extract(archive, xml)
            version = release_date(xml)
            versions[source_id] = version
            records.append({
                "id": source_id,
                "project_url": "https://www.edrdg.org/",
                "download_url": url,
                "release_date": version,
                "compressed_sha256": sha256(archive),
                "xml_sha256": sha256(xml),
            })
        build_jmdict_index(
            staged / "JMdict_e",
            staged / "JMdict.sqlite",
            dataset_id="edrdg-jmdict-e",
            dataset_version=versions["jmdict"],
        )
        build_jmnedict_index(
            staged / "JMnedict.xml",
            staged / "JMnedict.sqlite",
            dataset_id="edrdg-jmnedict",
            dataset_version=versions["jmnedict"],
        )
        for record in records:
            record["index_sha256"] = sha256(
                staged / (
                    "JMdict.sqlite" if record["id"] == "jmdict"
                    else "JMnedict.sqlite"
                )
            )
        manifest = {
            "schema_version": 1,
            "license": "Creative Commons Attribution-ShareAlike 4.0 International",
            "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
            "edrdg_license_url": "https://www.edrdg.org/edrdg/licence.html",
            "runtime_network_lookup": False,
            "sources": records,
        }
        (staged / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        for path in staged.iterdir():
            os.replace(path, output / path.name)
    finally:
        if staged.exists():
            shutil.rmtree(staged)


if __name__ == "__main__":
    main()
