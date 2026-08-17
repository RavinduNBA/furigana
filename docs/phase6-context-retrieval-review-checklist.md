# Phase 6 context-index and retrieval review

Review record: PENDING

Use these files:

- artifacts/phase6/run-a/context-index.json
- artifacts/phase6/run-a/retrieval.json
- tests/phase6_golden/retrieval-review-cases-v1.json

Machine checks:

- [ ] Index schema v1 records canonical schema v2, vocabulary schema v4, and enriched-plan schema v2.
- [ ] Run-A, run-B, and checked-in index JSON are byte-identical.
- [ ] Run-A, run-B, and checked-in retrieval JSON are byte-identical.
- [ ] Thirteen sentence records preserve canonical chapter, block, and sentence order.
- [ ] Five study items and six ordered occurrences retain exact source references and offsets.
- [ ] Tokenizer, JMdict, JMnedict, publisher-ruby, dictionary, and enrichment provenance is preserved.
- [ ] Source-input, query, and result hashes are stable and valid.
- [ ] Default retrieval contains the target plus at most one adjacent sentence per side.
- [ ] Default retrieval stays inside the containing block.
- [ ] Same-chapter mode may cross blocks but never chapters.
- [ ] Sentence and character budgets retain whole sentences only.
- [ ] No retrieval result contains the complete book.
- [ ] Publisher readings outrank user, dictionary, book-context, and model evidence.
- [ ] JMdict vocabulary/expressions and JMnedict names remain separate.
- [ ] Disabled and failure fallback plans are byte-identical to the approved Phase 5 plan.
- [ ] Diagnostics contain stable safe reason codes and no raw context, paths, credentials, or exceptions.

Manual trace:

- [ ] 良い天気だ resolves to its exact containing sentence as a JMdict expression.
- [ ] 言葉 resolves to its exact containing sentence without crossing its block.
- [ ] Both 表舞台 occurrences retain reading おもてぶたい and resolve independently.
- [ ] 雪乃 remains a JMnedict proper name with publisher reading ゆきの.
- [ ] 振り返っ retains lemma/dictionary references and its exact containing sentence.
- [ ] The reviewed block-boundary sentence is excluded in default mode.
- [ ] The reviewed chapter-boundary chapter is always excluded.

Approval:

- Reviewer:
- Date:
- Commit:
- Result:
- Notes:
