# Phase 6 recurring-term and entity-evidence review

Review record: PASS on 2026-08-18 at commit `ee7d0b9`, reviewed by Ravindu.

Review:

- artifacts/phase6/evidence/run-a/evidence.json
- artifacts/phase6/evidence/run-b/evidence.json
- artifacts/phase6/evidence/minimum-one/evidence.json
- tests/phase6_golden/evidence-v1.json
- tests/phase6_golden/evidence-review-cases-v1.json

Machine checks:

- [x] Evidence schema v1 records context-index v1, vocabulary v4, and enriched-plan v2.
- [x] Run-A, run-B, and checked-in evidence JSON are byte-identical.
- [x] Exactly five groups contain six globally ordered occurrences.
- [x] Stable group, occurrence, diagnostic, source, and evidence hashes validate.
- [x] Source items, records, tokens, candidates, expressions, names, ruby, entries, senses, translations, and offsets resolve exactly.
- [x] First/last locations and ordered chapter counts match occurrences.
- [x] JMdict vocabulary, JMdict expressions, and JMnedict names remain separate.
- [x] Publisher readings remain authoritative and different readings cannot merge.
- [x] Default threshold 2 makes only 表舞台 eligible.
- [x] Threshold 1 makes all five groups eligible without recurrence diagnostics.
- [x] Default output has four ordered insufficient-recurrence diagnostics.
- [x] No preferred terminology, translation choice, entity resolution, summary, or model-authored field exists.
- [x] Evidence records reference canonical sentence records without copying context text.
- [x] Disabled and failure plans are byte-identical to the approved Phase 5 plan.
- [x] Safe diagnostics contain no raw context, paths, credentials, caches, or exceptions.

Manual review:

- [x] 良い天気だ is one normalized JMdict expression group.
- [x] 言葉 and 振り返っ are separate JMdict lemma groups.
- [x] Both 表舞台 occurrences form one publisher-ruby vocabulary group.
- [x] Both 表舞台 ruby IDs and authoritative reading おもてぶたい are preserved.
- [x] 雪乃 remains publisher-backed JMnedict name evidence with reading ゆきの.
- [x] First-seen group and occurrence ordering matches canonical book order.
- [x] Eligibility expresses recurrence evidence only and does not choose terminology.

Approval:

- Reviewer: Ravindu
- Date: 2026-08-18
- Commit: `ee7d0b9`
- Result: PASS
- Notes: Machine verification confirmed deterministic bytes, IDs, hashes,
  references, offsets, provenance, thresholds, privacy, and byte-identical
  fallback. Manual review approved lexical/name separation, both 表舞台
  occurrences, publisher readings, first-seen ordering, chapter counts,
  threshold behavior, and reversibility. Eligibility is recurrence evidence
  only and does not itself choose terminology.
