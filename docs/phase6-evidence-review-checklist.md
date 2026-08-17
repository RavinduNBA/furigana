# Phase 6 recurring-term and entity-evidence review

Review record: PENDING

Review:

- artifacts/phase6/evidence/run-a/evidence.json
- artifacts/phase6/evidence/run-b/evidence.json
- artifacts/phase6/evidence/minimum-one/evidence.json
- tests/phase6_golden/evidence-v1.json
- tests/phase6_golden/evidence-review-cases-v1.json

Machine checks:

- [ ] Evidence schema v1 records context-index v1, vocabulary v4, and enriched-plan v2.
- [ ] Run-A, run-B, and checked-in evidence JSON are byte-identical.
- [ ] Exactly five groups contain six globally ordered occurrences.
- [ ] Stable group, occurrence, diagnostic, source, and evidence hashes validate.
- [ ] Source items, records, tokens, candidates, expressions, names, ruby, entries, senses, translations, and offsets resolve exactly.
- [ ] First/last locations and ordered chapter counts match occurrences.
- [ ] JMdict vocabulary, JMdict expressions, and JMnedict names remain separate.
- [ ] Publisher readings remain authoritative and different readings cannot merge.
- [ ] Default threshold 2 makes only 表舞台 eligible.
- [ ] Threshold 1 makes all five groups eligible without recurrence diagnostics.
- [ ] Default output has four ordered insufficient-recurrence diagnostics.
- [ ] No preferred terminology, translation choice, entity resolution, summary, or model-authored field exists.
- [ ] Evidence records reference canonical sentence records without copying context text.
- [ ] Disabled and failure plans are byte-identical to the approved Phase 5 plan.
- [ ] Safe diagnostics contain no raw context, paths, credentials, caches, or exceptions.

Manual review:

- [ ] 良い天気だ is one normalized JMdict expression group.
- [ ] 言葉 and 振り返っ are separate JMdict lemma groups.
- [ ] Both 表舞台 occurrences form one publisher-ruby vocabulary group.
- [ ] Both 表舞台 ruby IDs and authoritative reading おもてぶたい are preserved.
- [ ] 雪乃 remains publisher-backed JMnedict name evidence with reading ゆきの.
- [ ] First-seen group and occurrence ordering matches canonical book order.
- [ ] Eligibility expresses recurrence evidence only and does not choose terminology.

Approval:

- Reviewer:
- Date:
- Commit:
- Result:
- Notes:
