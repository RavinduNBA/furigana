# Phase 7 linked grammar-output review checklist

Review `artifacts/phase7/linked/run-a/` against
`tests/phase7_golden/grammar-linked-v1/` and the reviewed cases.

## Machine checks

- [x] Run A, run B, and all checked-in XHTML goldens are byte-identical.
- [x] Four namespaced XHTML documents parse with unique IDs.
- [x] Three grammar forward links and three matching backlinks resolve.
- [x] Seven exact canonical contexts occur in grammar-plan order.
- [x] Reference-only, rejected, and publisher-protected occurrences have no grammar link.
- [x] The three `〜ている` contexts show reference-only, linked, and publisher-preserved states.
- [x] Existing vocabulary, expression, and name links remain unchanged.
- [x] Visible source text, emphasis, namespaces, IDs, and publisher ruby remain unchanged.
- [x] All generated hrefs are relative, internal, and fragment-valid.
- [x] No nested anchors, nested ruby, scripts, provider metadata, or EPUB data appears.
- [x] Disabled and failure outputs reproduce the input linked set byte-for-byte.
- [x] Phase 4/5 linked vocabulary XHTML remains byte-identical.

## Manual review

- [x] Linked grammar occurrences navigate to the correct grammar note and back.
- [x] Nonlinked contexts do not imply that a backlink exists.
- [x] Partial overlap preserves vocabulary behavior and clearly rejects only grammar linking.
- [x] Publisher-ruby preservation is unambiguous.
- [x] Grammar and vocabulary navigation remain visually and conceptually distinct.

## Review record

- Reviewer: Ravindu
- Date: 2026-08-20
- Commit: 6228fdf488822c1179f10649dbc6693c4e5f4df6
- Result: PASS
- Notes: Machine review confirmed deterministic XHTML, five notes, seven exact
  contexts, three resolved forward links and backlinks, safe nonlinked overlap
  dispositions, publisher-ruby preservation, compatibility, and byte-identical
  fallback outputs. Manual review approved navigation, nonlinked context labels,
  overlap behavior, publisher boundaries, and separation of grammar and
  vocabulary navigation. The legal synthetic fixture does not approve the
  curated dataset for production use; the standalone synthetic `〜て` mechanics
  rule remains excluded and unapproved. The reviewed artifacts evidence no
  provider, SDK, network, OPF, navigation, EPUB-packaging, or Calibre activity;
  this is not a claim about unobserved external system state.
