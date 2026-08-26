"""Local, deterministic JMnedict ingestion and proper-name lookup."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Protocol
from xml.etree import ElementTree as ET

from furiganalyse.jmdict import normalize_reading, readings_match

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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entry_from_xml(
    entry_element: ET.Element, seen_sequences: set[int]
) -> JmnedictEntry:
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
        raise JmnedictError(f"JMnedict entry {sequence} lacks readings or translations")
    if any(not value.translations for value in translations):
        raise JmnedictError(f"JMnedict entry {sequence} lacks English translations")
    return JmnedictEntry(
        sequence=sequence,
        written_forms=written_forms,
        readings=readings,
        translations=translations,
    )


def iter_jmnedict_entries(xml_path: str | Path) -> Iterator[JmnedictEntry]:
    """Stream validated entries without retaining the full XML tree."""
    path = Path(xml_path)
    seen_sequences: set[int] = set()
    root_checked = False
    try:
        for event, element in ET.iterparse(path, events=("start", "end")):
            if event == "start" and not root_checked:
                if element.tag != "JMnedict":
                    raise JmnedictError("Expected a JMnedict root element")
                root_checked = True
            elif event == "end" and element.tag == "entry":
                yield _entry_from_xml(element, seen_sequences)
                element.clear()
    except ET.ParseError as error:
        raise JmnedictError("Invalid JMnedict XML") from error
    if not root_checked:
        raise JmnedictError("Expected a JMnedict root element")


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

    seen_sequences: set[int] = set()
    entries = [_entry_from_xml(element, seen_sequences) for element in root.findall("entry")]
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
    path = Path(xml_path)
    if not dataset_id or not dataset_version:
        provenance, entries = parse_jmnedict(
            path, dataset_id=dataset_id, dataset_version=dataset_version
        )
    else:
        provenance = JmnedictProvenance(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            format_version=INDEX_FORMAT_VERSION,
            sha256=_file_sha256(path),
        )
        entries = iter_jmnedict_entries(path)
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
    def __init__(
        self,
        index_path: str | Path,
        *,
        max_matches: int | None = None,
        max_translations_per_match: int | None = None,
    ):
        if max_matches is not None and max_matches < 1:
            raise JmnedictError("max_matches must be positive")
        if max_translations_per_match is not None and max_translations_per_match < 1:
            raise JmnedictError("max_translations_per_match must be positive")
        self.index_path = Path(index_path)
        self.max_matches = max_matches
        self.max_translations_per_match = max_translations_per_match
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
        self._lookup_cache: dict[JmnedictQuery, tuple[JmnedictEntryMatch, ...]] = {}

    @property
    def provenance(self) -> JmnedictProvenance:
        return self._provenance

    def close(self):
        self.connection.close()

    def lookup(self, query: JmnedictQuery) -> list[JmnedictEntryMatch]:
        cached = self._lookup_cache.get(query)
        if cached is not None:
            return list(cached)
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
                    or readings_match(reading.text, normalized_reading)
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
                    translations=(
                        entry.translations[: self.max_translations_per_match]
                        if self.max_translations_per_match is not None
                        else entry.translations
                    ),
                )
            )
            if self.max_matches is not None and len(matches) >= self.max_matches:
                break
        self._lookup_cache[query] = tuple(matches)
        return list(matches)
