# Phase 7 packaged grammar-EPUB review checklist

Review `artifacts/phase7/epub/run-a.epub` structurally and in Calibre 8.14.
The fixture is synthetic test data and does not approve the curated rules for
production use.

## Machine checks

- [ ] Run A and run B are byte-identical and match the checked-in SHA-256.
- [ ] Eight deterministic archive members have safe unique paths.
- [ ] `mimetype` is first, exact, and uncompressed.
- [ ] Ordering, timestamps, permissions, and compression match the golden.
- [ ] Container, package metadata, manifest, spine, and navigation validate.
- [ ] Spine order is chapter 1, chapter 2, Study Notes, Grammar Study Notes.
- [ ] TOC order matches the spine and keeps the two note layers separate.
- [ ] All four packaged text XHTML members equal the approved linked files.
- [ ] Five grammar notes, seven contexts, three forward links, three backlinks,
  and five study links resolve.
- [ ] Reference-only, rejected, and publisher-protected occurrences stay nonlinked.
- [ ] Visible text, emphasis, existing links, IDs, and publisher ruby are preserved.
- [ ] No nested anchors/ruby, unsafe markup, provider metadata, or external resources appear.
- [ ] Disabled and failed packaging reproduce the vocabulary-only EPUB byte-for-byte.
- [ ] Phase 4 and Phase 5 XHTML and EPUB compatibility checks pass.

## Manual Calibre 8.14 review

- [ ] TOC shows both chapters, Study Notes, then Grammar Study Notes.
- [ ] Chapter text, emphasis, vocabulary links, and publisher ruby render normally.
- [ ] All three grammar forward links reach the correct grammar note and return.
- [ ] Reference-only and rejected contexts show no misleading backlink.
- [ ] The shared 〜ている note clearly distinguishes all three occurrence states.
- [ ] Study Notes and Grammar Study Notes are readable and visually distinct.
- [ ] No broken links, duplicated text, missing content, or unexpected layout changes appear.

## Review record

- Reviewer:
- Date:
- Commit:
- Calibre version:
- Fixture: `artifacts/phase7/epub/run-a.epub`
- Result: PENDING
- Notes:
