# Phase 7 grammar-candidate review checklist

Review `artifacts/phase7/run-a/grammar.json` against the synthetic fixture and
`tests/phase7_golden/grammar-review-cases-v1.json`.

## Machine checks

- [x] Schema and curated dataset provenance are exact.
- [x] Run A, run B, and the checked-in golden are byte-identical.
- [x] Six grouped candidates contain eight canonically ordered occurrences.
- [x] IDs, source references, offsets, component tokens, counts, and hashes validate.
- [x] All five requested grammar forms are detected by exact curated rules.
- [x] Repeated `〜ている` occurrences remain distinct and ordered.
- [x] Longest-match selection rejects the shorter competing rule deterministically.
- [x] The lexical expression is not promoted to grammar.
- [x] Sentence/block/chapter boundaries are never crossed.
- [x] Publisher-ruby content is protected and `rt`/`rp` text is absent.
- [x] Vocabulary overlaps are references only; vocabulary records remain unchanged.
- [x] Disabled, invalid, and corrupt paths preserve the annotation plan byte-for-byte.
- [x] Diagnostics contain stable reason codes and no sensitive data.

## Manual review

- [x] The curated labels and explanations are concise and faithful.
- [x] The five grammar classifications are transparent and conservative.
- [x] The short competing form is retained only where no longer exact match exists.
- [x] Publisher-ruby and lexical-expression exclusions are appropriate.
- [x] Grammar remains visibly separate from vocabulary and names.

## Review record

- Reviewer: Ravindu
- Date: 2026-08-20
- Commit: 577a9a4
- Result: PASS
- Notes: Machine verification passed for deterministic identity, IDs, hashes,
  offsets, source slices, ordering, overlap resolution, exclusions, compatibility,
  privacy, and fallback identity. Manual review passed the five primary
  classifications, repeated `〜ている`, longest-match behavior, boundaries,
  lexical-expression separation, and publisher-ruby protection. The standalone
  `〜て` rule passes only as a synthetic mechanics fixture and is not approved
  as a production-quality grammar classification. The exact generated synthetic
  publisher-ruby ID and source anchor are covered by the completed regression
  gate because they are not serialized in the reviewed grammar report.
