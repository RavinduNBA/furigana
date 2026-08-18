# Phase 7 grammar-candidate review checklist

Review `artifacts/phase7/run-a/grammar.json` against the synthetic fixture and
`tests/phase7_golden/grammar-review-cases-v1.json`.

## Machine checks

- [ ] Schema and curated dataset provenance are exact.
- [ ] Run A, run B, and the checked-in golden are byte-identical.
- [ ] Six grouped candidates contain eight canonically ordered occurrences.
- [ ] IDs, source references, offsets, component tokens, counts, and hashes validate.
- [ ] All five requested grammar forms are detected by exact curated rules.
- [ ] Repeated `〜ている` occurrences remain distinct and ordered.
- [ ] Longest-match selection rejects the shorter competing rule deterministically.
- [ ] The lexical expression is not promoted to grammar.
- [ ] Sentence/block/chapter boundaries are never crossed.
- [ ] Publisher-ruby content is protected and `rt`/`rp` text is absent.
- [ ] Vocabulary overlaps are references only; vocabulary records remain unchanged.
- [ ] Disabled, invalid, and corrupt paths preserve the annotation plan byte-for-byte.
- [ ] Diagnostics contain stable reason codes and no sensitive data.

## Manual review

- [ ] The curated labels and explanations are concise and faithful.
- [ ] The five grammar classifications are transparent and conservative.
- [ ] The short competing form is retained only where no longer exact match exists.
- [ ] Publisher-ruby and lexical-expression exclusions are appropriate.
- [ ] Grammar remains visibly separate from vocabulary and names.

## Review record

- Reviewer:
- Date:
- Commit:
- Result: PENDING
- Notes:
