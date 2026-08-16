# Phase 3 vocabulary report review checklist

Generate the legal fixture report and retained artifacts with:

```bash
./scripts/phase3-regression.sh
```

Inspect `artifacts/phase3/run-a/vocabulary.json` and compare representative
records with `tests/phase3_golden/review-cases-v1.json`.

- [ ] Report schema is v1 and source canonical book schema is v2.
- [ ] Tokenizer provenance is MeCab 1.0.12, furigana 0.5, dictionary version 102.
- [ ] Report contains 82 tokens and 60 candidates in deterministic order.
- [ ] `言葉` is a noun candidate with reading `コトバ`.
- [ ] `振り返っ` has lemma `振り返る` and exact sentence/block offsets.
- [ ] Publisher `表舞台【おもてぶたい】` remains one authoritative candidate.
- [ ] Malformed publisher ruby `未知` remains one candidate with no reading.
- [ ] `English` and punctuation are tokens but not candidates.
- [ ] IPADIC splits `成功体験` into `成功` and `体験` as documented.
- [ ] Run-A, run-B, and the checked-in full golden report are byte-identical.

## Result

- Date:
- Commit:
- Reviewer:
- Review result: pass / fail
- Notes:
