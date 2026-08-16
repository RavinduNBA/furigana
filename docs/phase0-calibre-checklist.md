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

## Verification record

- Date: 2026-08-15
- Reader: Calibre 8.14
- Result: passed
- Chapters, table of contents, forward links, backlinks, image, Japanese and
  non-Japanese text, publisher ruby, and generated ruby were manually verified.
- The `<em>` element and `font-style: italic` rule survived conversion. The
  selected Japanese font did not make the italic styling visually distinct,
  so this item was confirmed from the EPUB structure as well as by comparing
  the original and converted books.

Phase 0 is complete. Failed and unpacked artifacts remain under
`artifacts/phase0/` for future diagnosis.
