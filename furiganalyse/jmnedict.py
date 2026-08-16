"""Local, deterministic JMnedict ingestion and proper-name lookup."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol
from xml.etree import ElementTree as ET

from furiganalyse.jmdict import normalize_reading

INDEX_FORMAT_VERSION = 1
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


class JmnedictError(ValueError):
    """Raised when JMnedict input or an index cannot be trusted."""


@dataclass(frozen=True)
class JmnedictProvenance:
    dataset_id: str
    dataset_version: str
    format_version: int
    sha256: str


@dataclass(frozen=True)
class JmnedictReading:
    text: str
    written_restrictions: list[str]


@dataclass(frozen=True)
class JmnedictTranslation:
    id: str
    index: int
    name_types: list[str]
    translations: list[str]


@dataclass(frozen=True)
class JmnedictEntry:
    sequence: int
    written_forms: list[str]
    readings: list[JmnedictReading]
    translations: list[JmnedictTranslation]


@dataclass(frozen=True)
class JmnedictQuery:
    surface: str
    reading: str | None
    part_of_speech: str | None
    publisher_reading: bool = False


@dataclass(frozen=True)
class JmnedictEntryMatch:
    entry_id: str
    sequence: int
    matched_form: str
    matched_by: str
    written_forms: list[str]
    readings: list[JmnedictReading]
    translations: list[JmnedictTranslation]


class JmnedictProvider(Protocol):
    @property
    def provenance(self) -> JmnedictProvenance: ...

    def lookup(self, query: JmnedictQuery) -> list[JmnedictEntryMatch]: ...


def _texts(element: ET.Element, name: str) -> list[str]:
    return [
        child.text.strip()
        for child in element.findall(name)
        if child.text and child.text.strip()
    ]


def parse_jmnedict(
    xml_path: str | Path,
    dataset_id: str | None = None,
    dataset_version: str | None = None,
) -> tuple[JmnedictProvenance, list[JmnedictEntry]]:
    path = Path(xml_path)
    raw = path.read_bytes()
    root = ET.fromstring(raw)
    if root.tag != "JMnedict":
        raise JmnedictError("Expected a JMnedict root element")
    dataset_id = dataset_id or root.attrib.get("dataset-id")
    dataset_version = dataset_version or root.attrib.get("version")
    if not dataset_id or not dataset_version:
        raise JmnedictError("JMnedict fixture requires dataset-id and version metadata")

    entries = []
    seen_sequences = set()
    for entry_element in root.findall("entry"):
        sequence_text = entry_element.findtext("ent_seq")
        if not sequence_text or not sequence_text.isdigit():
            raise JmnedictError("JMnedict entry has no numeric ent_seq")
        sequence = int(sequence_text)
        if sequence in seen_sequences:
            raise JmnedictError(f"Duplicate JMnedict entry sequence: {sequence}")
        seen_sequences.add(sequence)
        written_forms = [
            value
            for element in entry_element.findall("k_ele")
            for value in _texts(element, "keb")
        ]
        readings = []
        for element in entry_element.findall("r_ele"):
            reading = element.findtext("reb")
            if not reading or not reading.strip():
                raise JmnedictError(f"JMnedict entry {sequence} has an empty reading")
            readings.append(
                JmnedictReading(
                    text=reading.strip(),
                    written_restrictions=_texts(element, "re_restr"),
                )
            )
        translations = []
        for index, element in enumerate(entry_element.findall("trans"), start=1):
            translations.append(
                JmnedictTranslation(
                    id=f"jmnedict-{sequence}-translation-{index:04d}",
                    index=index,
                    name_types=_texts(element, "name_type"),
                    translations=[
                        value.text.strip()
                        for value in element.findall("trans_det")
                        if value.text
                        and value.text.strip()
                        and value.attrib.get(XML_LANG, "eng") == "eng"
                    ],
                )
            )
        if not readings or not translations:
            raise JmnedictError(
                f"JMnedict entry {sequence} lacks readings or translations"
            )
        if any(not value.translations for value in translations):
            raise JmnedictError(
                f"JMnedict entry {sequence} lacks English translations"
            )
        entries.append(
            JmnedictEntry(
                sequence=sequence,
                written_forms=written_forms,
                readings=readings,
                translations=translations,
            )
        )
    entries.sort(key=lambda entry: entry.sequence)
    return (
        JmnedictProvenance(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            format_version=INDEX_FORMAT_VERSION,
            sha256=hashlib.sha256(raw).hexdigest(),
        ),
        entries,
    )


def build_jmnedict_index(
    xml_path: str | Path,
    index_path: str | Path,
    dataset_id: str | None = None,
    dataset_version: str | None = None,
):
    provenance, entries = parse_jmnedict(
        xml_path, dataset_id=dataset_id, dataset_version=dataset_version
    )
    output = Path(index_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise JmnedictError(f"Refusing to overwrite existing index: {output}")
    connection = sqlite3.connect(output)
    try:
        connection.executescript(
            """
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE entries (
                sequence INTEGER PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE forms (
                form TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                kind TEXT NOT NULL,
                form_order INTEGER NOT NULL,
                PRIMARY KEY (form, sequence, kind, form_order)
            );
            CREATE INDEX forms_lookup ON forms(form, sequence, kind, form_order);
            """
        )
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            sorted((key, str(value)) for key, value in asdict(provenance).items()),
        )
        for entry in entries:
            connection.execute(
                "INSERT INTO entries(sequence, payload) VALUES (?, ?)",
                (
                    entry.sequence,
                    json.dumps(asdict(entry), ensure_ascii=False, sort_keys=True),
                ),
            )
            for order, form in enumerate(entry.written_forms):
                connection.execute(
                    "INSERT INTO forms VALUES (?, ?, 'written', ?)",
                    (form, entry.sequence, order),
                )
            for order, reading in enumerate(entry.readings):
                connection.execute(
                    "INSERT INTO forms VALUES (?, ?, 'reading', ?)",
                    (reading.text, entry.sequence, order),
                )
        connection.commit()
    finally:
        connection.close()


def _entry_from_payload(payload: str) -> JmnedictEntry:
    value = json.loads(payload)
    return JmnedictEntry(
        sequence=value["sequence"],
        written_forms=value["written_forms"],
        readings=[JmnedictReading(**reading) for reading in value["readings"]],
        translations=[
            JmnedictTranslation(**translation)
            for translation in value["translations"]
        ],
    )


class SqliteJmnedictProvider:
    def __init__(self, index_path: str | Path):
        self.index_path = Path(index_path)
        self.connection = sqlite3.connect(
            f"file:{self.index_path}?mode=ro", uri=True
        )
        metadata = dict(self.connection.execute("SELECT key, value FROM metadata"))
        if int(metadata.get("format_version", -1)) != INDEX_FORMAT_VERSION:
            raise JmnedictError("Unsupported JMnedict index format")
        self._provenance = JmnedictProvenance(
            dataset_id=metadata["dataset_id"],
            dataset_version=metadata["dataset_version"],
            format_version=int(metadata["format_version"]),
            sha256=metadata["sha256"],
        )

    @property
    def provenance(self) -> JmnedictProvenance:
        return self._provenance

    def close(self):
        self.connection.close()

    def lookup(self, query: JmnedictQuery) -> list[JmnedictEntryMatch]:
        if (
            query.part_of_speech
            and not query.part_of_speech.startswith("名詞,固有名詞")
            and not query.publisher_reading
        ):
            return []
        normalized_reading = normalize_reading(query.reading)
        sequences = {}
        for sequence, kind in self.connection.execute(
            "SELECT sequence, kind FROM forms WHERE form = ? "
            "ORDER BY sequence, kind, form_order",
            (query.surface,),
        ):
            sequences.setdefault(sequence, ("surface", query.surface, kind))
        if not sequences and normalized_reading:
            for sequence, kind in self.connection.execute(
                "SELECT sequence, kind FROM forms WHERE form = ? "
                "ORDER BY sequence, kind, form_order",
                (normalized_reading,),
            ):
                sequences.setdefault(
                    sequence, ("reading", normalized_reading, kind)
                )

        matches = []
        for sequence in sorted(sequences):
            matched_by, matched_form, kind = sequences[sequence]
            payload = self.connection.execute(
                "SELECT payload FROM entries WHERE sequence = ?", (sequence,)
            ).fetchone()[0]
            entry = _entry_from_payload(payload)
            written_form = matched_form if kind == "written" else None
            readings = [
                reading
                for reading in entry.readings
                if (
                    written_form is None
                    or not reading.written_restrictions
                    or written_form in reading.written_restrictions
                )
                and (
                    normalized_reading is None
                    or normalize_reading(reading.text) == normalized_reading
                )
            ]
            if not readings:
                continue
            matches.append(
                JmnedictEntryMatch(
                    entry_id=f"jmnedict-{entry.sequence}",
                    sequence=entry.sequence,
                    matched_form=matched_form,
                    matched_by=matched_by,
                    written_forms=entry.written_forms,
                    readings=readings,
                    translations=entry.translations,
                )
            )
        return matches
