# Phase 4 annotation-plan review checklist

Review `artifacts/phase4/run-a/annotation-plan.json` against `tests/phase4_golden/review-cases-v1.json`.

- [ ] Schema is v1 and source vocabulary schema is v4.
- [ ] Tokenizer, JMdict, and JMnedict provenance exactly matches the source report.
- [ ] Counts are 5 items, 6 occurrences, and 52 diagnostics.
- [ ] IDs, source order, references, offsets, and anchors are stable and unique.
- [ ] 言葉 and inflected 振り返っ → 振り返る use dictionary-only meanings.
- [ ] 良い天気だ is an expression normalized to 良い天気.
- [ ] 雪乃 remains a proper name with a JMnedict translation.
- [ ] Both 表舞台 occurrences preserve publisher reading おもてぶたい and target the existing ruby.
- [ ] Unmatched and incompatible candidates are excluded with concise diagnostics.
- [ ] Run-A, run-B, and the checked-in golden plan are byte-identical.

## Review record

- Date: 2026-08-17
- Commit reviewed: `9d49edadddefd019230bd40b616856bde0c7c0c4`
- Reviewer: Ravindu
- Result: PASS
- Notes: Machine checks confirmed schema/provenance, 5 items, 6 occurrences,
  52 diagnostics, deterministic IDs/order, exact source references and offsets,
  publisher-ruby protection, limits, non-overlap, and byte-identical run-A,
  run-B, and golden output. The reviewer approved all five dictionary-only
  display meanings.
