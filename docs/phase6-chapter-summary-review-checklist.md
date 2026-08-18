# Phase 6 chapter packets and explicit-summary review

Review record: PENDING

Review:

- artifacts/phase6/summaries/run-a/packets.json
- artifacts/phase6/summaries/run-a/summary.json
- artifacts/phase6/summaries/run-a/retrieval.json
- tests/fixtures/phase6-chapter-summary-registry-v1.json
- tests/phase6_golden/chapter-summary-review-cases-v1.json

Machine checks:

- [ ] Two packets preserve canonical chapter, sentence-record, item, occurrence, evidence, and terminology ordering.
- [ ] Packets contain references and counts but no complete chapter or book text.
- [ ] JMdict and JMnedict references remain separate and publisher readings remain authoritative.
- [ ] Run-A, run-B, and checked-in packet, report, and retrieval goldens are byte-identical.
- [ ] The registry is explicitly marked synthetic test-fixture data.
- [ ] Chapter 1 has one explicit approved synthetic summary containing approved terminology.
- [ ] Chapter 2 is deferred and has no effective summary.
- [ ] Rejected and missing decisions produce no effective summary.
- [ ] Retrieval by chapter, item, and occurrence returns only approved summaries.
- [ ] Previous-summary retrieval never includes a following chapter or crosses the book boundary.
- [ ] Count and character budgets retain complete summaries only.
- [ ] IDs, source hashes, packet/decision/result/query/retrieval hashes, and diagnostics validate.
- [ ] Disabled, stale, invalid, and corrupt fallbacks preserve the Phase 5 plan byte-for-byte.
- [ ] No provider, cache, prompt, XHTML, EPUB, credentials, paths, raw exceptions, or complete chapter text appears.

Manual review:

- [ ] Chapter 1 packet references are minimal, ordered, and sufficient for summary review.
- [ ] The synthetic chapter-1 summary is short and supported by its referenced evidence.
- [ ] “public stage” follows the explicit terminology decision and publisher reading remains unchanged.
- [ ] Chapter 2 deferral is clear and does not create summary text.
- [ ] Previous-only bounded retrieval is conservative and useful.
- [ ] Rejected, missing, disabled, and failure states are auditable and reversible.

Approval:

- Reviewer:
- Date:
- Commit:
- Result:
- Notes:
