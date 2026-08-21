# Phase 7 packaged grammar-EPUB review checklist

Review `artifacts/phase7/epub/run-a.epub` structurally and in Calibre 8.14.
The fixture is synthetic test data and does not approve the curated rules for
production use.

## Machine checks

- [x] Run A and run B are byte-identical and match the checked-in SHA-256.
- [x] Eight deterministic archive members have safe unique paths.
- [x] `mimetype` is first, exact, and uncompressed.
- [x] Ordering, timestamps, permissions, and compression match the golden.
- [x] Container, package metadata, manifest, spine, and navigation validate.
- [x] Spine order is chapter 1, chapter 2, Study Notes, Grammar Study Notes.
- [x] TOC order matches the spine and keeps the two note layers separate.
- [x] All four packaged text XHTML members equal the approved linked files.
- [x] Five grammar notes, seven contexts, three forward links, three backlinks,
  and five study links resolve.
- [x] Reference-only, rejected, and publisher-protected occurrences stay nonlinked.
- [x] Visible text, emphasis, existing links, IDs, and publisher ruby are preserved.
- [x] No nested anchors/ruby, unsafe markup, provider metadata, or external resources appear.
- [x] Disabled and failed packaging reproduce the vocabulary-only EPUB byte-for-byte.
- [x] Phase 4 and Phase 5 XHTML and EPUB compatibility checks pass.

## Manual Calibre 8.14 review

- [x] TOC shows both chapters, Study Notes, then Grammar Study Notes.
- [x] Chapter text, emphasis, vocabulary links, and publisher ruby render normally.
- [x] All three grammar forward links reach the correct grammar note and return.
- [x] Reference-only and rejected contexts show no misleading backlink.
- [x] The shared 〜ている note clearly distinguishes all three occurrence states.
- [x] Study Notes and Grammar Study Notes are readable and visually distinct.
- [x] No broken links, duplicated text, missing content, or unexpected layout changes appear.

## Review record

- Reviewer: Ravindu
- Date: 2026-08-21
- Commit: `41f6bd4b41ac12534e25e59ddbf9bc79eed78e98`
- Calibre version: 8.14
- Fixture: `artifacts/phase7/epub/run-a.epub`
- Result: PASS
- Notes: Machine verification passed deterministic archive, checksum, package,
  navigation, XHTML/link, fallback, and Phase 4/5 compatibility checks. Manual
  review passed TOC and navigation separation, chapter layout, existing study
  links, publisher ruby, all three linked grammar round trips, nonlinked overlap
  behavior, five-note ordering, and the three 〜ている states. No broken or
  misleading links, nested markup, missing content, metadata leakage, or
  unexpected layout changes were observed. Compact synthetic Study Notes
  intentionally contain only selected words and backlinks and were accepted.
  This legal synthetic mechanics fixture does not approve the curated grammar
  rules or the standalone synthetic 〜て rule for production use.
