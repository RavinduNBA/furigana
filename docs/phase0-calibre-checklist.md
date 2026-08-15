# Phase 0 Calibre checklist

Run `./scripts/phase0-regression.sh`, then copy these remote artifacts to a
machine with Calibre:

- `artifacts/phase0/fixture.epub`
- `artifacts/phase0/fixture-converted.epub`

Record the Calibre version and date, then check both books:

- chapters and table-of-contents entries are in the correct order;
- the chapter link and backlink resolve;
- the lantern image, stylesheet, dialogue punctuation, and emphasis survive;
- Japanese, English, numbers, and Greek text survive;
- publisher readings for the grouped words and unusual name survive;
- ordinary kanji gains generated furigana only in the converted book;
- no unexpected layout or navigation difference appears.

Phase 0 is not complete until this checklist is recorded as passed. Failed and
unpacked artifacts remain under `artifacts/phase0/` for diagnosis.
