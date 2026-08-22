# Phase 8 adaptive-density review

Use the retained artifacts under `artifacts/phase8/density/`. The policies are synthetic deterministic mechanics fixtures, not pedagogical recommendations.

## Machine verification

- [x] Run-A, run-B, and `per-occurrence-assistance-plan-v1.json` are byte-identical.
- [x] Canonical chapter character counts are 67 and 18, excluding publisher `rt`/`rp` and markup.
- [x] Budgets use integer numerators, denominator 1,000, ceiling rounding, and explicit minimum/maximum bounds.
- [x] All 12 source occurrences are retained once in canonical order.
- [x] Reading, meaning, and grammar budgets are independent.
- [x] N5 selects at least as much assistance as N4, and N4 at least as much as N3.
- [x] Hidden input states and explicit hide overrides remain suppressed.
- [x] Explicit show overrides outrank exhausted budgets with hashed over-budget evidence.
- [x] Density exclusions are explicit and hashed.
- [x] Repeated `〜ている` occurrences remain distinct with deterministic first-occurrence preference.
- [x] Publisher ruby is preserved and does not consume generated-reading density.
- [x] Publisher-adjacent grammar remains protected.
- [x] Grammar reference-only and partial-overlap-rejected dispositions are not promoted.
- [x] Vocabulary, JMdict expressions, JMnedict names, and grammar remain separate.
- [x] Disabled and failure reports contain no partial plans or chapter summaries.
- [x] Fallback annotation and grammar plans are byte-identical to their inputs.
- [x] Phase 3, Phase 5, Phase 7, and Phase 8 compatibility artifacts are unchanged.
- [x] The approved Phase 7 EPUB checksum remains `df4c4bf0f072c01ac0a8d8aff316ee92613760c1822274cecd7ec9ce409a9619`.
- [x] No XHTML, EPUB, provider, model, cache, credential, path, or complete-book data appears.

## Manual review

1. Compare N5, N4, and N3 targets, character counts, and integer budgets. Confirm that differences are explicit, monotonic, and synthetic.
2. Review selected and density-excluded actions. Confirm independent reading, meaning, and grammar decisions.
3. Review explicit reading/meaning hide cases and the grammar show-over-budget case. Confirm dimension-local override behavior.
4. Review all three `〜ている` occurrences. Confirm repetition remains auditable and publisher adjacency protected.
5. Review the publisher-ruby vocabulary occurrence. Confirm publisher content is preserved outside generated-reading density.
6. Review grammar reference-only and partial-overlap-rejected occurrences. Confirm density does not override overlap policy.
7. Review disabled and failure artifacts. Confirm safe diagnostics and byte-identical fallback.

## Result

- Date: 2026-08-22
- Commit: `02927b256c49483853d8c5e7ed49b4234f59c1e4`
- Reviewer: Ravindu
- Machine verification: PASS — deterministic identities, 115 nested hashes, source slices, integer budgets, occurrence ordering, diagnostics, compatibility, and the Phase 7 EPUB checksum were verified.
- Manual review: PASS — policy clarity, independent dimensions, overrides, repetition, publisher protection, overlap boundaries, safe failure, and compatibility were approved.
- Result: PASS
- Notes: N5/N4/N3 targets are synthetic mechanics fixtures, not pedagogical recommendations or validated JLPT defaults. Exposure is explicit local input, not inferred telemetry. Suppression is presentation planning and deletes no knowledge records. Item-level publisher rationale may be inherited while occurrence-specific fields remain authoritative. Unknown-occurrence, publisher-conflict, and grammar-conflict fallback identity is covered by the completed regression gate rather than separate allowed review artifacts. The reviewed artifacts evidence no provider, SDK, network, model judgment, dictionary-source change, XHTML/link mutation, EPUB packaging, or Calibre activity.
