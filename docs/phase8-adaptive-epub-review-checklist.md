# Phase 8 adaptive-assistance EPUB review checklist

Use this checklist for the deterministic synthetic adaptive EPUB under
`artifacts/phase8/epub/`. Complete machine verification before opening the
fixture in Calibre 8.14.

## Machine verification

- [x] Run-A and run-B EPUB bytes and packaging reports are identical.
- [x] The output SHA-256 equals the checked-in structural golden.
- [x] The archive has exactly eight safe members; `mimetype` is first, exact,
  and stored, while remaining members use deterministic metadata and deflate.
- [x] Container, EPUB 3 metadata, manifest, spine, and navigation are valid.
- [x] Spine and TOC order are chapter 1, chapter 2, Study Notes, Grammar Study
  Notes; vocabulary and grammar navigation remain separate.
- [x] All four packaged XHTML members equal the approved adaptive XHTML bytes,
  parse as Japanese namespaced XHTML, and have resolvable relative links.
- [x] One generated reading (`前` / `まえ`) and one approved meaning (`to read`)
  are present; suppressed assistance is absent rather than hidden.
- [x] Five study links/backlinks and two grammar links/backlinks resolve.
- [x] Three grammar notes and three contexts remain; reference-only, rejected,
  density-suppressed, and publisher-protected cases are not promoted.
- [x] Publisher ruby `publisher-ruby-1-8-1` remains `表舞台` / `おもてぶたい`
  without wrapping, splitting, nesting, or generated duplication.
- [x] Disabled and all failure EPUBs equal the Phase 7 base EPUB byte-for-byte.
- [x] Phase 3, Phase 5, Phase 7, and prior Phase 8 compatibility checks pass.
- [x] Reports contain no suppressed content, learner identity, credentials,
  paths, provider/model/cache data, raw exceptions, or hidden audit metadata.

## Calibre 8.14 review

- [x] Record Calibre version, fixture path, and output SHA-256.
- [x] Confirm the four-entry TOC and separate Study Notes / Grammar Study Notes.
- [x] Confirm Japanese text, punctuation, emphasis, and layout render normally.
- [x] Confirm `前` displays the generated reading `まえ` and its name link works.
- [x] Confirm only `to read` is displayed as an adaptive meaning and suppressed
  readings/meanings do not appear.
- [x] Confirm all five study links and backlinks return to exact occurrences.
- [x] Confirm both grammar links and backlinks return to exact occurrences.
- [x] Confirm reference-only, partial-overlap, density-suppressed, and publisher-
  adjacent grammar occurrences remain nonnavigable.
- [x] Confirm `表舞台【おもてぶたい】` and its study link render unchanged.
- [x] Confirm no broken links, nested-link/ruby artifacts, duplicated text,
  hidden assistance, learner metadata, or unexpected layout changes are visible.

## Qualifications and approval

- [x] This is a legal synthetic mechanics fixture, not evidence of pedagogical
  validity, JLPT placement accuracy, production dictionary approval, or a real
  learner's knowledge.
- [x] Suppression changes presentation only; it does not delete source evidence,
  dictionary records, approved meanings/readings, grammar evidence, or state.
- [x] The unavailable expression reading remains a deliberate no-op with the
  nonfatal reason `missing-approved-reading`; no reading is invented.

## Review record

- Date: 2026-08-22
- Commit: `c2a8ea135ea45bc025a88f022399d96219d1859c`
- Reviewer: Ravindu
- Calibre version: 8.14
- Fixture: `artifacts/phase8/epub/run-a.epub`
- Machine verification: PASS — deterministic archive/report identity, checksum,
  EPUB structure, XHTML safety, assistance counts, links, suppression,
  publisher preservation, safe fallbacks, privacy, and compatibility passed.
- Manual review: PASS — import, TOC, layout, generated reading, displayed and
  suppressed meanings, study/grammar navigation, overlap boundaries, density
  suppression, publisher ruby, and final visual checks were approved.
- Result: PASS
- Notes:
  - The compact proper-name note intentionally displays only `前`; its
    `adaptive-name-note` classification is structural and its synthetic
    translation is density-suppressed.
  - `また読んでいる` is intentionally nonclickable because its grammar
    assistance is density-suppressed.
  - The single `missing-approved-reading` diagnostic for
    `study-item-0002-occ-0001` is intentional; no reading is invented.
  - The fixture uses synthetic readings, meanings, profiles, presets,
    exposures, overrides, density policies, and grammar mechanics. It does not
    establish pedagogical validity, JLPT placement accuracy, production
    dictionary approval, optimal assistance density, or knowledge about a real
    learner.
  - Suppression affects learner-facing presentation only and deletes no
    dictionary records, approved meanings, readings, grammar evidence, source
    evidence, or learner-state records.
  - Artifact-based evidence showed no provider, SDK, network, model judgment,
    dictionary-source change, original-XHTML mutation, source-EPUB mutation, or
    production packaging activity.
