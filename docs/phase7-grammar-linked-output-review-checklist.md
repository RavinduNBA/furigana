# Phase 7 linked grammar-output review checklist

Review `artifacts/phase7/linked/run-a/` against
`tests/phase7_golden/grammar-linked-v1/` and the reviewed cases.

## Machine checks

- [ ] Run A, run B, and all checked-in XHTML goldens are byte-identical.
- [ ] Four namespaced XHTML documents parse with unique IDs.
- [ ] Three grammar forward links and three matching backlinks resolve.
- [ ] Seven exact canonical contexts occur in grammar-plan order.
- [ ] Reference-only, rejected, and publisher-protected occurrences have no grammar link.
- [ ] The three `〜ている` contexts show reference-only, linked, and publisher-preserved states.
- [ ] Existing vocabulary, expression, and name links remain unchanged.
- [ ] Visible source text, emphasis, namespaces, IDs, and publisher ruby remain unchanged.
- [ ] All generated hrefs are relative, internal, and fragment-valid.
- [ ] No nested anchors, nested ruby, scripts, provider metadata, or EPUB data appears.
- [ ] Disabled and failure outputs reproduce the input linked set byte-for-byte.
- [ ] Phase 4/5 linked vocabulary XHTML remains byte-identical.

## Manual review

- [ ] Linked grammar occurrences navigate to the correct grammar note and back.
- [ ] Nonlinked contexts do not imply that a backlink exists.
- [ ] Partial overlap preserves vocabulary behavior and clearly rejects only grammar linking.
- [ ] Publisher-ruby preservation is unambiguous.
- [ ] Grammar and vocabulary navigation remain visually and conceptually distinct.

## Review record

- Reviewer:
- Date:
- Commit:
- Result: PENDING
- Notes:
