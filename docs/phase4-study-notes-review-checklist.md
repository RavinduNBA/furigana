# Phase 4 study-note XHTML review checklist

Review `artifacts/phase4/notes/run-a/study-notes.xhtml` against
`tests/phase4_golden/study-notes-review-cases-v1.json`.

- [ ] The document is readable XHTML titled “Study Notes” with five notes.
- [ ] Notes follow annotation-plan source order and use the expected stable anchors.
- [ ] Vocabulary, expression, and proper-name labels are visually distinct.
- [ ] 良い天気だ shows normalized form 良い天気 and meaning “fine weather”.
- [ ] 言葉 shows reading ことば and meaning “language”.
- [ ] 表舞台 shows authoritative reading おもてぶたい and two occurrences.
- [ ] 雪乃 is labeled “Proper name” and uses the JMnedict translation.
- [ ] 振り返っ shows lemma 振り返る and meaning “to turn around”.
- [ ] Dictionary provenance and selected entry/sense or translation references appear.
- [ ] CSS affects only `study-notes` and `study-note` classes.
- [ ] The document contains no links, backlinks, or ruby markup in this slice.
- [ ] Run-A, run-B, and the checked-in XHTML golden are byte-identical.

## Review record

- Date: 2026-08-17
- Commit reviewed: `58bf0c44e9b78732df2a6cab472a8b039c9cc974`
- Reviewer: Ravindu
- Result: PASS
- Notes: Machine checks confirmed valid deterministic XHTML, five ordered notes,
  exact plan mappings and dictionary references, scoped CSS, publisher-reading
  preservation, prohibited-element absence, and byte-identical run-A, run-B,
  and golden output. The reviewer visually approved readability, labels,
  meanings, and styling.
