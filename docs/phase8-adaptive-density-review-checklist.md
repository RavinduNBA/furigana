# Phase 8 adaptive-density review

Use the retained artifacts under `artifacts/phase8/density/`. The policies are synthetic deterministic mechanics fixtures, not pedagogical recommendations.

## Machine verification

- [ ] Run-A, run-B, and `per-occurrence-assistance-plan-v1.json` are byte-identical.
- [ ] Canonical chapter character counts are 67 and 18, excluding publisher `rt`/`rp` and markup.
- [ ] Budgets use integer numerators, denominator 1,000, ceiling rounding, and explicit minimum/maximum bounds.
- [ ] All 12 source occurrences are retained once in canonical order.
- [ ] Reading, meaning, and grammar budgets are independent.
- [ ] N5 selects at least as much assistance as N4, and N4 at least as much as N3.
- [ ] Hidden input states and explicit hide overrides remain suppressed.
- [ ] Explicit show overrides outrank exhausted budgets with hashed over-budget evidence.
- [ ] Density exclusions are explicit and hashed.
- [ ] Repeated `〜ている` occurrences remain distinct with deterministic first-occurrence preference.
- [ ] Publisher ruby is preserved and does not consume generated-reading density.
- [ ] Publisher-adjacent grammar remains protected.
- [ ] Grammar reference-only and partial-overlap-rejected dispositions are not promoted.
- [ ] Vocabulary, JMdict expressions, JMnedict names, and grammar remain separate.
- [ ] Disabled and failure reports contain no partial plans or chapter summaries.
- [ ] Fallback annotation and grammar plans are byte-identical to their inputs.
- [ ] Phase 3, Phase 5, Phase 7, and Phase 8 compatibility artifacts are unchanged.
- [ ] The approved Phase 7 EPUB checksum remains `df4c4bf0f072c01ac0a8d8aff316ee92613760c1822274cecd7ec9ce409a9619`.
- [ ] No XHTML, EPUB, provider, model, cache, credential, path, or complete-book data appears.

## Manual review

1. Compare N5, N4, and N3 targets, character counts, and integer budgets. Confirm that differences are explicit, monotonic, and synthetic.
2. Review selected and density-excluded actions. Confirm independent reading, meaning, and grammar decisions.
3. Review explicit reading/meaning hide cases and the grammar show-over-budget case. Confirm dimension-local override behavior.
4. Review all three `〜ている` occurrences. Confirm repetition remains auditable and publisher adjacency protected.
5. Review the publisher-ruby vocabulary occurrence. Confirm publisher content is preserved outside generated-reading density.
6. Review grammar reference-only and partial-overlap-rejected occurrences. Confirm density does not override overlap policy.
7. Review disabled and failure artifacts. Confirm safe diagnostics and byte-identical fallback.

## Result

- Date:
- Commit:
- Reviewer:
- Machine verification:
- Manual review:
- Result: PENDING
- Notes:
