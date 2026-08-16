# Phase 3 JMdict Expression Report Review

Use only the legal EPUB, synthetic expression dictionary, generated schema v3
reports, and checked-in reviewed expectations.

1. Run `./scripts/phase3-regression.sh`.
2. Confirm `artifacts/phase3/jmdict/expressions/run-a/vocabulary.json` has
   schema version 3, 82 tokens, 60 candidates, 4 single-token matches, and one
   selected expression.
3. Compare dictionary identity, version, index format, and SHA-256 with
   `tests/phase3_golden/expression-review-cases-v3.json`.
4. Trace `良い天気だ` to normalized form `良い天気`, its three ordered token
   and candidate IDs, exact offsets, entry 1008, sense 1, and `fine weather`.
5. Review the focused cases for longest-match `気がする`, inflected
   `気がした`, `仕方がない`, restrictions, no-match behavior, and every
   prohibited boundary.
6. Confirm schema-v1 and schema-v2 reports still match their historical
   goldens.
7. Confirm these schema-v3 files are byte-identical:
   - `artifacts/phase3/jmdict/expressions/run-a/vocabulary.json`
   - `artifacts/phase3/jmdict/expressions/run-b/vocabulary.json`
   - `tests/phase3_golden/vocabulary-jmdict-expressions-v3.json`

Known limitation: expression lookup considers at most eight adjacent Japanese
candidate tokens and applies deterministic longest-match selection. It does not
rank senses or search across punctuation, whitespace, Latin text, sentence
boundaries, or publisher ruby.

- Date: 2026-08-16
- Commit: `e516afd`
- Reviewer: Ravindu
- Result: Pass
- Notes: Schema, provenance, counts, IDs, ordering, references, offsets,
  restrictions, boundary exclusions, and byte identity passed direct checks.
  The reviewer confirmed `良い天気だ` → `良い天気`, reading
  `よいてんき`, and gloss `fine weather`.
