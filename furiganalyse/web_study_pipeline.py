"""Dictionary-only web orchestration over validated Phase 2–8 boundaries."""

from __future__ import annotations

import hashlib
import gc
import json
import os
import zipfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from xml.etree import ElementTree as ET

from furiganalyse.adaptive_rendering import render_adaptive_output, write_output
from furiganalyse.assistance_density import (
    add_hash as add_density_hash,
    build_density_report,
)
from furiganalyse.book_analysis import extract_book
from furiganalyse.enriched_plan import promote_dictionary_only_plan
from furiganalyse.epub_packaging import package_study_epub, write_deterministic_epub
from furiganalyse.jmdict import SqliteJmdictProvider
from furiganalyse.jmnedict import SqliteJmnedictProvider
from furiganalyse.guided_reading import (
    build_guided_reading_plan,
    render_guided_reading,
)
from furiganalyse.learner_profile import (
    add_hash,
    build_assistance_report,
    stable_hash,
)
from furiganalyse.linked_output import (
    LinkedOutput,
    create_linked_output,
    split_study_notes_by_source_document,
    write_linked_output,
)
from furiganalyse.study_plan import StudyPlanConfig, create_annotation_plan
from furiganalyse.vocabulary_analysis import (
    analyze_vocabulary,
    enrich_name_report,
    enrich_vocabulary_report,
    validate_name_report,
)


ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class WebStudyOptions:
    # Zero means every safely selectable dictionary-backed item.
    per_chapter_item_limit: int = 50
    experimental_adaptive: bool = False
    preset_level: str = "N5"
    reading_state: str = "show-reading"
    meaning_state: str = "show-meaning"
    meaning_coverage: str = "all-selected"
    guided_reading: bool = False
    bilingual_companion: bool = False
    bilingual_provider: str = "none"
    bilingual_api_key: str | None = None
    bilingual_base_url: str | None = None
    bilingual_model: str | None = None
    # LLM enrichment options (independent of bilingual companion)
    llm_enrich_nouns: bool = False    # Module 4: proper noun furigana correction
    llm_enrich_glosses: bool = False  # Module 3: contextual study note glosses
    llm_provider: str = "none"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    # Module 2 & Series Memory options
    publisher_ruby_propagation: bool = True  # Module 2: propagate author ruby
    series_profile_id: str | None = None    # Series Profile ID to load pre-context from


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _preset(identifier, level, reading, meaning, grammar, rank, threshold):
    return add_hash({
        "id": identifier,
        "schema_version": 1,
        "level": level,
        "reading_default": reading,
        "meaning_default": meaning,
        "grammar_default": grammar,
        "frequency_thresholds": {
            "reading_rank": rank,
            "meaning_rank": rank,
            "grammar_rank": rank,
        },
        "exposure_thresholds": {
            "reading": threshold,
            "meaning": threshold,
            "grammar": threshold,
        },
        "rationale_codes": [
            f"synthetic-{level.lower()}-assistance-defaults",
            f"synthetic-{level.lower()}-exposure-threshold-{threshold}",
        ],
        "source_provenance": "local synthetic Phase 8 web preset",
    })


def build_web_preset_dataset() -> dict[str, Any]:
    return add_hash({
        "schema_version": 1,
        "dataset_id": "furiganalyse-synthetic-learner-presets",
        "dataset_version": "2026-08-21",
        "fixture_notice": (
            "Synthetic explainable defaults; not a learner diagnosis or "
            "pedagogical validation."
        ),
        "source_provenance": "local synthetic Phase 8 web fixture",
        "presets": [
            _preset("phase8-preset-n5", "N5", "show-reading", "show-meaning", "show-grammar", 100, 3),
            _preset("phase8-preset-n4", "N4", "hide-reading", "show-meaning", "show-grammar", 60, 2),
            _preset("phase8-preset-n3", "N3", "hide-reading", "hide-meaning", "hide-grammar", 30, 1),
        ],
    })


def _density_policy(
    level: str,
    reading: int,
    meaning: int,
    grammar: int,
    maximum: int,
    *,
    all_selected_meanings: bool = False,
):
    lower = level.lower()
    return add_density_hash({
        "id": f"phase8-density-{lower}",
        "schema_version": 1,
        "preset_id": f"phase8-preset-{lower}",
        "targets_per_1000": {
            "reading": reading,
            "meaning": 1_000_000 if all_selected_meanings else meaning,
            "grammar": grammar,
        },
        "minimum_per_chapter": {"reading": 1, "meaning": 1, "grammar": 1},
        "maximum_per_chapter": {
            "reading": maximum,
            "meaning": 10_000 if all_selected_meanings else maximum,
            "grammar": maximum,
        },
        "rounding_policy": "ceiling-integer",
        "source_order_tie_breaking": "canonical-source-order",
        "publisher_ruby_counting_policy": "preserve-without-generated-reading-budget",
        "explicit_override_handling": "show-forced-hide-suppressed-dimension-only",
        "repeated_occurrence_handling": "first-eligible-source-occurrence-before-later",
        "rationale_codes": [
            f"synthetic-{lower}-density-target",
            "independent-dimension-budgets",
            "canonical-source-order",
        ],
        "source_provenance": "local-synthetic-density-fixture",
    })


