# Phase 8 adaptive-rendering review checklist

Review the checked-in synthetic rendering fixture only. Suppression is presentation-only; it does not delete source or dictionary evidence. The fixture is not a learner assessment or pedagogical recommendation.

## Machine verification

- [x] Run-A, run-B, and checked-in XHTML/report outputs are byte-identical.
- [x] All four XHTML files parse with the XHTML namespace and Japanese language metadata.
- [x] Exactly 12 occurrence results appear in canonical source order with stable IDs and hashes.
- [x] Reading-presented, reading-suppressed, and reading-unavailable behavior matches the density plan.
- [x] Meaning-presented, input-suppressed, density-suppressed, and override-suppressed behavior matches the density plan.
- [x] Grammar presented, suppressed, reference-only, partial-overlap-rejected, and publisher-protected behavior matches the validated dispositions.
- [x] Existing vocabulary, expression, name, and retained grammar links and backlinks resolve without nesting.
- [x] Suppressed assistance is absent from text, attributes, comments, metadata, and CSS.
- [x] Visible canonical source text, emphasis, and publisher ruby remain unchanged.
- [x] Disabled and failed modes reproduce the linked input byte-for-byte with deterministic diagnostics.
- [x] Phase 3, Phase 5, Phase 7, assistance-selection, and density artifacts remain unchanged.

## Manual review

- [x] Confirm 前 displays the synthetic approved reading まえ without changing its name classification.
- [x] Confirm 読ん shows only the approved meaning “to read”; suppressed meanings are absent.
- [x] Confirm the explicit grammar override retains 〜たことがある and its navigation.
- [x] Confirm the shared 〜ている behavior distinguishes reference-only, density suppression, and publisher protection.
- [x] Confirm 表舞台【おもてぶたい】 is structurally and visibly unchanged.
- [x] Confirm vocabulary/expression/name notes remain distinct from grammar notes.
- [x] Confirm the output is readable and contains no hidden assistance or unexpected metadata.

## Review record

- Date: 2026-08-22
- Commit: `51783374e14957f53fbd450f608cbc8d25fb04a7`
- Reviewer: Ravindu
- Machine verification: PASS — deterministic report/XHTML identity, exact 12-result mapping, safe links, genuine suppression, publisher preservation, fallbacks, privacy, and prior-phase compatibility were verified directly.
- Manual review: PASS — reading, meaning, grammar, repetition, overlap, publisher-ruby, evidence-kind separation, safe-failure, and compatibility cases were approved.
- Result: PASS
- Notes:
  - The fixture uses synthetic approved readings, meanings, profiles, exposure, overrides, and density mechanics; it does not establish pedagogical validity, JLPT placement accuracy, production dictionary approval, or knowledge about a real learner.
  - Suppressed assistance is omitted presentation only and does not delete dictionary records, approved meanings, readings, grammar evidence, or learner-state records.
  - The successful report intentionally contains one nonfatal `missing-approved-reading` diagnostic for `study-item-0002-occ-0001`; no reading is invented.
  - Density suppression reduces learner-facing grammar contexts while preserving all 12 source occurrences in the rendering report.
  - Artifact-based evidence showed no provider, SDK, network, model judgment, dictionary-source change, original-XHTML mutation, EPUB packaging, navigation/OPF mutation, or Calibre activity during adaptive rendering.
