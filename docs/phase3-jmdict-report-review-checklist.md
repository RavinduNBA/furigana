# Phase 3 JMdict-Enriched Report Review

Use only the synthetic fixture and generated artifacts. No production JMdict
data is required.

1. Run `./scripts/phase3-regression.sh`.
2. Confirm `artifacts/phase3/jmdict/run-a/vocabulary.json` has
   `schema_version: 2`, 82 tokens, 60 candidates, and 4 dictionary matches.
3. Compare its `dictionary` object with
   `tests/phase3_golden/jmdict-review-cases-v2.json`: dataset identity,
   version, index format, and SHA-256 must match exactly.
4. Review the four ordered report matches against `report_matches` in that
   reviewed-case file. Check candidate, match, entry, and sense IDs.
5. Review `lookup_cases` for exact noun, inflected lemma, kana-only,
   restrictions, POS rejection, no-match, and publisher-reading precedence.
6. Confirm every retained sense has at least one English gloss and that senses
   remain in source order.
7. Confirm these three files are byte-identical:
   - `artifacts/phase3/jmdict/run-a/vocabulary.json`
   - `artifacts/phase3/jmdict/run-b/vocabulary.json`
   - `tests/phase3_golden/vocabulary-jmdict-v2.json`

Record the review date, commit, reviewer, result, and concise notes below before
closing Phase 3.

- Date:
- Commit:
- Reviewer:
- Result:
- Notes:
