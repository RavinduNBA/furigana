# Phase 2 canonical JSON trace checklist

Use the copyright-free fixture and generated JSON retained by:

```bash
./scripts/phase2-regression.sh
```

Inspect `artifacts/phase2/fixture.epub` and
`artifacts/phase2/run-a/book.json`. This is a data inspection gate; Calibre is
not required because Phase 2 does not modify or render an EPUB.

## Trace

- [ ] Open `EPUB/text/chapter-01.xhtml` inside the fixture.
- [ ] Find paragraph `publisher-ruby-cases`.
- [ ] Confirm it maps to chapter `ch-0001`, block `ch-0001-b-0004`.
- [ ] Confirm the first sentence is `ch-0001-b-0004-s-0001`.
- [ ] Confirm its text is `舞台は表舞台だった。` at block offsets 0 through 10.
- [ ] Confirm its spans are `舞台は` (0..3), `表舞台` (3..6), and `だった。`
      (6..10), in that order with no gap or overlap.
- [ ] Confirm the middle span references `ch-0001-b-0004-r-0001`.
- [ ] Confirm that ruby record has surface `表舞台`, reading `おもてぶたい`,
      source `publisher`, and source anchor `publisher-grouped`.
- [ ] Confirm `おもてぶたい` is absent from sentence and chapter text.
- [ ] Confirm `run-a/book.json` and `run-b/book.json` are byte-identical.
- [ ] Confirm generated JSON matches `tests/golden/phase2-book-v2.json`.

## Result

- Date:
- Commit:
- Reviewer:
- Trace result: pass / fail
- Notes:
