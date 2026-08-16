# Phase 3 vocabulary report review checklist

Generate the legal fixture report and retained artifacts with:

```bash
./scripts/phase3-regression.sh
```

Inspect `artifacts/phase3/run-a/vocabulary.json` and compare representative
records with `tests/phase3_golden/review-cases-v1.json`.

- [x] Report schema is v1 and source canonical book schema is v2.
- [x] Tokenizer provenance is MeCab 1.0.12, furigana 0.5, dictionary version 102.
- [x] Report contains 82 tokens and 60 candidates in deterministic order.
- [x] `言葉` is a noun candidate with reading `コトバ`.
- [x] `振り返っ` has lemma `振り返る` and exact sentence/block offsets.
- [x] Publisher `表舞台【おもてぶたい】` remains one authoritative candidate.
- [x] Malformed publisher ruby `未知` remains one candidate with no reading.
- [x] `English` and punctuation are tokens but not candidates.
- [x] IPADIC splits `成功体験` into `成功` and `体験` as documented.
- [x] Run-A, run-B, and the checked-in full golden report are byte-identical.

## Result

- Date: 2026-08-16
- Commit: `cc23b28`
- Reviewer: Ravindu
- Review result: pass
- Notes: Reviewer approved all six representative cases. Machine checks passed
  for schema, provenance, counts, ordering, IDs, offsets, exclusions, IPADIC
  segmentation, and byte identity. Report SHA-256:
  `06a3df9ea7e44aa92eac8d0ad20bc16f8349cf32f57df8ed6a1dcfef65be12c9`.
