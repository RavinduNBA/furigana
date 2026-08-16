# Phase 1 Calibre checklist

Run `./scripts/phase1-regression.sh`, then open these artifacts in Calibre:

- `artifacts/phase1/fixture.epub`
- `artifacts/phase1/fixture-converted.epub`

Record the Calibre version and date, then compare both books:

- both chapters, table-of-contents entries, links, image, and styling work;
- grouped `表舞台【おもてぶたい】` remains one publisher annotation;
- `雪乃【ゆきの】` retains its `rb`/`rp` fallback structure and reading;
- unusual `第一【ファースト】` is not replaced by a dictionary reading;
- publisher ruby containing emphasis and span markup renders normally;
- malformed `未知` ruby remains visible without a guessed reading;
- ordinary kanji immediately after publisher or malformed ruby gains furigana;
- no publisher ruby contains nested generated ruby;
- no unexpected layout or navigation difference is visible.

Phase 1 is complete only after this checklist is recorded as passed. Packed and
unpacked diagnostic artifacts remain under `artifacts/phase1/`.