def build_web_density_dataset(
    *, all_selected_meanings: bool = False
) -> dict[str, Any]:
    return add_density_hash({
        "schema_version": 1,
        "dataset_id": "furiganalyse-synthetic-density-policies",
        "dataset_version": "2026-08-21",
        "fixture_notice": (
            "Synthetic deterministic density mechanics fixture; not a "
            "pedagogical recommendation."
        ),
        "source_provenance": "local-synthetic-density-fixture",
        "policies": [
            _density_policy(
                "N5", 8, 7, 6, 500,
                all_selected_meanings=all_selected_meanings,
            ),
            _density_policy(
                "N4", 4, 4, 2, 300,
                all_selected_meanings=all_selected_meanings,
            ),
            _density_policy(
                "N3", 2, 2, 1, 150,
                all_selected_meanings=all_selected_meanings,
            ),
        ],
    })


WEB_LINK_STYLE = """
a.study-link:link, a.grammar-link:link, a.study-note__backlink:link,
a.grammar-note__backlink:link { color: #075fbd !important; text-decoration: underline !important; }
a.study-link:visited, a.grammar-link:visited, a.study-note__backlink:visited,
a.grammar-note__backlink:visited { color: #6b3fa0 !important; text-decoration: underline !important; }
a.study-link:focus, a.grammar-link:focus, a.study-note__backlink:focus,
a.grammar-note__backlink:focus { outline: 2px solid #d28b00 !important; }
"""

WEB_NOTE_STYLE = """
html, body { writing-mode: horizontal-tb !important; -webkit-writing-mode: horizontal-tb !important;
  margin: 0 !important; padding: 0 !important; max-width: 100% !important; }
.study-notes, .grammar-notes { writing-mode: horizontal-tb !important;
  -webkit-writing-mode: horizontal-tb !important; direction: ltr; box-sizing: border-box;
  width: 100%; min-width: 0; max-width: 42rem; margin: 0 auto; padding: .8rem 1rem 2rem;
  overflow-wrap: anywhere; word-break: normal; text-align: start; }
.study-note, .grammar-study-note { writing-mode: horizontal-tb !important;
  -webkit-writing-mode: horizontal-tb !important; box-sizing: border-box;
  min-width: 0; max-width: 100%; overflow-wrap: anywhere; }
.study-note__context, .grammar-study-note__context { box-sizing: border-box;
  max-width: 100%; margin: .5em 0; padding: .5em .75em; overflow-wrap: anywhere; }
.study-note__details, .grammar-study-note__details { max-width: 100%; }
.study-note__details dd, .grammar-study-note__details dd { margin-left: 1em; }
.study-note__heading, .grammar-study-note__heading,
.study-note__backlink, .grammar-study-note__backlink { overflow-wrap: anywhere; }
"""


def _prepare_web_linked_files(files: dict[str, bytes]) -> dict[str, bytes]:
    """Add scoped reader-facing affordances without changing publisher CSS."""
    namespace = "http://www.w3.org/1999/xhtml"
    xhtml = f"{{{namespace}}}"
    ET.register_namespace("", namespace)
    prepared: dict[str, bytes] = {}
    for path, payload in sorted(files.items()):
        root = ET.fromstring(payload)
        head = root.find(xhtml + "head")
        if head is None:
            raise ValueError("Linked XHTML lacks head")
        style = ET.SubElement(head, xhtml + "style", {
            "id": "furiganalyse-web-link-style",
            "type": "text/css",
        })
        style.text = WEB_LINK_STYLE
        if path.endswith(("/study-notes.xhtml", "/grammar-notes.xhtml")):
            root.set("lang", "ja")
            root.set("{http://www.w3.org/XML/1998/namespace}lang", "ja")
            note_style = ET.SubElement(head, xhtml + "style", {
                "id": "furiganalyse-web-note-style",
                "type": "text/css",
            })
            note_style.text = WEB_NOTE_STYLE
        if path.endswith("/study-notes.xhtml"):
            body = root.find(xhtml + "body")
            if body is None:
                raise ValueError("Study notes lack body")
            container = body.find(xhtml + "main")
            if container is None:
                container = body
            notice = ET.Element(xhtml + "p", {
                "class": "study-note__scope-notice",
            })
            notice.text = (
                "Dictionary glosses for selected items; this is not sentence translation."
            )
            container.insert(1 if len(container) else 0, notice)
        prepared[path] = ET.tostring(
            root, encoding="utf-8", xml_declaration=True, short_empty_elements=True
        )
    return prepared


def build_web_profile(
    vocabulary: dict[str, Any],
    annotation_plan: dict[str, Any],
    presets: dict[str, Any],
    options: WebStudyOptions,
) -> dict[str, Any]:
    level = options.preset_level.upper()
    if level not in {"N5", "N4", "N3"}:
        raise ValueError("Unsupported experimental preset")
    if options.reading_state not in {"show-reading", "hide-reading"}:
        raise ValueError("Unsupported reading assistance state")
    if options.meaning_state not in {"show-meaning", "hide-meaning"}:
        raise ValueError("Unsupported meaning assistance state")
    if options.meaning_coverage not in {"all-selected", "adaptive"}:
        raise ValueError("Unsupported meaning coverage")
    return add_hash({
        "schema_version": 1,
        "id": "web-dictionary-adaptive-profile-v1",
        "label": "Web dictionary-only adaptive assistance",
        "preset_id": f"phase8-preset-{level.lower()}",
        "reading_assistance_policy": {"state": options.reading_state},
        "meaning_assistance_policy": {"state": options.meaning_state},
        "grammar_assistance_policy": {"state": "hide-grammar"},
        "overrides": [],
        "exposure_policy": {"enabled": False, "dimensions": []},
        "source_references": {
            "vocabulary_hash": stable_hash(vocabulary),
            "annotation_plan_hash": stable_hash(annotation_plan),
            "grammar_plan_hash": "none",
            "preset_dataset_hash": presets["hash"],
        },
        "provenance": "user",
    })


