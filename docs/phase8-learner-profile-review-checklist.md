# Phase 8 learner-profile and assistance-selection review

Use the retained artifacts under `artifacts/phase8/selection/`. The presets and profiles are synthetic fixtures for deterministic mechanics; they are not learner diagnoses or pedagogically validated JLPT defaults.

## Machine verification

- [x] Run-A, run-B, and `assistance-selection-v1.json` are byte-identical.
- [x] Profile, preset, override, exposure, result, configuration, diagnostic, and report hashes validate.
- [x] Source vocabulary schema is 4, annotation-plan schema is 2, and optional grammar-plan schema is 1.
- [x] Source hashes and book identity match exactly.
- [x] Result order is five Phase 5-style study items followed by five Phase 7 grammar items.
- [x] All four reading/meaning combinations are represented by explicit profiles.
- [x] Grammar assistance remains independent of reading and meaning assistance.
- [x] N5 provides the most assistance, N4 moderately less, and N3 the least.
- [x] Every preset difference has explicit defaults, thresholds, and rationale codes.
- [x] Reading exposure changes only reading assistance.
- [x] Meaning exposure changes only meaning assistance.
- [x] Grammar exposure changes only grammar assistance.
- [x] Explicit reading, meaning, and grammar overrides outrank preset/exposure results.
- [x] Each effective dimension has exactly one recorded winning source.
- [x] Vocabulary, JMdict expressions, JMnedict names, and grammar remain separate.
- [x] Publisher-ruby-backed vocabulary and publisher-adjacent grammar remain `preserved-authoritative` even when reading assistance is hidden.
- [x] No dictionary reading, approved meaning, item kind, occurrence, offset, anchor, or source record is rewritten.
- [x] Disabled, stale, invalid, corrupt, duplicate, unknown, dimension-mismatch, and publisher-suppression paths have deterministic safe diagnostics.
- [x] Every fallback annotation plan and grammar plan is byte-identical to its input.
- [x] Phase 3 vocabulary and Phase 5 enriched-plan compatibility artifacts are byte-identical.
- [x] The approved Phase 7 EPUB checksum remains `df4c4bf0f072c01ac0a8d8aff316ee92613760c1822274cecd7ec9ce409a9619`.
- [x] No XHTML, EPUB, provider, model, cache, prompt, credential, path, or complete-book data appears.

## Manual review

1. Compare the four explicit reading/meaning profiles. Confirm that the combinations are understandable and affect independent dimensions only.
2. Compare N5, N4, and N3. Confirm that assistance decreases transparently and is presented as a synthetic default, not a learner diagnosis.
3. Review the reading, meaning, and grammar exposure cases. Confirm that each changes only its configured dimension at the recorded threshold.
4. Review all three explicit overrides. Confirm that each is local, auditable, dimension-specific, and wins over preset/exposure evidence.
5. Review the publisher-ruby vocabulary and publisher-adjacent grammar results. Confirm that publisher content remains authoritative in every profile.
6. Review expression, proper-name, vocabulary, and grammar results together. Confirm that their kinds and evidence remain separate.
7. Review disabled and failure artifacts. Confirm that diagnostics are safe and Phase 5/7 source plans are byte-identical.

## Result

- Date: 2026-08-21
- Commit: `57dff4321573ad6492198d2316b49d9203dd9372`
- Reviewer: Ravindu
- Machine verification: PASS — deterministic identity, hashes, ordering, precedence, diagnostics, fallback identity, and Phase 3/5/7 compatibility were verified.
- Manual review: PASS — assistance dimensions, synthetic presets, exposure behavior, explicit overrides, evidence-kind separation, and publisher precedence were approved.
- Result: PASS
- Notes: N5, N4, and N3 are synthetic explainable defaults, not learner diagnoses or pedagogically validated JLPT placement. Exposure history is explicit local fixture data, not inferred behavioral telemetry. Hidden assistance is presentation suppression only; it does not delete readings, meanings, grammar evidence, or knowledge records. The reviewed artifacts evidence no provider, SDK, network, XHTML/link mutation, EPUB packaging, Calibre, or dictionary-source activity.
