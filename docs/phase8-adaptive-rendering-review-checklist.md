# Phase 8 adaptive-rendering review checklist

Review the checked-in synthetic rendering fixture only. Suppression is presentation-only; it does not delete source or dictionary evidence. The fixture is not a learner assessment or pedagogical recommendation.

## Machine verification

- [ ] Run-A, run-B, and checked-in XHTML/report outputs are byte-identical.
- [ ] All four XHTML files parse with the XHTML namespace and Japanese language metadata.
- [ ] Exactly 12 occurrence results appear in canonical source order with stable IDs and hashes.
- [ ] Reading-presented, reading-suppressed, and reading-unavailable behavior matches the density plan.
- [ ] Meaning-presented, input-suppressed, density-suppressed, and override-suppressed behavior matches the density plan.
- [ ] Grammar presented, suppressed, reference-only, partial-overlap-rejected, and publisher-protected behavior matches the validated dispositions.
- [ ] Existing vocabulary, expression, name, and retained grammar links and backlinks resolve without nesting.
- [ ] Suppressed assistance is absent from text, attributes, comments, metadata, and CSS.
- [ ] Visible canonical source text, emphasis, and publisher ruby remain unchanged.
- [ ] Disabled and failed modes reproduce the linked input byte-for-byte with deterministic diagnostics.
- [ ] Phase 3, Phase 5, Phase 7, assistance-selection, and density artifacts remain unchanged.

## Manual review

- [ ] Confirm 前 displays the synthetic approved reading まえ without changing its name classification.
- [ ] Confirm 読ん shows only the approved meaning “to read”; suppressed meanings are absent.
- [ ] Confirm the explicit grammar override retains 〜たことがある and its navigation.
- [ ] Confirm the shared 〜ている behavior distinguishes reference-only, density suppression, and publisher protection.
- [ ] Confirm 表舞台【おもてぶたい】 is structurally and visibly unchanged.
- [ ] Confirm vocabulary/expression/name notes remain distinct from grammar notes.
- [ ] Confirm the output is readable and contains no hidden assistance or unexpected metadata.

## Review record

- Date:
- Commit:
- Reviewer:
- Machine verification:
- Manual review:
- Result:
- Notes:
