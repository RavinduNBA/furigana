# Phase 6 terminology-registry and consistency review

Review record: PENDING

Review:

- tests/fixtures/phase6-terminology-registry-v1.json
- artifacts/phase6/terminology/run-a/consistency.json
- artifacts/phase6/terminology/run-b/consistency.json
- artifacts/phase6/terminology/rejected/consistency.json
- tests/phase6_golden/terminology-consistency-v1.json
- tests/phase6_golden/terminology-review-cases-v1.json

Machine checks:

- [ ] Registry and report schemas are version 1 with exact source identities and hashes.
- [ ] Every decision is explicit, user-provenanced, reviewer/date stamped, and hash-valid.
- [ ] Run-A, run-B, and checked-in consistency JSON are byte-identical.
- [ ] Five results preserve evidence order, hashes, provenance, references, offsets, and chapter counts.
- [ ] Only approved decisions produce an effective user terminology term.
- [ ] 表舞台 applies public stage to both occurrences without changing publisher reading.
- [ ] 雪乃 remains a deferred publisher-backed JMnedict name with no effective term.
- [ ] 良い天気だ, 言葉, and 振り返っ remain single observations without automatic terms.
- [ ] Rejected decisions remain auditable and produce no effective term.
- [ ] Stale, unknown, duplicate, unsafe, mismatched, and unsupported decisions are rejected.
- [ ] Differences from Phase 5 meanings are diagnostics only and never mutate the plan.
- [ ] Result and decision IDs, ordering, hashes, and diagnostics validate.
- [ ] Disabled, stale, invalid, and failure fallback plans are byte-identical to Phase 5.
- [ ] No context text, credentials, paths, caches, exceptions, provider calls, or rendering data appears.

Manual review:

- [ ] 表舞台 decision clearly records explicit user approval and source evidence.
- [ ] Both 表舞台 occurrences retain distinct source and publisher-ruby references.
- [ ] 雪乃 deferred status remains clearly separate from vocabulary terminology.
- [ ] Undecided single-occurrence groups are not presented as approved terminology.
- [ ] Rejected and deferred statuses are auditable without effective terms.
- [ ] Registry precedence is publisher reading, user terminology, dictionary, context, model.
- [ ] Fallback demonstrates complete Phase 5 reversibility.

Approval:

- Reviewer:
- Date:
- Commit:
- Result:
- Notes:
