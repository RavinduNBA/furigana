# Phase 7 synthetic grammar-evaluation review checklist

Review the deterministic evaluation report as synthetic regression evidence.
Perfect fixture metrics do not establish production grammar accuracy or approve
the curated rules.

## Corpus and provenance

- [ ] Corpus, dataset, source, configuration, and report hashes validate.
- [ ] The corpus is explicitly synthetic, copyright-free, and versioned.
- [ ] Exactly 20 positives cover four occurrences of each primary rule.
- [ ] Thirteen labeled negatives provide 12 scored true negatives plus one
  explicitly excluded synthetic-mechanics competitor.
- [ ] Expected labels and offsets come from checked-in ground truth, not detector output.

## Baseline metrics

- [ ] Baseline has 20 TP, 0 FP, 0 FN, and 12 TN.
- [ ] Precision and recall are each 20/20.
- [ ] Every primary rule has 4/4 recall.
- [ ] The synthetic 〜て mechanics rule is excluded from primary scoring.
- [ ] Grammar, JMdict expressions, names, and publisher ruby remain separate.

## Rule controls and safety

- [ ] Each primary rule can be disabled independently.
- [ ] Disabling one primary rule excludes only its four positives.
- [ ] All unaffected result IDs, hashes, ordering, and references remain unchanged.
- [ ] Re-enabling restores the exact baseline primary results.
- [ ] Unknown and duplicate rule requests fail safely.
- [ ] Disabled, stale, invalid, and corrupt inputs emit deterministic diagnostics.
- [ ] Approved Phase 3, Phase 5, and Phase 7 artifacts remain unchanged.

## Review record

- Reviewer:
- Date:
- Commit:
- Result: PENDING
- Notes:
