"""Local, deterministic JMdict ingestion and single-token lookup."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Protocol
from xml.etree import ElementTree as ET

INDEX_FORMAT_VERSION = 1


class JmdictError(ValueError):
    """Raised when JMdict input or an index cannot be trusted."""


@dataclass(frozen=True)
class JmdictProvenance:
    dataset_id: str
    dataset_version: str
    format_version: int
    sha256: str


@dataclass(frozen=True)
class JmdictReading:
    text: str
    written_restrictions: list[str]
    no_kanji: bool


@dataclass(frozen=True)
class JmdictSense:
    id: str
    index: int
    parts_of_speech: list[str]
    written_restrictions: list[str]
    reading_restrictions: list[str]
    glosses: list[str]


@dataclass(frozen=True)
class JmdictEntry:
    sequence: int
    written_forms: list[str]
    readings: list[JmdictReading]
    senses: list[JmdictSense]


@dataclass(frozen=True)
class JmdictQuery:
    surface: str
    lemma: str
    reading: str | None
    part_of_speech: str | None
    publisher_reading: bool = False


@dataclass(frozen=True)
class JmdictEntryMatch:
    entry_id: str
    sequence: int
    matched_form: str
    matched_by: str
    written_forms: list[str]
    readings: list[JmdictReading]
    senses: list[JmdictSense]


class JmdictProvider(Protocol):
    @property
    def provenance(self) -> JmdictProvenance: ...

    def lookup(self, query: JmdictQuery) -> list[JmdictEntryMatch]: ...


def normalize_reading(value: str | None) -> str | None:
    if value is None:
        return None
    return "".join(
        chr(ord(character) - 0x60)
        if "ァ" <= character <= "ヶ"
        else character
        for character in value
    )


def kana_fold(value: str | None) -> str | None:
    """Normalize hiragana/katakana and fold small kana (e.g. ょ -> よ, ゃ -> や, っ -> つ)."""
    if value is None:
        return None
    hiragana = normalize_reading(value)
    if hiragana is None:
        return None
    small_to_large = {
        "ぁ": "あ", "ぃ": "い", "ぅ": "う", "ぇ": "え", "ぉ": "お",
        "っ": "つ", "ゃ": "や", "ゅ": "ゆ", "ょ": "よ", "ゎ": "わ",
    }
    return "".join(small_to_large.get(ch, ch) for ch in hiragana)


def readings_match(a: str | None, b: str | None) -> bool:
    """Check if two readings match exactly or under unreduced kana folding."""
    if a is None or b is None:
        return a == b
    if normalize_reading(a) == normalize_reading(b):
        return True
    return kana_fold(a) == kana_fold(b)


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


def _entity_code_map_from_bytes(raw: bytes) -> dict[str, str]:
    return {
        description.decode("utf-8"): code.decode("ascii")
        for code, description in re.findall(
            rb'<!ENTITY\s+([A-Za-z0-9_-]+)\s+"([^"]+)"\s*>', raw
        )
    }


def _entity_code_map(path: Path) -> dict[str, str]:
    header = bytearray()
    with path.open("rb") as source:
        for line in source:
            header.extend(line)
            if b"]>" in line:
                break
    return _entity_code_map_from_bytes(bytes(header))


def _entry_from_xml(
    entry_element: ET.Element,
    seen_sequences: set[int],
    entity_codes: dict[str, str] | None = None,
) -> JmdictEntry:
    sequence_text = entry_element.findtext("ent_seq")
    if not sequence_text or not sequence_text.isdigit():
        raise JmdictError("JMdict entry has no numeric ent_seq")
    sequence = int(sequence_text)
    if sequence in seen_sequences:
        raise JmdictError(f"Duplicate JMdict entry sequence: {sequence}")
    seen_sequences.add(sequence)

    written_forms = [
        keb
        for k_ele in entry_element.findall("k_ele")
        for keb in _texts(k_ele, "keb")
    ]
    readings = []
    for r_ele in entry_element.findall("r_ele"):
        reb = r_ele.findtext("reb")
        if not reb or not reb.strip():
            raise JmdictError(f"JMdict entry {sequence} has an empty reading")
        readings.append(
            JmdictReading(
                text=reb.strip(),
                written_restrictions=_texts(r_ele, "re_restr"),
                no_kanji=r_ele.find("re_nokanji") is not None,
            )
        )

    senses = []
    for index, sense in enumerate(entry_element.findall("sense"), start=1):
        senses.append(
            JmdictSense(
                id=f"jmdict-{sequence}-sense-{index:04d}",
                index=index,
                parts_of_speech=[
                    (entity_codes or {}).get(value, value)
                    for value in _texts(sense, "pos")
                ],
                written_restrictions=_texts(sense, "stagk"),
                reading_restrictions=_texts(sense, "stagr"),
                glosses=[
                    gloss.text.strip()
                    for gloss in sense.findall("gloss")
                    if gloss.text
                    and gloss.text.strip()
                    and gloss.attrib.get(
                        "{http://www.w3.org/XML/1998/namespace}lang", "eng"
                    ) == "eng"
                ],
            )
        )
    if not readings or not senses:
        raise JmdictError(f"JMdict entry {sequence} lacks readings or senses")
    return JmdictEntry(
        sequence=sequence,
        written_forms=written_forms,
        readings=readings,
        senses=senses,
    )


def iter_jmdict_entries(xml_path: str | Path) -> Iterator[JmdictEntry]:
    """Stream validated entries without retaining the full XML tree."""
    path = Path(xml_path)
    seen_sequences: set[int] = set()
    entity_codes = _entity_code_map(path)
    root_checked = False
    try:
        for event, element in ET.iterparse(path, events=("start", "end")):
            if event == "start" and not root_checked:
                if element.tag != "JMdict":
                    raise JmdictError("Expected a JMdict root element")
                root_checked = True
            elif event == "end" and element.tag == "entry":
                yield _entry_from_xml(element, seen_sequences, entity_codes)
                element.clear()
    except ET.ParseError as error:
        raise JmdictError("Invalid JMdict XML") from error
    if not root_checked:
        raise JmdictError("Expected a JMdict root element")


def parse_jmdict(
    xml_path: str | Path,
    dataset_id: str | None = None,
    dataset_version: str | None = None,
) -> tuple[JmdictProvenance, list[JmdictEntry]]:
    path = Path(xml_path)
    raw = path.read_bytes()
    root = ET.fromstring(raw)
    if root.tag != "JMdict":
        raise JmdictError("Expected a JMdict root element")
    dataset_id = dataset_id or root.attrib.get("dataset-id")
    dataset_version = dataset_version or root.attrib.get("version")
    if not dataset_id or not dataset_version:
        raise JmdictError("JMdict fixture requires dataset-id and version metadata")

    seen_sequences: set[int] = set()
    entity_codes = _entity_code_map_from_bytes(raw)
    entries = [
        _entry_from_xml(element, seen_sequences, entity_codes)
        for element in root.findall("entry")
    ]

    entries.sort(key=lambda entry: entry.sequence)
    return (
        JmdictProvenance(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            format_version=INDEX_FORMAT_VERSION,
            sha256=hashlib.sha256(raw).hexdigest(),
        ),
        entries,
    )


def build_jmdict_index(
    xml_path: str | Path,
    index_path: str | Path,
    dataset_id: str | None = None,
    dataset_version: str | None = None,
):
    path = Path(xml_path)
    if not dataset_id or not dataset_version:
        # Fixture metadata remains supported by the in-memory parser. Production
        # release builds supply explicit, pinned provenance at the boundary.
        provenance, entries = parse_jmdict(path, dataset_id, dataset_version)
    else:
        provenance = JmdictProvenance(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            format_version=INDEX_FORMAT_VERSION,
            sha256=_file_sha256(path),
        )
        entries = iter_jmdict_entries(path)
    output = Path(index_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise JmdictError(f"Refusing to overwrite existing index: {output}")
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


def _entry_from_payload(payload: str) -> JmdictEntry:
    value = json.loads(payload)
    return JmdictEntry(
        sequence=value["sequence"],
        written_forms=value["written_forms"],
        readings=[JmdictReading(**reading) for reading in value["readings"]],
        senses=[JmdictSense(**sense) for sense in value["senses"]],
    )


def pos_compatible(candidate_pos: str | None, sense_pos: list[str]) -> bool:
    if not candidate_pos or not sense_pos:
        return True
    category, _, detail = candidate_pos.partition(",")
    if category == "名詞" and detail.startswith("接尾"):
        return any(pos.startswith(("suf", "n-suf")) for pos in sense_pos)
    if category == "名詞" and detail.startswith("接頭"):
        return any(pos.startswith(("pref", "n-pref")) for pos in sense_pos)
    prefixes = {
        "動詞": ("v",),
        "名詞": ("n",),
        "形容詞": ("adj",),
        "副詞": ("adv",),
        "助詞": ("prt",),
        "助動詞": ("aux",),
        "接続詞": ("conj",),
        "感動詞": ("int",),
        "接頭詞": ("pref",),
        "連体詞": ("adj-pn",),
    }.get(category)
    return False if prefixes is None else any(
        pos.startswith(prefixes) for pos in sense_pos
    )


def _valid_readings(
    entry: JmdictEntry, written_form: str | None, query_reading: str | None
) -> list[JmdictReading]:
    readings = [
        reading
        for reading in entry.readings
        if written_form is None
        or not reading.written_restrictions
        or written_form in reading.written_restrictions
    ]
    if query_reading:
        norm_q = normalize_reading(query_reading)
        exact = [
            reading
            for reading in readings
            if normalize_reading(reading.text) == norm_q
        ]
        if exact:
            return exact
        folded_q = kana_fold(query_reading)
        folded = [
            reading
            for reading in readings
            if kana_fold(reading.text) == folded_q
        ]
        if folded:
            return folded
        return []
    return readings


class SqliteJmdictProvider:
    def __init__(
        self,
        index_path: str | Path,
        *,
        max_matches: int | None = None,
        max_senses_per_match: int | None = None,
    ):
        if max_matches is not None and max_matches < 1:
            raise JmdictError("max_matches must be positive")
        if max_senses_per_match is not None and max_senses_per_match < 1:
            raise JmdictError("max_senses_per_match must be positive")
        self.index_path = Path(index_path)
        self.max_matches = max_matches
        self.max_senses_per_match = max_senses_per_match
        self.connection = sqlite3.connect(f"file:{self.index_path}?mode=ro", uri=True)
        metadata = dict(self.connection.execute("SELECT key, value FROM metadata"))
        if int(metadata.get("format_version", -1)) != INDEX_FORMAT_VERSION:
            raise JmdictError("Unsupported JMdict index format")
        self._provenance = JmdictProvenance(
            dataset_id=metadata["dataset_id"],
            dataset_version=metadata["dataset_version"],
            format_version=int(metadata["format_version"]),
            sha256=metadata["sha256"],
        )
        self._lookup_cache: dict[JmdictQuery, tuple[JmdictEntryMatch, ...]] = {}

    @property
    def provenance(self) -> JmdictProvenance:
        return self._provenance

    def close(self):
        self.connection.close()

    def lookup(self, query: JmdictQuery) -> list[JmdictEntryMatch]:
        cached = self._lookup_cache.get(query)
        if cached is not None:
            return list(cached)
        forms = []
        for matched_by, form in (("lemma", query.lemma), ("surface", query.surface)):
            if form and form not in [existing[1] for existing in forms]:
                forms.append((matched_by, form))
        normalized_reading = normalize_reading(query.reading)
        sequences = {}
        for matched_by, form in forms:
            for sequence, kind in self.connection.execute(
                "SELECT sequence, kind FROM forms WHERE form = ? "
                "ORDER BY sequence, kind, form_order",
                (form,),
            ):
                if kind == "reading":
                    if (
                        not normalized_reading
                        or (
                            normalize_reading(form) != normalized_reading
                            and kana_fold(form) != kana_fold(normalized_reading)
                        )
                    ):
                        continue
                    sequences.setdefault(
                        sequence,
                        ("reading", normalized_reading, kind),
                    )
                else:
                    sequences.setdefault(sequence, (matched_by, form, kind))
        if not sequences and normalized_reading:
            for sequence, kind in self.connection.execute(
                "SELECT sequence, kind FROM forms WHERE form = ? ORDER BY sequence",
                (normalized_reading,),
            ):
                sequences.setdefault(sequence, ("reading", normalized_reading, kind))

        matches = []
        for sequence in sorted(sequences):
            matched_by, matched_form, kind = sequences[sequence]
            payload = self.connection.execute(
                "SELECT payload FROM entries WHERE sequence = ?", (sequence,)
            ).fetchone()[0]
            entry = _entry_from_payload(payload)
            written_form = matched_form if kind == "written" else None
            strict_reading = (
                normalized_reading
                if query.publisher_reading or query.surface == query.lemma
                else None
            )
            readings = _valid_readings(entry, written_form, strict_reading)
            if strict_reading and not readings:
                continue
            senses = [
                sense
                for sense in entry.senses
                if (not sense.written_restrictions or written_form in sense.written_restrictions)
                and (
                    not sense.reading_restrictions
                    or any(
                        reading.text in sense.reading_restrictions
                        for reading in readings
                    )
                )
                and pos_compatible(query.part_of_speech, sense.parts_of_speech)
            ]
            if not senses:
                continue
            if self.max_senses_per_match is not None:
                senses = senses[: self.max_senses_per_match]
            matches.append(
                JmdictEntryMatch(
                    entry_id=f"jmdict-{entry.sequence}",
                    sequence=entry.sequence,
                    matched_form=matched_form,
                    matched_by=matched_by,
                    written_forms=entry.written_forms,
                    readings=readings,
                    senses=senses,
                )
            )
            if self.max_matches is not None and len(matches) >= self.max_matches:
                break
        self._lookup_cache[query] = tuple(matches)
        return list(matches)
