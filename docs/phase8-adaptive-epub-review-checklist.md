# Phase 8 adaptive-assistance EPUB review checklist

Use this checklist for the deterministic synthetic adaptive EPUB under
`artifacts/phase8/epub/`. Complete machine verification before opening the
fixture in Calibre 8.14.

## Machine verification

- [ ] Run-A and run-B EPUB bytes and packaging reports are identical.
- [ ] The output SHA-256 equals the checked-in structural golden.
- [ ] The archive has exactly eight safe members; `mimetype` is first, exact,
  and stored, while remaining members use deterministic metadata and deflate.
- [ ] Container, EPUB 3 metadata, manifest, spine, and navigation are valid.
- [ ] Spine and TOC order are chapter 1, chapter 2, Study Notes, Grammar Study
  Notes; vocabulary and grammar navigation remain separate.
- [ ] All four packaged XHTML members equal the approved adaptive XHTML bytes,
  parse as Japanese namespaced XHTML, and have resolvable relative links.
- [ ] One generated reading (`前` / `まえ`) and one approved meaning (`to read`)
  are present; suppressed assistance is absent rather than hidden.
- [ ] Five study links/backlinks and two grammar links/backlinks resolve.
- [ ] Three grammar notes and three contexts remain; reference-only, rejected,
  density-suppressed, and publisher-protected cases are not promoted.
- [ ] Publisher ruby `publisher-ruby-1-8-1` remains `表舞台` / `おもてぶたい`
  without wrapping, splitting, nesting, or generated duplication.
- [ ] Disabled and all failure EPUBs equal the Phase 7 base EPUB byte-for-byte.
- [ ] Phase 3, Phase 5, Phase 7, and prior Phase 8 compatibility checks pass.
- [ ] Reports contain no suppressed content, learner identity, credentials,
  paths, provider/model/cache data, raw exceptions, or hidden audit metadata.

## Calibre 8.14 review

- [ ] Record Calibre version, fixture path, and output SHA-256.
- [ ] Confirm the four-entry TOC and separate Study Notes / Grammar Study Notes.
- [ ] Confirm Japanese text, punctuation, emphasis, and layout render normally.
- [ ] Confirm `前` displays the generated reading `まえ` and its name link works.
- [ ] Confirm only `to read` is displayed as an adaptive meaning and suppressed
  readings/meanings do not appear.
- [ ] Confirm all five study links and backlinks return to exact occurrences.
- [ ] Confirm both grammar links and backlinks return to exact occurrences.
- [ ] Confirm reference-only, partial-overlap, density-suppressed, and publisher-
  adjacent grammar occurrences remain nonnavigable.
- [ ] Confirm `表舞台【おもてぶたい】` and its study link render unchanged.
- [ ] Confirm no broken links, nested-link/ruby artifacts, duplicated text,
  hidden assistance, learner metadata, or unexpected layout changes are visible.

## Qualifications and approval

- [ ] This is a legal synthetic mechanics fixture, not evidence of pedagogical
  validity, JLPT placement accuracy, production dictionary approval, or a real
  learner's knowledge.
- [ ] Suppression changes presentation only; it does not delete source evidence,
  dictionary records, approved meanings/readings, grammar evidence, or state.
- [ ] The unavailable expression reading remains a deliberate no-op with the
  nonfatal reason `missing-approved-reading`; no reading is invented.

Reviewer: _pending_

Date: _pending_

Calibre version: _pending_

Fixture: _pending_

Result: _pending_

Notes: _pending_
