# Phase 2 canonical JSON trace checklist

Use the copyright-free fixture and generated JSON retained by:

```bash
./scripts/phase2-regression.sh
```

Inspect `artifacts/phase2/fixture.epub` and
`artifacts/phase2/run-a/book.json`. This is a data inspection gate; Calibre is
not required because Phase 2 does not modify or render an EPUB.

## Trace

- [x] Open `EPUB/text/chapter-01.xhtml` inside the fixture.
- [x] Find paragraph `publisher-ruby-cases`.
- [x] Confirm it maps to chapter `ch-0001`, block `ch-0001-b-0004`.
- [x] Confirm the first sentence is `ch-0001-b-0004-s-0001`.
- [x] Confirm its text is `舞台は表舞台だった。` at block offsets 0 through 10.
- [x] Confirm its spans are `舞台は` (0..3), `表舞台` (3..6), and `だった。`
      (6..10), in that order with no gap or overlap.
- [x] Confirm the middle span references `ch-0001-b-0004-r-0001`.
- [x] Confirm that ruby record has surface `表舞台`, reading `おもてぶたい`,
      source `publisher`, and source anchor `publisher-grouped`.
- [x] Confirm `おもてぶたい` is absent from sentence and chapter text.
- [x] Confirm `run-a/book.json` and `run-b/book.json` are byte-identical.
- [x] Confirm generated JSON matches `tests/golden/phase2-book-v2.json`.

## Result

- Date: 2026-08-16
- Commit: `c774358`
- Reviewer: Ravindu
- Trace result: pass
- Notes: Visual XHTML trace confirmed by reviewer. All 49 canonical IDs were
  unique; offsets, text slices, span ordering, and ruby references passed.
  Run-A, run-B, and golden JSON shared SHA-256
  `63ab8dc0708e71d5af3876dc3b011223b1f804f76111a33dbb363f6df412afde`.
