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
    })
    jmdict = SqliteJmdictProvider(
        jmdict_index, max_matches=1, max_senses_per_match=1
    )
    try:
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
    _write_json(work / "book.json", book)
    _write_json(work / "vocabulary.json", vocabulary)

    progress({"stage": "study-selection"})
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
    progress({"stage": "linked-rendering", "study_items": len(annotation_plan["items"])})
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

    if options.bilingual_companion:
        progress({"stage": "bilingual-translation"})
        from furiganalyse.bilingual_context import build_book_context
        from furiganalyse.bilingual_epub import package_bilingual_epub
        from furiganalyse.bilingual_translation import TranslationCache, translate_chapter
        from furiganalyse.llm_provider import get_llm_provider

        provider = get_llm_provider(
            provider_name=options.bilingual_provider,
            api_key=options.bilingual_api_key,
            base_url=options.bilingual_base_url,
            model=options.bilingual_model,
        )
        book_context = build_book_context(book, vocabulary, provider=provider)
        trans_cache = TranslationCache(cache_dir=work / "translation_cache")
        translated_chapters = []

        for ch in book.get("chapters", []):
            trans_ch = translate_chapter(
                ch,
                book_context,
                provider=provider,
                cache=trans_cache,
                model=options.bilingual_model or "gpt-4o-mini",
            )
            translated_chapters.append(trans_ch)

        package_bilingual_epub(base_epub_target, output, translated_chapters)

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
    progress({"stage": "packaging", "study_items": summary["study_items"]})
    return summary