def _replace_epub_members(
    base_epub: Path, replacements: dict[str, bytes], output_epub: Path
) -> None:
    with zipfile.ZipFile(base_epub) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate EPUB archive member")
        if any(
            PurePosixPath(name).is_absolute()
            or ".." in PurePosixPath(name).parts
            or "\\" in name
            for name in names
        ):
            raise ValueError("Unsafe EPUB archive path")
        files = {name: archive.read(name) for name in names}
    if any(name not in files for name in replacements):
        raise ValueError("Adaptive XHTML does not match the packaged EPUB")
    files.update(replacements)
    write_deterministic_epub(files, output_epub)


def normalize_epub_archive(source_epub: str | Path, output_epub: str | Path) -> None:
    """Rewrite an EPUB with the project's deterministic safe ZIP metadata."""
    source = Path(source_epub)
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate EPUB archive member")
        if any(
            not name
            or PurePosixPath(name).is_absolute()
            or ".." in PurePosixPath(name).parts
            or "\\" in name
            for name in names
        ):
            raise ValueError("Unsafe EPUB archive path")
        files = {name: archive.read(name) for name in names}
    if files.get("mimetype") != b"application/epub+zip":
        raise ValueError("Invalid EPUB mimetype")
    write_deterministic_epub(files, Path(output_epub))


def _study_chapter_ids(book: dict[str, Any]) -> set[str]:
    administrative_markers = {
        "cover", "colophon", "caution", "bookwalker", "copyright",
        "fmatter", "frontmatter", "nav", "toc",
    }
    return {
        chapter["id"]
        for chapter in book["chapters"]
        if not any(
            marker in PurePosixPath(chapter["source_path"]).name.lower()
            for marker in administrative_markers
        )
    }


def _bounded_web_report(
    report,
    per_chapter_item_limit: int,
    allowed_chapter_ids: set[str] | None = None,
):
    """Retain a conservative source-ordered dictionary evidence window.

    A positive web limit keeps eight times that amount for each evidence kind,
    leaving deterministic room for overlaps and repeated lexical identities.
    Zero retains every safe match in allowed reading chapters.
    """
    window = (
        None
        if per_chapter_item_limit == 0
        else max(25, per_chapter_item_limit * 8)
    )
    candidate_chapters = {value.id: value.chapter_id for value in report.candidates}
    expression_chapters = {value.id: value.chapter_id for value in report.expressions}
    name_chapters = {value.id: value.chapter_id for value in report.name_occurrences}

    def bounded(values, chapter_for):
        counts: dict[str, int] = {}
        retained = []
        for value in values:
            chapter = chapter_for(value)
            if allowed_chapter_ids is not None and chapter not in allowed_chapter_ids:
                continue
            if window is not None and counts.get(chapter, 0) >= window:
                continue
            counts[chapter] = counts.get(chapter, 0) + 1
            retained.append(value)
        return retained

    dictionary_matches = bounded(
        report.dictionary_matches,
        lambda value: candidate_chapters[value.candidate_id],
    )
    expression_matches = bounded(
        report.expression_dictionary_matches,
        lambda value: expression_chapters[value.expression_id],
    )
    expression_ids = {value.expression_id for value in expression_matches}
    expressions = [value for value in report.expressions if value.id in expression_ids]
    name_matches = bounded(
        report.name_dictionary_matches,
        lambda value: name_chapters[value.name_id],
    )
    name_ids = {value.name_id for value in name_matches}
    names = [value for value in report.name_occurrences if value.id in name_ids]
    retained_candidate_ids = {
        value.candidate_id for value in dictionary_matches
    } | {
        candidate_id
        for value in expressions
        for candidate_id in value.candidate_ids
    } | {
        value.candidate_id for value in names
    }
    candidates = [
        value for value in report.candidates if value.id in retained_candidate_ids
    ]
    retained_token_ids = {
        value.token_id for value in candidates
    } | {
        token_id for value in expressions for token_id in value.token_ids
    } | {
        value.token_id for value in names
    }
    token_positions = {value.id: index for index, value in enumerate(report.tokens)}
    for candidate in candidates:
        index = token_positions[candidate.token_id]
        if index > 0:
            previous = report.tokens[index - 1]
            if previous.sentence_id == candidate.sentence_id:
                retained_token_ids.add(previous.id)
    tokens = [value for value in report.tokens if value.id in retained_token_ids]
    bounded_report = replace(
        report,
        tokens=tokens,
        candidates=candidates,
        dictionary_matches=dictionary_matches,
        expressions=expressions,
        expression_dictionary_matches=expression_matches,
        name_occurrences=names,
        name_dictionary_matches=name_matches,
        name_diagnostics=[],
    )
    validate_name_report(bounded_report)
    return bounded_report


