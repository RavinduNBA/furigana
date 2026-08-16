# Phase 3 JMnedict Name Report Review

Use only the legal EPUB, synthetic JMdict/JMnedict data, generated schema v4
reports, and checked-in reviewed expectations.

1. Run `./scripts/phase3-regression.sh`.
2. Confirm `artifacts/phase3/jmnedict/run-a/vocabulary.json` has schema
   version 4, 82 tokens, 60 candidates, 4 JMdict matches, one expression, one
   name occurrence, one name match, and four name diagnostics.
3. Compare `name_dictionary` with
   `tests/phase3_golden/jmnedict-review-cases-v4.json`: identity, version,
   index format, and SHA-256 must match exactly.
4. Trace publisher-ruby `雪乃【ゆきの】` through candidate, token, name,
   publisher-ruby, entry 2001, name types, offsets, and translations.
5. Review person, place, organization, kana-only, ambiguity, restrictions,
   ordinary-word rejection, no-match, and publisher-reading cases.
6. Confirm incompatible publisher readings are diagnostics rather than guessed
   names and that `言葉` is not promoted to a proper name.
7. Confirm schema-v1, schema-v2, and schema-v3 files remain byte-identical to
   their historical goldens.
8. Confirm these schema-v4 files are byte-identical:
   - `artifacts/phase3/jmnedict/run-a/vocabulary.json`
   - `artifacts/phase3/jmnedict/run-b/vocabulary.json`
   - `tests/phase3_golden/vocabulary-jmnedict-v4.json`

Known limitations: lookup is exact and local. It does not perform fuzzy name
matching, entity resolution, expression/name merging, transliteration, or
book-wide identity tracking. Ambiguous entries remain ordered candidates.

- Date: 2026-08-16
- Commit: `5e0c01d`
- Reviewer: Ravindu
- Result: Pass
- Notes: Schemas v1-v4, provenance, counts, deterministic IDs/order,
  publisher-ruby precedence, JMdict matches, expression matching, name
  restrictions, diagnostics, and byte identity passed direct checks. The
  reviewer confirmed `雪乃【ゆきの】`, its person/female-given-name types,
  and ordered `Yukino`/`Yuki-no` translations.
