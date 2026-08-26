# EDRDG dictionary data sources

Furiganalyse can use explicit local indexes built from the official English
JMdict release and the separate JMnedict release. Dictionary files are not
downloaded during book analysis, rendering, or EPUB packaging, and they are not
committed to this repository.

The administrator-only updater is:

```bash
.venv/bin/python scripts/update_edrdg_dictionaries.py --replace
```

It downloads only the hard-coded official EDRDG HTTPS release URLs, records the
release dates and SHA-256 values, builds local SQLite indexes, and atomically
replaces the previous local release. Moving `latest` URLs are not used as
analysis provenance: each index stores the creation date embedded in its source
release and the exact XML SHA-256.

JMdict and JMnedict are property of the Electronic Dictionary Research and
Development Group and are used under the [EDRDG licence terms](https://www.edrdg.org/edrdg/licence.html)
and [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/).
JMdict vocabulary and expressions remain separate from JMnedict proper names.
Publisher-supplied ruby remains authoritative over dictionary readings.

The local release currently prepared for deployment was generated on
2026-08-22. No legal approval to bundle or redistribute the dictionary archives
is implied; production redistribution still requires a separate licensing
review.
