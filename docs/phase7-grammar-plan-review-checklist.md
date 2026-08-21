# Phase 7 grammar-plan and overlap review checklist

Review `artifacts/phase7/grammar-plan/run-a/plan.json` against
`tests/phase7_golden/grammar-plan-v1.json` and the reviewed cases.

## Machine checks

- [x] Run A, run B, and the checked-in golden are byte-identical.
- [x] Five primary grammar items contain seven ordered occurrences.
- [x] Repeated `〜ている` is one item with three source occurrences.
- [x] Synthetic `〜て` is excluded by default and test-only inclusion is explicit.
- [x] Per-chapter limits use deterministic first-seen ordering.
- [x] IDs, anchors, hashes, references, offsets, and source slices validate.
- [x] Contains, exact, partial, non-overlap, and publisher-ruby cases are recorded.
- [x] Existing vocabulary links are always preserved.
- [x] Unsafe partial overlap rejects only the grammar link.
- [x] Publisher ruby is never split, replaced, or entered.
- [x] Vocabulary, expressions, names, and grammar remain separate.
- [x] Phase 3 vocabulary and Phase 5 annotation-plan bytes remain unchanged.
- [x] Disabled, stale, invalid, and corrupt fallbacks reproduce Phase 5 bytes.
- [x] Reports contain no sensitive, rendering, XHTML, or EPUB data.

## Manual review

- [x] Primary grammar selection is conservative and understandable.
- [x] Synthetic mechanics-rule exclusion is prominent.
- [x] Repeated occurrences and chapter limits are transparent.
- [x] Vocabulary-link precedence is appropriate for every overlap class.
- [x] Publisher-ruby precedence is unambiguous.
- [x] This plan makes no rendering claim or production-rule approval.

## Review record

- Reviewer: Ravindu
- Date: 2026-08-20
- Commit: `c42b6befc8942bf90308c8c1b175abcf8b93549e`
- Result: PASS
- Notes: Machine verification confirmed deterministic serialization, stable
  references and anchors, conservative overlap dispositions, publisher-ruby
  precedence, and byte-identical Phase 3/5 compatibility and fallback outputs.
  Manual review approved default selection, repeated-occurrence handling,
  chapter limits, overlap policy, layer separation, and safe reversibility.
  The standalone `〜て` rule remains a synthetic mechanics fixture and is not
  approved as a production-quality grammar classification. Overlap dispositions
  remain planning decisions only and do not authorize nested or competing XHTML links.
