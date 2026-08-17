# Phase 5 enriched rendering review checklist

- [x] Schema-v2 standalone notes match run-A, run-B, and the golden.
- [x] Linked run-A/run-B trees match all three schema-v2 XHTML goldens.
- [x] Packaged run-A/run-B EPUBs are byte-identical and structurally valid.
- [x] Five notes show only the approved active meanings.
- [x] Six contexts, forward links, backlinks, and source anchors still resolve.
- [x] 表舞台 and 雪乃 publisher ruby, including rt/rp, is unchanged.
- [x] Source text, emphasis, links, image/CSS, navigation, spine, and resources survive.
- [x] Provider, model, cache, prompt, context-hash, and audit metadata is absent.
- [x] Schema-v1 and disabled/failure rendering remains byte-identical to Phase 4.
- [x] No rendering path invokes a provider, SDK, credential, or network service.

Review record: PASS on 2026-08-17 at commit `33cdd9a`, reviewed by Ravindu
with Calibre 8.14 using `artifacts/phase5/rendered/run-a.epub`.

Machine verification passed run/golden identity, EPUB SHA-256, archive,
manifest, spine, navigation, resources, XHTML, internal links, approved active
meanings, metadata exclusion, publisher-ruby preservation, and byte-identical
schema-v1 fallback. Calibre review passed TOC order 第一章 → 第二章 → Study
Notes, reading order, chapter text/layout, emphasized 言葉, lantern image/CSS,
existing navigation, all five note links/contexts/backlinks, both 表舞台
occurrences, 雪乃 proper-name ruby, and 振り返る. No broken links, nested
ruby, duplicated text, missing resources, superseded meanings, or unexpected
layout changes were observed. Reader-visible occurrence count, dictionary
dataset, entry, and sense provenance fields were expected and accepted.
