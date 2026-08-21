# Phase 7 synthetic grammar-evaluation review checklist

Review the deterministic evaluation report as synthetic regression evidence.
Perfect fixture metrics do not establish production grammar accuracy or approve
the curated rules.

## Corpus and provenance

- [x] Corpus, dataset, source, configuration, and report hashes validate.
- [x] The corpus is explicitly synthetic, copyright-free, and versioned.
- [x] Exactly 20 positives cover four occurrences of each primary rule.
- [x] Thirteen labeled negatives provide 12 scored true negatives plus one
  explicitly excluded synthetic-mechanics competitor.
- [x] Expected labels and offsets come from checked-in ground truth, not detector output.

## Baseline metrics

- [x] Baseline has 20 TP, 0 FP, 0 FN, and 12 TN.
- [x] Precision and recall are each 20/20.
- [x] Every primary rule has 4/4 recall.
- [x] The synthetic 〜て mechanics rule is excluded from primary scoring.
- [x] Grammar, JMdict expressions, names, and publisher ruby remain separate.

## Rule controls and safety

- [x] Each primary rule can be disabled independently.
- [x] Disabling one primary rule excludes only its four positives.
- [x] All unaffected result IDs, hashes, ordering, and references remain unchanged.
- [x] Re-enabling restores the exact baseline primary results.
- [x] Unknown and duplicate rule requests fail safely.
- [x] Disabled, stale, invalid, and corrupt inputs emit deterministic diagnostics.
- [x] Approved Phase 3, Phase 5, and Phase 7 artifacts remain unchanged.

## Review record

- Reviewer: Ravindu
- Date: 2026-08-21
- Commit: `d1573adc599829eed737a045112403b90effef21`
- Result: PASS
- Notes: Machine verification passed deterministic corpus, input, report, and
  disable-matrix identity; source references, offsets, IDs, hashes, metrics,
  independent rule controls, safe diagnostics, privacy, and Phase 3/5/7
  compatibility. Manual review approved the five primary classifications,
  repeated `〜ている`, boundaries and confounders, lexical/name/ruby
  separation, longest-match behavior, integer metric denominators, and
  independently reversible rule disabling. The corpus is synthetic regression
  evidence only: 20/20 precision, 20/20 recall, and 4/4 per-rule recall do not
  establish production accuracy, completeness, or rule approval. The
  standalone `〜て` rule remains a synthetic mechanics fixture excluded from
  production-quality metrics. The reviewed artifacts evidence no provider,
  SDK, network, model-judgment, XHTML-mutation, EPUB-packaging, or Calibre
  activity; this is not a claim about unobserved external system state.
