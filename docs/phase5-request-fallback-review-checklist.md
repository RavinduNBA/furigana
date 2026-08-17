# Phase 5 request and fallback review checklist

- [x] Five stable requests contain only bounded same-block context.
- [x] Context text excludes publisher rt/rp readings and complete-book text.
- [x] JMdict vocabulary/expressions and JMnedict names remain separate.
- [x] Publisher readings and dictionary provenance outrank model output.
- [x] Scripted selections reference only supplied entries and senses/translations.
- [x] Independent scripted runs are byte-identical; the second identical run is a cache hit.
- [x] Invalid, unavailable, timed-out, and corrupt-cache paths retain dictionary meanings.
- [x] Disabled output preserves the Phase 4 annotation plan byte-for-byte.
- [x] Artifacts and diagnostics contain no credentials, markup, URLs, or unrelated context.

Review record: PASS on 2026-08-17 at commit `6a3b40f`, reviewed by Ravindu.
Machine verification passed. Editorial review approved 良い天気だ “pleasant
weather”, 表舞台 “public stage”, and 雪乃 “Yukino (female given name)”. It
also approved the corrected meanings 言葉 “word” and 振り返る “to turn
around”. Dictionary-only fallback and provenance precedence remained intact.
