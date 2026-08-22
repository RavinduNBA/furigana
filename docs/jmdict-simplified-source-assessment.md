# `jmdict-simplified` source assessment

- Assessment date: 2026-08-21
- Project: https://github.com/scriptin/jmdict-simplified
- Status: `candidate-for-future-optional-adapter`
- Production-source decision: none

This is a bounded documentation assessment. No repository was cloned, no release or dictionary archive was downloaded, and no NPM package, Gradle project, Java tool, or dependency was installed. No network-backed runtime lookup is proposed.

## Project shape

The project publishes JMdict, JMnedict, Kanjidic, and related RADKFILE/KRADFILE data using regular, self-contained JSON structures. Its documentation currently describes automatically scheduled Monday releases, prebuilt release archives, and local conversion tooling.

JMdict distributions include full, common-only, language-specific, and an English example-bearing variant. The project notes that the example-bearing variant has incomplete package support. JMnedict remains a separate, English-only dataset and does not have JMdict-style common-entry indicators. These variants are semantically meaningful inputs, not interchangeable packaging choices.

The JSON shape may simplify ingestion, but an adapter must map into Furiganalyse's existing internal JMdict and JMnedict semantics. It must not redefine lookup, ordering, identity, restrictions, provenance, or precedence.

Authoritative references reviewed:

- Project and distribution documentation: https://github.com/scriptin/jmdict-simplified
- Format/type documentation: https://scriptin.github.io/jmdict-simplified/
- Official project releases: https://github.com/scriptin/jmdict-simplified/releases
- Project source-code licence: https://github.com/scriptin/jmdict-simplified/blob/master/LICENSE.txt
- EDRDG dictionary-data licence: https://www.edrdg.org/edrdg/licence.html

## Licensing boundary

Repository code and dictionary data must be assessed separately:

- The project documents its source code and other project files as Creative Commons Attribution-ShareAlike 4.0, apart from separately identified packages and data.
- The project documents its NPM type and loader packages as MIT licensed.
- Derived JMdict and JMnedict JSON files remain governed by the original EDRDG dictionary-data terms. The EDRDG licence applies to listed dictionary files and derived data, requires attribution and licence documentation or links, and includes share-alike conditions for distributed adaptations.

This assessment is not legal approval. Before bundling or redistributing any derived data, a separate legal/licensing review must confirm the exact attribution, documentation, redistribution, update, and share-alike obligations for the intended product and distribution model. Furiganalyse must not claim that the project repository licence replaces the underlying dictionary-data licence.

## Required semantic mapping

A future adapter must preserve and test all of the following:

### JMdict

- stable entry identity and original sequence;
- ordered written forms;
- ordered readings, no-kanji flags, and reading-to-written-form restrictions;
- written-form and reading priorities;
- ordered senses and stable derived sense IDs;
- parts of speech, field tags, and dialect tags;
- sense restrictions by written form and reading;
- gloss ordering, language, and gloss type;
- expression records remaining distinct from ordinary single-token vocabulary where Furiganalyse already distinguishes them.

### JMnedict

- stable entry identity and original sequence;
- ordered written forms and readings;
- reading-to-written-form restrictions;
- ordered translations and stable derived translation IDs;
- name types and translation language;
- JMnedict proper names remaining separate from JMdict vocabulary and expressions.

### Provenance and internal identity

- source project and dataset identity;
- distribution variant: full, common-only, example-bearing, or another explicitly supported variant;
- language variant;
- pinned release identifier and release date;
- verified upstream checksum and separately recorded local SHA-256;
- adapter schema and implementation version;
- deterministic internal entry, sense, translation, index, and provenance hashes.

## Precedence and compatibility

Any future JSON adapter must preserve the established precedence:

1. publisher readings remain authoritative;
2. explicit user-approved terminology outranks dictionary display meanings;
3. dictionary evidence remains below publisher and user decisions;
4. JMdict vocabulary and expressions remain separate from JMnedict names.

A common-only distribution must never silently replace full JMdict. Language filtering must be explicit and recorded in provenance. Switching source formats must not change Phase 3–7 output ordering, stable IDs, meanings, readings, classifications, offsets, anchors, or source references.

## Pinning and reproducibility

A future adapter must:

- accept only an explicit local file path;
- require a pinned release identifier rather than a moving `latest` URL;
- verify an expected upstream checksum and record the local SHA-256;
- record source project, distribution and language variants, release date, and adapter version;
- reject unsupported schemas, release mismatches, and checksum mismatches deterministically;
- never download data during analysis, tests, rendering, or packaging.

No network access should be required at runtime. Acquiring and approving dictionary files must remain a separate, explicit operation outside the analysis pipeline.

## Proposed future acceptance gates

- Small, legal, checked-in synthetic JSON fixtures for JMdict and JMnedict.
- XML-versus-JSON semantic parity tests over representative entries.
- Written/reading restriction, priority, sense-order, gloss-language, and gloss-type parity.
- JMdict expression and JMnedict proper-name separation.
- Publisher-ruby precedence and user-terminology precedence.
- Deterministic indexing, lookup, IDs, hashes, and serialization.
- Full/common-only and language-variant mismatch diagnostics.
- Disabled and failure byte identity with the existing XML-backed path.
- Separate licence, attribution, redistribution, and update-policy review.
- Production-size performance testing outside the normal regression suite.
- No network access at runtime.

## Recommendation

Retain the existing explicit local XML-backed JMdict and JMnedict path as authoritative. Treat `jmdict-simplified` as a promising optional future ingestion adapter, not a required dependency or a replacement dictionary model.

Do not bundle or redistribute its derived dictionary data yet. Do not use it in Phase 8 learner-profile work unless a separate implementation request approves the adapter, fixtures, semantic-parity gates, release pinning, and licensing review.
