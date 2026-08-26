"""Rebuild all 4 processing mode EPUBs for the sample book."""
import os
import shutil
import sys
from pathlib import Path

from furiganalyse.__main__ import main as furigana_main
from furiganalyse.params import FuriganaMode, OutputFormat, WritingMode
from furiganalyse.web_study_pipeline import run_dictionary_study_pipeline, WebStudyOptions, normalize_epub_archive

SOURCE = Path("sample_book/魔法科高校の劣等生 1.epub")
OUT_FURI = Path("sample_book/魔法科高校の劣等生 1 - Furigana.epub")
OUT_STUDY = Path("sample_book/魔法科高校の劣等生 1 - Study.epub")
OUT_COMBINED = Path("sample_book/魔法科高校の劣等生 1 - Combined.epub")
OUT_GUIDED = Path("sample_book/魔法科高校の劣等生 1 - Guided.epub")

WORK = Path("/tmp/rebuild_work")
shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True)

def log(msg):
    print(msg, flush=True)

# ── Furigana ─────────────────────────────────────────────────────────────────
log("=== [1/4] Furigana mode ===")
furigana_main(
    str(SOURCE),
    str(OUT_FURI),
    furigana_mode=FuriganaMode.add,
    output_format=OutputFormat.epub,
    writing_mode=WritingMode.auto,
)
log(f"  → {OUT_FURI} ({OUT_FURI.stat().st_size // 1024} KB)")

# ── Study ─────────────────────────────────────────────────────────────────────
log("=== [2/4] Study mode ===")
study_work = WORK / "study"
run_dictionary_study_pipeline(
    SOURCE,
    OUT_STUDY,
    study_work,
    WebStudyOptions(per_chapter_item_limit=50),
)
log(f"  → {OUT_STUDY} ({OUT_STUDY.stat().st_size // 1024} KB)")

# ── Combined ──────────────────────────────────────────────────────────────────
log("=== [3/4] Combined mode ===")
combined_work = WORK / "combined"
combined_work.mkdir()
furi_stage = combined_work / "furi-stage.epub"
furigana_main(
    str(SOURCE),
    str(furi_stage),
    furigana_mode=FuriganaMode.add,
    output_format=OutputFormat.epub,
    writing_mode=WritingMode.auto,
)
combined_stage = combined_work / "annotated-stage.epub"
run_dictionary_study_pipeline(
    furi_stage,
    combined_stage,
    combined_work / "study-work",
    WebStudyOptions(per_chapter_item_limit=50),
)
normalize_epub_archive(combined_stage, str(OUT_COMBINED))
log(f"  → {OUT_COMBINED} ({OUT_COMBINED.stat().st_size // 1024} KB)")

# ── Guided ────────────────────────────────────────────────────────────────────
log("=== [4/4] Guided mode ===")
guided_work = WORK / "guided"
guided_work.mkdir()
furi_stage_g = guided_work / "furi-stage.epub"
furigana_main(
    str(SOURCE),
    str(furi_stage_g),
    furigana_mode=FuriganaMode.add,
    output_format=OutputFormat.epub,
    writing_mode=WritingMode.auto,
)
guided_stage = guided_work / "annotated-stage.epub"
run_dictionary_study_pipeline(
    furi_stage_g,
    guided_stage,
    guided_work / "study-work",
    WebStudyOptions(per_chapter_item_limit=0, guided_reading=True),
)
normalize_epub_archive(guided_stage, str(OUT_GUIDED))
log(f"  → {OUT_GUIDED} ({OUT_GUIDED.stat().st_size // 1024} KB)")

log("\n✓ All 4 EPUBs rebuilt successfully.")