def _sanitize_plan_for_linked_output(
    source: Path, book: dict[str, Any], plan: dict[str, Any]
) -> dict[str, Any]:
    from furiganalyse.linked_output import _leaf_blocks, _parent_map, _visible_map

    if not source.exists():
        return plan

    with zipfile.ZipFile(source) as z:
        archive_files = {name: z.read(name) for name in z.namelist()}

    block_refs = {}
    for ch in book.get("chapters", []):
        ch_path = ch.get("source_path")
        if not ch_path or ch_path not in archive_files:
            continue
        try:
            root = ET.fromstring(archive_files[ch_path])
            blocks_xml = list(_leaf_blocks(root))
            parents = _parent_map(root)
            for i, b in enumerate(ch.get("blocks", [])):
                if i < len(blocks_xml):
                    _, refs, rubies = _visible_map(blocks_xml[i])
                    block_refs[b["id"]] = (refs, rubies, parents)
        except Exception:
            continue

    sanitized_items = []
    dropped_count = 0
    for item in plan.get("items", []):
        valid_occs = []
        for occ in item.get("occurrences", []):
            b_id = occ.get("block_id")
            if b_id in block_refs:
                refs, rubies, parents = block_refs[b_id]
                start, end = occ.get("block_start", 0), occ.get("block_end", 0)
                if occ.get("annotation_target") == "ruby":
                    valid_occs.append(occ)
                elif end <= len(refs):
                    first, last = refs[start], refs[end - 1]
                    contained = [
                        v for v in rubies if v.start >= start and v.end <= end
                    ]
                    if contained:
                        ruby_parents = [parents.get(v.element) for v in contained]
                        if len(set(ruby_parents)) == 1 and None not in ruby_parents:
                            valid_occs.append(occ)
                        else:
                            dropped_count += 1
                    elif (
                        first.owner is last.owner
                        and first.attribute == last.attribute
                    ):
                        valid_occs.append(occ)
                    else:
                        dropped_count += 1
                else:
                    dropped_count += 1
            else:
                valid_occs.append(occ)

        if valid_occs:
            item_copy = dict(item)
            primary = valid_occs[0]
            item_copy["chapter_id"] = primary["chapter_id"]
            item_copy["block_id"] = primary["block_id"]
            item_copy["sentence_id"] = primary["sentence_id"]
            item_copy["token_ids"] = primary["token_ids"]
            item_copy["candidate_ids"] = primary["candidate_ids"]
            item_copy["expression_id"] = primary.get("expression_id")
            item_copy["name_id"] = primary.get("name_id")
            item_copy["publisher_ruby_id"] = primary.get("publisher_ruby_id")
            item_copy["occurrences"] = valid_occs
            sanitized_items.append(item_copy)

    if dropped_count > 0:
        sanitized_items.sort(
            key=lambda it: (
                it["chapter_id"],
                it["block_id"],
                it["sentence_id"],
                it["occurrences"][0]["sentence_start"],
            )
        )
        for item_idx, item_obj in enumerate(sanitized_items, start=1):
            item_id = f"study-item-{item_idx:04d}"
            item_obj["id"] = item_id
            item_obj["note_anchor_id"] = f"note-study-item-{item_idx:04d}"
            for occ_idx, occ_obj in enumerate(item_obj["occurrences"], start=1):
                occ_id = f"{item_id}-occ-{occ_idx:04d}"
                source_anchor_id = f"src-{item_id}-occ-{occ_idx:04d}"
                occ_obj["occurrence_number"] = occ_idx
                occ_obj["id"] = occ_id
                occ_obj["source_anchor_id"] = source_anchor_id
            item_obj["source_anchor_id"] = item_obj["occurrences"][0]["source_anchor_id"]

        result = dict(plan)
        result["items"] = sanitized_items
        return result
    return plan


