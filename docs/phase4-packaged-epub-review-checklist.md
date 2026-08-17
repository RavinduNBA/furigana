# Phase 4 packaged EPUB and Calibre checklist

- [ ] run-A and run-B EPUB files are byte-identical and structurally valid.
- [ ] The TOC contains one visible “Study Notes” entry after chapter 2.
- [ ] Chapter reading order is unchanged and Study Notes follows chapter 2.
- [ ] 良い天気だ and 表舞台 open the correct notes and backlinks return exactly.
- [ ] Publisher ruby, emphasis, images, CSS, and existing chapter links render unchanged.
- [ ] Five notes, six contexts, six forward links, and six backlinks are present.
- [ ] Calibre version, navigation, layout, links, ruby, and notes are recorded.

## Review record

- Date: 2026-08-17
- Commit reviewed: `948e59dd4318527f57280c2ecf9c58ebcb365336`
- Reviewer: Ravindu
- Calibre: 8.14
- Fixture: `artifacts/phase4/epub/run-a.epub`
- Result: PASS
- Notes: TOC order 第一章 → 第二章 → Study Notes, reading order, chapter
  layout, emphasized 言葉, image/CSS, existing chapter links, and
  第一【ファースト】 navigation passed. Forward links, exact contexts, and
  backlinks passed for 良い天気だ, 言葉, both 表舞台 occurrences, 雪乃, and
  振り返っ. Publisher ruby remained intact; five notes were readable and
  correctly ordered. No broken links, nested ruby, duplicated text, missing
  resources, viewer errors, or unexpected layout changes were observed.
  Compact unlabeled reading/meaning/context fields were accepted. Unlinked
  words such as 彼女 are expected with the tiny synthetic dictionary.
