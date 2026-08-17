# Phase 6 context-index and retrieval review

Review record: PASS on 2026-08-17 at commit `2db81c4`, reviewed by Ravindu.

Use these files:

- artifacts/phase6/run-a/context-index.json
- artifacts/phase6/run-a/retrieval.json
- tests/phase6_golden/retrieval-review-cases-v1.json

Machine checks:

- [x] Index schema v1 records canonical schema v2, vocabulary schema v4, and enriched-plan schema v2.
- [x] Run-A, run-B, and checked-in index JSON are byte-identical.
- [x] Run-A, run-B, and checked-in retrieval JSON are byte-identical.
- [x] Thirteen sentence records preserve canonical chapter, block, and sentence order.
- [x] Five study items and six ordered occurrences retain exact source references and offsets.
- [x] Tokenizer, JMdict, JMnedict, publisher-ruby, dictionary, and enrichment provenance is preserved.
- [x] Source-input, query, and result hashes are stable and valid.
- [x] Default retrieval contains the target plus at most one adjacent sentence per side.
- [x] Default retrieval stays inside the containing block.
- [x] Same-chapter mode may cross blocks but never chapters.
- [x] Sentence and character budgets retain whole sentences only.
- [x] No retrieval result contains the complete book.
- [x] Publisher readings outrank user, dictionary, book-context, and model evidence.
- [x] JMdict vocabulary/expressions and JMnedict names remain separate.
- [x] Disabled and failure fallback plans are byte-identical to the approved Phase 5 plan.
- [x] Diagnostics contain stable safe reason codes and no raw context, paths, credentials, or exceptions.

Manual trace:

- [x] 良い天気だ resolves to its exact containing sentence as a JMdict expression.
- [x] 言葉 resolves to its exact containing sentence without crossing its block.
- [x] Both 表舞台 occurrences retain reading おもてぶたい and resolve independently.
- [x] 雪乃 remains a JMnedict proper name with publisher reading ゆきの.
- [x] 振り返っ retains lemma/dictionary references and its exact containing sentence.
- [x] The reviewed block-boundary sentence is excluded in default mode.
- [x] The reviewed chapter-boundary chapter is always excluded.

Approval:

- Reviewer: Ravindu
- Date: 2026-08-17
- Commit: `2db81c4`
- Result: PASS
- Notes: Machine verification confirmed deterministic index/retrieval bytes,
  canonical references and offsets, bounded context, provenance precedence,
  privacy, and byte-identical Phase 5 fallback. Manual review approved all five
  item contexts, both publisher-ruby occurrences, conservative boundaries, and
  reversibility. Explicit same-chapter retrieval behavior is covered by the
  completed regression gate rather than a retained reviewed artifact.