def run_dictionary_study_pipeline(
    input_epub: str | Path,
    output_epub: str | Path,
    work_directory: str | Path,
    options: WebStudyOptions,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Build a dictionary-only study EPUB, optionally applying Phase 8 mechanics."""
    source = Path(input_epub)
    output = Path(output_epub)
    work = Path(work_directory)
    work.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() != ".epub":
        raise ValueError("Study EPUB processing currently accepts EPUB input only")
    if options.per_chapter_item_limit != 0 and not (
        1 <= options.per_chapter_item_limit <= 50
    ):
        raise ValueError("Study-item limit must be 0 (all) or between 1 and 50")
    jmdict_index = Path(
        os.environ.get("FURIGANALYSE_JMDICT_INDEX", "data/edrdg/JMdict.sqlite")
    )
    jmnedict_index = Path(
        os.environ.get("FURIGANALYSE_JMNEDICT_INDEX", "data/edrdg/JMnedict.sqlite")
    )
    if not jmdict_index.is_file() or not jmnedict_index.is_file():
        raise ValueError("Local EDRDG dictionary indexes are unavailable")

    def progress(value: dict[str, Any]) -> None:
        if progress_callback:
            progress_callback({"pipeline_mode": "study", **value})

    progress({"stage": "canonical-analysis"})
    book_model = extract_book(source)
    book = asdict(book_model)
    chapter_count = len(book["chapters"])
    character_count = sum(
        len(sentence["text"])
        for chapter in book["chapters"]
        for block in chapter["blocks"]
        for sentence in block["sentences"]
    )
    progress({
        "stage": "tokenizing",
        "sections_total": chapter_count,
        "characters_total": character_count,
        "log": f"Extracted EPUB: Found {chapter_count} chapters ({character_count:,} characters)",
    })
    evidence_window = (
        None
        if options.per_chapter_item_limit == 0
        else max(25, options.per_chapter_item_limit * 8)
    )
    base_report = analyze_vocabulary(book_model, progress_callback=progress)
    progress({
        "stage": "dictionary-lookup",
        "words_total": len(base_report.candidates),
        "log": f"Tokenized book: Found {len(base_report.candidates):,} unique vocabulary candidates across {chapter_count} chapters",
    })
    jmdict = SqliteJmdictProvider(
        jmdict_index, max_matches=1, max_senses_per_match=1
    )
    try:
        progress({
            "stage": "dictionary-lookup",
            "log": f"Querying local JMdict database for {len(base_report.candidates):,} vocabulary candidates and multi-word expressions…",
        })
        vocabulary_model = enrich_vocabulary_report(
            base_report,
            jmdict,
            include_expressions=True,
            progress_callback=progress,
            max_matches_per_chapter=evidence_window,
            exclude_closed_class_tokens=True,
        )
    finally:
        jmdict.close()
    del jmdict
    jmnedict = SqliteJmnedictProvider(
        jmnedict_index, max_matches=1, max_translations_per_match=1
    )
    try:
        progress({
            "stage": "name-lookup",
            "log": "Querying local JMnedict database for character names and proper nouns…",
        })
        vocabulary_model = enrich_name_report(
            vocabulary_model,
            jmnedict,
            progress_callback=progress,
            max_matches_per_chapter=evidence_window,
        )
    finally:
        jmnedict.close()
    del jmnedict
    vocabulary_model = _bounded_web_report(
        vocabulary_model,
        options.per_chapter_item_limit,
        _study_chapter_ids(book),
    )
    gc.collect()
    vocabulary = asdict(vocabulary_model)
    del vocabulary_model
    del base_report
    gc.collect()

    # Step A: Apply Series Memory Profile if selected (Cross-Volume Consistency)
    series_data = None
    if options.series_profile_id:
        from furiganalyse.series_glossary import (
            apply_series_profile_to_vocabulary,
            load_series_profile,
        )
        series_data = load_series_profile(options.series_profile_id)
        if series_data:
            vocabulary, patch_count = apply_series_profile_to_vocabulary(series_data, vocabulary)
            progress({
                "stage": "tokenizing",
                "log": f"Series Memory: Applied {patch_count} character & term overrides from series '{series_data.get('title')}'",
            })

    # Step B: Module 2: Publisher Ruby Propagation (extract and propagate author-assigned readings)
    if options.publisher_ruby_propagation:
        from furiganalyse.ruby_override import (
            apply_publisher_ruby_propagation,
            extract_publisher_ruby_map,
        )
        ruby_map = extract_publisher_ruby_map(book)
        if ruby_map:
            vocabulary, patch_count = apply_publisher_ruby_propagation(vocabulary, ruby_map)
            progress({
                "stage": "tokenizing",
                "log": f"Module 2: Extracted {len(ruby_map)} author ruby terms; propagated to {patch_count} unannotated instances",
            })

    # Module 4: LLM Proper Noun Furigana Correction (optional, independent of bilingual companion)
    if options.llm_enrich_nouns and options.llm_provider not in {"none", "", None}:
        from furiganalyse.proper_noun_resolver import (
            apply_proper_noun_overrides,
            collect_unresolved_proper_nouns,
            resolve_proper_nouns,
        )
        from furiganalyse.llm_provider import get_llm_provider

        enrich_model = options.llm_model or options.bilingual_model
        progress({
            "stage": "tokenizing",
            "log": f"Module 4: Collecting unresolved proper nouns (checking JMnedict and Series Memory)…",
        })
        unresolved = collect_unresolved_proper_nouns(vocabulary, book, series_profile=series_data)
        if unresolved:
            progress({
                "stage": "tokenizing",
                "log": f"Module 4: Found {len(unresolved)} proper nouns not in JMnedict or Series Memory — sending to LLM service: {options.llm_provider} ({enrich_model or 'default'})…",
            })
            llm_provider_instance = get_llm_provider(
                provider_name=options.llm_provider,
                api_key=options.llm_api_key,
                base_url=options.llm_base_url,
                model=enrich_model,
                progress_callback=progress,
                auto_fallback=True,
                debug_log_path=work / "llm_debug.log",
            )
            overrides = resolve_proper_nouns(
                unresolved,
                llm_provider_instance,
                model=enrich_model,
                series_profile=series_data,
                cache_dir=work / "llm_cache",
                progress_callback=progress,
            )
            if overrides:
                vocabulary = apply_proper_noun_overrides(vocabulary, overrides)
                progress({
                    "stage": "tokenizing",
                    "log": f"Module 4 complete: patched {len(overrides)} proper noun readings in vocabulary",
                })
        else:
            progress({
                "stage": "tokenizing",
                "log": "Module 4: All proper nouns already resolved by JMnedict — no LLM call needed",
            })

    _write_json(work / "book.json", book)
    _write_json(work / "vocabulary.json", vocabulary)

    progress({
        "stage": "study-selection",
        "log": f"EDRDG Dictionary Matching complete: {len(vocabulary['dictionary_matches']):,} word senses and {len(vocabulary['name_dictionary_matches']):,} proper names",
    })
    selection_limit = options.per_chapter_item_limit
    if selection_limit == 0:
        # This upper bound exceeds the number of selectable lexical groups in
        # any one chapter without changing the established plan schema.
        selection_limit = max(
            1,
            len(vocabulary["dictionary_matches"])
            + len(vocabulary["expression_dictionary_matches"])
            + len(vocabulary["name_dictionary_matches"]),
        )
    phase4_plan = asdict(create_annotation_plan(
        vocabulary,
        StudyPlanConfig(per_chapter_item_limit=selection_limit),
        prefer_occurrence_reading=True,
    ))
    annotation_plan = promote_dictionary_only_plan(phase4_plan)
    _write_json(work / "annotation-plan.json", annotation_plan)
    total_occs = sum(len(it["occurrences"]) for it in annotation_plan["items"])
    progress({
        "stage": "study-selection",
        "log": f"Study Annotation Plan: Selected {len(annotation_plan['items']):,} study items ({total_occs:,} occurrences) across {chapter_count} chapters",
    })

    # Module 3: LLM Contextual Study Note Gloss Enrichment (optional, all conversion modes)
    if options.llm_enrich_glosses and options.llm_provider not in {"none", "", None}:
        from furiganalyse.contextual_gloss import (
            apply_gloss_enrichments,
            collect_gloss_candidates,
            enrich_glosses,
        )
        from furiganalyse.llm_provider import get_llm_provider as _get_llm

        enrich_model = options.llm_model or options.bilingual_model
        gloss_candidates = collect_gloss_candidates(annotation_plan, book)
        if gloss_candidates:
            progress({
                "stage": "study-selection",
                "log": f"Module 3: Enriching {len(gloss_candidates)} study note glosses with LLM service: {options.llm_provider} ({enrich_model or 'default'})…",
            })
            _llm = _get_llm(
                provider_name=options.llm_provider,
                api_key=options.llm_api_key,
                base_url=options.llm_base_url,
                model=enrich_model,
                progress_callback=progress,
                auto_fallback=True,
                debug_log_path=work / "llm_debug.log",
            )
            glosses = enrich_glosses(
                gloss_candidates,
                _llm,
                model=enrich_model,
                series_profile=series_data,
                cache_dir=work / "llm_cache",
                progress_callback=progress,
            )
            if glosses:
                annotation_plan = apply_gloss_enrichments(annotation_plan, glosses)
                _write_json(work / "annotation-plan-enriched.json", annotation_plan)

    progress({
        "stage": "linked-rendering",
        "study_items": len(annotation_plan["items"]),
        "log": f"Sanitizing annotation plan against XHTML DOM element boundaries…",
    })
    annotation_plan = _sanitize_plan_for_linked_output(source, book, annotation_plan)
    progress({
        "stage": "linked-rendering",
        "study_items": len(annotation_plan["items"]),
        "log": f"Rendering interactive popups and study notes across {chapter_count} chapters…",
    })
    linked = create_linked_output(source, book, annotation_plan)
    guided_plan = None
    guided_report = None
    if options.guided_reading:
        guided_plan = build_guided_reading_plan(book, vocabulary, annotation_plan)
        linked, guided_report = render_guided_reading(
            linked,
            book,
            guided_plan,
        )
        _write_json(work / "guided-reading-plan.json", guided_plan)
        _write_json(work / "guided-reading-report.json", guided_report)
    linked = replace(linked, files=_prepare_web_linked_files(linked.files))
    linked_directory = work / "linked"
    write_linked_output(linked, linked_directory)

    rendering_report = None
    density_report = None
    assistance_report = None
    if options.experimental_adaptive:
        progress({"stage": "assistance-selection"})
        presets = build_web_preset_dataset()
        profile = build_web_profile(vocabulary, annotation_plan, presets, options)
        assistance_report = build_assistance_report(
            vocabulary,
            annotation_plan,
            None,
            profile,
            presets,
            None,
            enabled=True,
        )
        progress({"stage": "density-planning"})
        policies = build_web_density_dataset(
            all_selected_meanings=options.meaning_coverage == "all-selected"
        )
        density_report = build_density_report(
            book,
            annotation_plan,
            None,
            assistance_report,
            policies,
            policy_id=f"phase8-density-{options.preset_level.lower()}",
            enabled=True,
        )
        progress({"stage": "adaptive-rendering"})
        rendering_report, adaptive_files = render_adaptive_output(
            linked_directory,
            book,
            annotation_plan,
            None,
            assistance_report,
            density_report,
            enabled=True,
            strict_source_markup=False,
        )
        final_linked = split_study_notes_by_source_document(
            LinkedOutput(notes_path=linked.notes_path, files=adaptive_files),
            book,
        )
        write_output(final_linked.files, work / "adaptive")
    else:
        final_linked = split_study_notes_by_source_document(linked, book)
        write_linked_output(final_linked, linked_directory)

    base_epub_target = output if not options.bilingual_companion else (work / "base-study.epub")
    write_deterministic_epub(
        package_study_epub(
            source,
            book,
            annotation_plan,
            linked_output=final_linked,
        ),
        base_epub_target,
    )
    normalize_epub_archive(base_epub_target, output)
    main_size = os.path.getsize(output)

    if assistance_report is not None:
        _write_json(work / "assistance.json", assistance_report)
        _write_json(work / "density.json", density_report)
        _write_json(work / "rendering.json", rendering_report)

    summary = {
        "schema_version": 1,
        "mode": (
            "guided-reading"
            if options.guided_reading
            else "experimental-adaptive"
            if options.experimental_adaptive
            else "dictionary-study"
        ),
        "chapters": chapter_count,
        "canonical_characters": character_count,
        "tokens": len(vocabulary["tokens"]),
        "vocabulary_candidates": len(vocabulary["candidates"]),
        "dictionary_matches": len(vocabulary["dictionary_matches"]),
        "expression_matches": len(vocabulary["expression_dictionary_matches"]),
        "name_matches": len(vocabulary["name_dictionary_matches"]),
        "study_items": len(annotation_plan["items"]),
        "study_occurrences": sum(
            len(item["occurrences"]) for item in annotation_plan["items"]
        ),
        "study_note_pages": sum(
            "/study-notes-page-" in path and path.endswith(".xhtml")
            for path in final_linked.files
        ),
        "guided_items": len(guided_plan["items"]) if guided_plan else 0,
        "guided_occurrences": (
            guided_report["rendered_occurrences"] if guided_report else 0
        ),
        "guided_note_pages": (
            guided_report["guided_note_pages"] if guided_report else 0
        ),
        "adaptive_occurrences": (
            len(density_report["occurrence_plans"]) if density_report else 0
        ),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "provider_calls": 0,
        "network_dictionary_lookups": 0,
    }
    _write_json(work / "summary.json", summary)

    # Extract discovered cast members and glossary terms from annotation plan and vocabulary
    discovered_casts = []
    seen_names = set()
    for item in annotation_plan.get("items", []):
        if item.get("kind") == "name":
            name = item.get("surface", "")
            if name and name not in seen_names:
                seen_names.add(name)
                discovered_casts.append({
                    "name": name,
                    "romanized": item.get("reading") or name,
                    "role": "Character / Proper Name",
                })
        if len(discovered_casts) >= 20:
            break

    if len(discovered_casts) < 20:
        for match in vocabulary.get("name_dictionary_matches", []):
            name = match.get("surface", "")
            if name and name not in seen_names:
                seen_names.add(name)
                discovered_casts.append({
                    "name": name,
                    "romanized": match.get("reading") or name,
                    "role": "Proper Name",
                })
            if len(discovered_casts) >= 20:
                break

    discovered_glossary = []
    seen_terms = set()
    for item in annotation_plan.get("items", []):
        if item.get("kind") != "name":
            term = item.get("surface", "")
            if term and term not in seen_terms:
                seen_terms.add(term)
                meaning = item.get("contextual_gloss") or item.get("display_meaning") or ""
                first_meaning = meaning.split("\n")[0].replace("✦ Story Context:", "").strip()
                discovered_glossary.append({
                    "japanese": term,
                    "translation": first_meaning[:80],
                    "definition": first_meaning[:120],
                })
            if len(discovered_glossary) >= 30:
                break

    progress({
        "stage": "complete" if not options.bilingual_companion else "bilingual-translation",
        "main_file_ready": True,
        "main_output_bytes": main_size,
        "study_items": summary["study_items"],
        "cast_summary": discovered_casts,
        "glossary_summary": discovered_glossary,
        "log": f"Primary converted ebook ready: {output.name} ({main_size:,} bytes) — Available for download now!",
    })

    if options.bilingual_companion:
        from furiganalyse.bilingual_context import build_book_context
        from furiganalyse.bilingual_epub import package_bilingual_epub
        from furiganalyse.bilingual_translation import TranslationCache, translate_chapter
        from furiganalyse.llm_provider import get_llm_provider

        model_name = options.bilingual_model or ("qwen-plus-character" if options.bilingual_provider in {"alibaba", "dashscope"} else ("gemini-flash-latest" if options.bilingual_provider in {"google", "gemini"} else "gpt-4o-mini"))
        provider_display = (
            f"Alibaba Cloud (Qwen) · {model_name}" if options.bilingual_provider in {"alibaba", "dashscope"} else (
                f"Google AI Studio · {model_name}" if options.bilingual_provider in {"google", "gemini"} else (
                    f"Hetzner · {model_name}" if options.bilingual_provider == "hetzner" else (
                        f"OpenAI · {model_name}" if options.bilingual_provider == "openai" else (
                            f"OpenRouter · {model_name}" if options.bilingual_provider == "openrouter" else (
                                f"Ollama · {model_name}" if options.bilingual_provider == "ollama" else "Offline Fallback"
                            )
                        )
                    )
                )
            )
        )

        progress({
            "stage": "bilingual-translation",
            "log": f"Pass 1: Discovering Cast & Terminology Pre-Context using LLM service: {provider_display}…",
            "main_file_ready": True,
            "main_output_bytes": main_size,
        })

        provider = get_llm_provider(
            provider_name=options.bilingual_provider,
            api_key=options.bilingual_api_key,
            base_url=options.bilingual_base_url,
            model=options.bilingual_model,
            progress_callback=progress,
            auto_fallback=True,
            debug_log_path=work / "llm_debug.log",
        )
        book_context = build_book_context(
            book,
            vocabulary,
            provider=provider,
            model=model_name,
            progress_callback=progress,
            series_profile=series_data,
        )

        cast_summary = [
            {
                "name": k,
                "romanized": v.romanized,
                "role": v.role,
                "gender": v.gender,
                "aliases": list(v.aliases),
            }
            for k, v in list(book_context.characters.items())[:20]
        ]
        glossary_summary = [
            {
                "japanese": k,
                "translation": v.preferred_translation,
                "definition": v.definition,
            }
            for k, v in list(book_context.glossary.items())[:30]
        ]

        trans_cache = TranslationCache(cache_dir=work / "translation_cache")
        translated_chapters = []

        chapters = book.get("chapters", [])
        total_chapters = len(chapters)
        total_paragraphs = sum(len(ch.get("blocks", [])) for ch in chapters)
        completed_paragraphs = 0
        total_cache_hits = 0

        progress({
            "stage": "bilingual-translation",
            "translation_model": model_name,
            "translation_backend": provider_display,
            "translation_chapters_completed": 0,
            "translation_chapters_total": total_chapters,
            "translation_paragraphs_completed": 0,
            "translation_paragraphs_total": total_paragraphs,
            "translation_cache_hits": 0,
            "cast_summary": cast_summary,
            "glossary_summary": glossary_summary,
            "main_file_ready": True,
            "main_output_bytes": main_size,
            "log": f"Pass 1 Complete: Discovered {len(cast_summary)} characters and {len(glossary_summary)} glossary terms. Starting scene translation…",
        })

        for i, ch in enumerate(chapters, start=1):
            ch_title = ch.get("title", f"Chapter {i}")
            progress({
                "stage": "bilingual-translation",
                "log": f"Translating Chapter {i}/{total_chapters} '{ch_title}' with {model_name}…",
                "main_file_ready": True,
                "main_output_bytes": main_size,
            })

            def make_on_batch(ch_idx: int, done_base: int, cache_base: int):
                def on_batch(data: dict[str, Any]):
                    progress({
                        "stage": "bilingual-translation",
                        "translation_model": model_name,
                        "translation_backend": provider_display,
                        "translation_chapters_completed": ch_idx - 1,
                        "translation_chapters_total": total_chapters,
                        "translation_paragraphs_completed": done_base + data.get("paragraphs_done", 0),
                        "translation_paragraphs_total": total_paragraphs,
                        "translation_cache_hits": cache_base + (1 if data.get("cache_hit") else 0),
                        "translation_current_chapter": data.get("chapter_title", f"Chapter {ch_idx}"),
                        "translation_latest_japanese": data.get("latest_japanese", ""),
                        "translation_latest_english": data.get("latest_english", ""),
                        "main_file_ready": True,
                        "main_output_bytes": main_size,
                        "log": (
                            f"Translated {data.get('paragraphs_done', 0)}/{data.get('paragraphs_total', 0)} paragraphs in {data.get('chapter_title', f'Chapter {ch_idx}')}"
                            if not data.get("latest_english", "").startswith("Model generating")
                            else f"Translating scene in {data.get('chapter_title', f'Chapter {ch_idx}')}…"
                        ),
                    })
                return on_batch

            trans_ch = translate_chapter(
                ch,
                book_context,
                provider=provider,
                cache=trans_cache,
                model=model_name,
                batch_callback=make_on_batch(i, completed_paragraphs, total_cache_hits),
            )
            translated_chapters.append(trans_ch)
            completed_paragraphs += len(trans_ch.paragraphs)
            total_cache_hits += trans_ch.cache_hits

            progress({
                "stage": "bilingual-translation",
                "translation_model": model_name,
                "translation_backend": provider_display,
                "translation_chapters_completed": i,
                "translation_chapters_total": total_chapters,
                "translation_paragraphs_completed": completed_paragraphs,
                "translation_paragraphs_total": total_paragraphs,
                "translation_cache_hits": total_cache_hits,
                "main_file_ready": True,
                "main_output_bytes": main_size,
                "log": f"Completed Chapter {i}/{total_chapters} '{ch_title}' ({len(trans_ch.paragraphs)} paragraphs translated)",
            })

        # Save standalone bilingual companion EPUB alongside main output
        bilingual_target = Path(str(output).replace(".epub", " - Bilingual Companion.epub"))
        package_bilingual_epub(base_epub_target, bilingual_target, translated_chapters)
        bilingual_size = os.path.getsize(bilingual_target)

        progress({
            "stage": "complete",
            "main_file_ready": True,
            "bilingual_file_ready": True,
            "main_output_bytes": main_size,
            "bilingual_output_bytes": bilingual_size,
            "output_bytes": main_size,
            "log": f"All chapters translated! Standalone Bilingual Companion EPUB packaged: {bilingual_target.name} ({bilingual_size:,} bytes)",
        })
    else:
        progress({
            "stage": "complete",
            "main_file_ready": True,
            "main_output_bytes": main_size,
            "output_bytes": main_size,
            "study_items": summary["study_items"],
            "log": f"Conversion complete: Converted ebook ready at {output.name} ({main_size:,} bytes)",
        })

    return summary
