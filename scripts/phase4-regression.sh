#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
./scripts/phase3-regression.sh
OUT=artifacts/phase4
SOURCE=artifacts/phase3/jmnedict/run-a/vocabulary.json
GOLDEN=tests/phase4_golden/annotation-plan-v1.json
mkdir -p "$OUT/run-a" "$OUT/run-b"
.venv/bin/python scripts/create_study_plan.py "$SOURCE" "$OUT/run-a/annotation-plan.json"
.venv/bin/python scripts/create_study_plan.py "$SOURCE" "$OUT/run-b/annotation-plan.json"
cmp "$OUT/run-a/annotation-plan.json" "$OUT/run-b/annotation-plan.json"
cmp "$OUT/run-a/annotation-plan.json" "$GOLDEN"
NOTES=$OUT/notes
NOTES_GOLDEN=tests/phase4_golden/study-notes-v1.xhtml
mkdir -p "$NOTES/run-a" "$NOTES/run-b"
.venv/bin/python scripts/render_study_notes.py "$OUT/run-a/annotation-plan.json" "$NOTES/run-a/study-notes.xhtml"
.venv/bin/python scripts/render_study_notes.py "$OUT/run-a/annotation-plan.json" "$NOTES/run-b/study-notes.xhtml"
cmp "$NOTES/run-a/study-notes.xhtml" "$NOTES/run-b/study-notes.xhtml"
cmp "$NOTES/run-a/study-notes.xhtml" "$NOTES_GOLDEN"
LINKED=$OUT/linked
LINKED_GOLDEN=tests/phase4_golden/linked-v1
mkdir -p "$LINKED/run-a" "$LINKED/run-b"
.venv/bin/python scripts/render_linked_study_notes.py artifacts/phase2/fixture.epub artifacts/phase2/run-a/book.json "$OUT/run-a/annotation-plan.json" "$LINKED/run-a"
.venv/bin/python scripts/render_linked_study_notes.py artifacts/phase2/fixture.epub artifacts/phase2/run-a/book.json "$OUT/run-a/annotation-plan.json" "$LINKED/run-b"
diff -ru "$LINKED/run-a" "$LINKED/run-b"
diff -ru "$LINKED_GOLDEN" "$LINKED/run-a"
EPUB_OUT=$OUT/epub
mkdir -p "$EPUB_OUT"
.venv/bin/python scripts/package_study_epub.py artifacts/phase2/fixture.epub artifacts/phase2/run-a/book.json "$OUT/run-a/annotation-plan.json" "$EPUB_OUT/run-a.epub"
.venv/bin/python scripts/package_study_epub.py artifacts/phase2/fixture.epub artifacts/phase2/run-a/book.json "$OUT/run-a/annotation-plan.json" "$EPUB_OUT/run-b.epub"
cmp "$EPUB_OUT/run-a.epub" "$EPUB_OUT/run-b.epub"
.venv/bin/python -c "from tests.phase0_epub import validate_epub; import sys; e=validate_epub('$EPUB_OUT/run-a.epub'); print(e); sys.exit(bool(e))"
.venv/bin/python -m pytest -q tests/test_study_plan.py tests/test_study_notes.py tests/test_linked_output.py tests/test_epub_packaging.py
echo "Phase 4 regression passed; artifacts retained under $OUT/"
