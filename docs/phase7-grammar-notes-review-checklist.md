# Phase 7 standalone grammar-note XHTML review checklist

Review `artifacts/phase7/grammar-notes/run-a/grammar-notes.xhtml` against
`tests/phase7_golden/grammar-notes-v1.xhtml` and the reviewed cases.

## Machine checks

- [x] Run A, run B, and the checked-in golden are byte-identical.
- [x] The XHTML parses with the XHTML namespace and Japanese language metadata.
- [x] Five grammar notes and seven ordered occurrence references are present.
- [x] Curated keys, labels, explanations, formations, usage, provenance, and hashes match.
- [x] Grammar note anchors are stable and unique.
- [x] Repeated `〜ている` retains three distinct source references.
- [x] Publisher-ruby protection is described without rendering ruby or `rt`/`rp` text.
- [x] Synthetic `〜て` is absent by default and test-only rendering is explicit.
- [x] CSS selectors are restricted to grammar-note classes.
- [x] Links, backlinks, scripts, external resources, and provider metadata are absent.
- [x] Existing Phase 4/5 vocabulary-note XHTML remains byte-identical.
- [x] Disabled, stale, invalid, and corrupt inputs emit safe diagnostics and no XHTML.

## Manual review

- [x] The five grammar notes are readable and clearly distinct from dictionary notes.
- [x] Curated explanations and formations are concise and understandable.
- [x] Occurrence references are useful without copying unrelated context.
- [x] Publisher-ruby preservation and the synthetic-rule limitation are clear.

## Review record

- Reviewer: Ravindu
- Date: 2026-08-20
- Commit: `5d415be77a66452053c19d444ceaf0a97f814e85`
- Result: PASS
- Notes: Machine verification confirmed deterministic namespaced XHTML, five
  ordered notes, seven occurrence references, curated rule provenance, stable
  anchors, publisher-ruby protection, safe diagnostics, and byte-identical
  Phase 4/5 vocabulary notes. Manual review approved readability, concise
  grammar explanations, auditable occurrence references, and isolation from
  dictionary notes. The explicit synthetic-mechanics XHTML has no standalone
  warning banner; its test-only status is established by the explicit CLI
  option, plan configuration, artifact path, and synthetic dataset identity.
  The synthetic `〜て` rule remains unapproved for production use.
