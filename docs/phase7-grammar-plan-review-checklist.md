# Phase 7 grammar-plan and overlap review checklist

Review `artifacts/phase7/grammar-plan/run-a/plan.json` against
`tests/phase7_golden/grammar-plan-v1.json` and the reviewed cases.

## Machine checks

- [ ] Run A, run B, and the checked-in golden are byte-identical.
- [ ] Five primary grammar items contain seven ordered occurrences.
- [ ] Repeated `〜ている` is one item with three source occurrences.
- [ ] Synthetic `〜て` is excluded by default and test-only inclusion is explicit.
- [ ] Per-chapter limits use deterministic first-seen ordering.
- [ ] IDs, anchors, hashes, references, offsets, and source slices validate.
- [ ] Contains, exact, partial, non-overlap, and publisher-ruby cases are recorded.
- [ ] Existing vocabulary links are always preserved.
- [ ] Unsafe partial overlap rejects only the grammar link.
- [ ] Publisher ruby is never split, replaced, or entered.
- [ ] Vocabulary, expressions, names, and grammar remain separate.
- [ ] Phase 3 vocabulary and Phase 5 annotation-plan bytes remain unchanged.
- [ ] Disabled, stale, invalid, and corrupt fallbacks reproduce Phase 5 bytes.
- [ ] Reports contain no sensitive, rendering, XHTML, or EPUB data.

## Manual review

- [ ] Primary grammar selection is conservative and understandable.
- [ ] Synthetic mechanics-rule exclusion is prominent.
- [ ] Repeated occurrences and chapter limits are transparent.
- [ ] Vocabulary-link precedence is appropriate for every overlap class.
- [ ] Publisher-ruby precedence is unambiguous.
- [ ] This plan makes no rendering claim or production-rule approval.

## Review record

- Reviewer:
- Date:
- Commit:
- Result: PENDING
- Notes:
