# Phase 7 standalone grammar-note XHTML review checklist

Review `artifacts/phase7/grammar-notes/run-a/grammar-notes.xhtml` against
`tests/phase7_golden/grammar-notes-v1.xhtml` and the reviewed cases.

## Machine checks

- [ ] Run A, run B, and the checked-in golden are byte-identical.
- [ ] The XHTML parses with the XHTML namespace and Japanese language metadata.
- [ ] Five grammar notes and seven ordered occurrence references are present.
- [ ] Curated keys, labels, explanations, formations, usage, provenance, and hashes match.
- [ ] Grammar note anchors are stable and unique.
- [ ] Repeated `〜ている` retains three distinct source references.
- [ ] Publisher-ruby protection is described without rendering ruby or `rt`/`rp` text.
- [ ] Synthetic `〜て` is absent by default and test-only rendering is explicit.
- [ ] CSS selectors are restricted to grammar-note classes.
- [ ] Links, backlinks, scripts, external resources, and provider metadata are absent.
- [ ] Existing Phase 4/5 vocabulary-note XHTML remains byte-identical.
- [ ] Disabled, stale, invalid, and corrupt inputs emit safe diagnostics and no XHTML.

## Manual review

- [ ] The five grammar notes are readable and clearly distinct from dictionary notes.
- [ ] Curated explanations and formations are concise and understandable.
- [ ] Occurrence references are useful without copying unrelated context.
- [ ] Publisher-ruby preservation and the synthetic-rule limitation are clear.

## Review record

- Reviewer:
- Date:
- Commit:
- Result: PENDING
- Notes:
