# Phase 6 editable context-manifest integration review

Review record: PENDING

Machine checks:

- [ ] Run-A, run-B, and golden manifests are byte-identical.
- [ ] Two ordered chapter records contain references, counts, provenance, and no chapter text.
- [ ] Four JMdict term/expression records remain separate from one JMnedict proper-name record.
- [ ] Publisher readings おもてぶたい and ゆきの remain authoritative.
- [ ] Protected source, dictionary, occurrence, reading, and provenance fields cannot be edited.
- [ ] Every accepted edit is explicit, user-provenanced, reviewer/date stamped, and hash-valid.
- [ ] Synthetic 表舞台 edit exports and rebuilds as “public arena”.
- [ ] Synthetic chapter-2 edit exports and rebuilds its approved summary.
- [ ] All synthetic fixtures state that they are not real user approvals.
- [ ] Five request augmentations contain only directly matching lexical/name context.
- [ ] Target-only retrieval excludes previous summaries; optional previous retrieval never includes following chapters.
- [ ] Phase 5 sentence context, request bytes, plan bytes, prompts, and cache keys remain unchanged.
- [ ] Disabled, stale, invalid, and corrupt fallback artifacts preserve Phase 5 bytes.
- [ ] No complete chapter/book text, credentials, paths, caches, provider data, XHTML, or EPUB data appears.

Manual review:

- [ ] The manifest is understandable and its editable fields are narrowly scoped.
- [ ] The 表舞台 edit is traceable without changing its publisher reading or occurrences.
- [ ] 雪乃 remains a proper name with publisher reading ゆきの.
- [ ] The chapter-2 synthetic summary is clearly fixture data and grounded in supplied references.
- [ ] Per-item augmentation is relevant, bounded, and contains no unrelated records.
- [ ] Disabled and failure behavior demonstrates Phase 5 reversibility.

Approval:

- Reviewer:
- Date:
- Commit:
- Result:
- Notes:
