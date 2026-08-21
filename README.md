<span class="badge-buymeacoffee">
<a href="https://www.buymeacoffee.com/itsupera" title="Donate to this project using Buy Me A Coffee"><img src="https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg" alt="Buy Me A Coffee donate button" /></a>
</span>
<span class="badge-dockercloudbuild">
<img src="https://img.shields.io/docker/cloud/build/itsupera/furiganalyse" title="Docker Cloud build status"></img>
</span>

Furiganalyse
=============

Annotate Japanese ebooks with furigana, and other conversions.

<a href="http://furiganalyse.itsupera.co/"><b>→ Try it here!</b></a>

![](assets/furiganalyse.jpg)

---

Supported input formats:
- EPUB
- AZW3 (without DRM)
- MOBI

Supported output formats:
- EPUB
- AZW3 (without DRM)
- MOBI
- Many text files (one per book part)
- Single text file
- Anki Deck (each sentence as a card)
- HTML (readable in web browser)

Setup and run
--------------

Using Docker to create a container with all the dependencies and dictionaries (tested on Ubuntu 24.04):
```bash
docker compose build
```
Or grab the latest prebuilt image:
```bash
docker pull itsupera/furiganalyse:latest
docker tag itsupera/furiganalyse:latest furiganalyse:latest
```

### Run as a web app
```bash
docker compose up -d
```
Then open http://127.0.0.1:5000 in your web browser

### Run as a CLI
```bash
# Run this from the directory your ebook (for example "book.epub") is in
docker run -v $PWD:/workspace --entrypoint=python3 furiganalyse:latest \
    -m furiganalyse /workspace/book.epub /workspace/book_with_furigana.epub
```

### Calling the API
```bash
# Submit a job
curl -v -XPOST http://127.0.0.1/submit \
    -F "file=@<path-to-your-epub>" \
    -F furigana_mode="add" \
    -F writing_mode="horizontal-tb" \
    -F of="epub" \
    -F redirect=false

# Response will look like this:
# {"uid":"<job-id>"}

# Check the status of the job
curl -v http://127.0.0.1/jobs/<job-id>/status
# Response will look like this:
# {
#   "uid": "<job-id>",
#   "status": "complete",
#   "result": "(...data...)"
# }

# Download the result
curl http://127.0.0.1/jobs/<job-id>/file -o output.epub
```

Local development setup
------------------------

Install python and poetry, (optionally) create a virtual environment, and install the dependencies:
```bash
poetry install
```

Phase 0 EPUB regression
-----------------------

The generated copyright-free fixture covers two chapters, navigation, CSS, an
image, internal links, punctuation, emphasis, publisher ruby, Japanese, and
non-Japanese text. Run:

```bash
./scripts/phase0-regression.sh
```

This runs focused checks, converts and validates the fixture, and retains
packed and unpacked files in `artifacts/phase0/`. Complete
`docs/phase0-calibre-checklist.md` before declaring Phase 0 complete.

Phase 1 publisher-ruby regression
---------------------------------

The Phase 1 gate extends the fixture with grouped and unusual publisher ruby,
`rb`/`rp` fallback markup, nested emphasis, a link around ruby, malformed ruby,
and annotatable text immediately after protected markup. Run:

```bash
./scripts/phase1-regression.sh
```

This compares publisher ruby structures before and after conversion, rejects
nested generated ruby, validates diagnostics and EPUB links, and retains the
Calibre artifacts in `artifacts/phase1/`. Complete
`docs/phase1-calibre-checklist.md` before declaring Phase 1 complete.

Phase 2 canonical extraction
----------------------------

Extract deterministic, versioned canonical chapter and block JSON directly
from an EPUB without modifying the book:

```bash
.venv/bin/python scripts/extract_book.py book.epub analysis/book.json
```

Run the complete Phase 2 acceptance gate with:

```bash
./scripts/phase2-regression.sh
```

The gate builds the legal fixture, performs two byte-identical extractions,
compares the result with the checked-in schema v2 golden JSON, runs the focused
tests, and retains inspectable output in `artifacts/phase2/`. Complete
`docs/phase2-manual-trace-checklist.md` before closing Phase 2.

The extractor follows manifest/spine order, processes only spine XHTML,
normalizes visible block text, excludes `rt`/`rp` readings from canonical text,
and records publisher ruby with provenance and source anchors. Schema v2 adds
deterministic sentences and text spans with block-relative offsets. It does not
perform dictionary lookup or render annotations.

The fixture passage containing publisher ruby for 表舞台 can be traced to block
`ch-0001-b-0004`, sentence `ch-0001-b-0004-s-0001`, and canonical text
`舞台は表舞台だった。` at block offsets 0 through 10. Its text spans cover
`舞台は`, `表舞台`, and `だった。`. The middle span references publisher-ruby
record `ch-0001-b-0004-r-0001`; its reading remains on that record and never
appears in canonical sentence text.

Phase 3 vocabulary candidates
-----------------------------

Generate a deterministic, versioned tokenizer and vocabulary-candidate report:

```bash
.venv/bin/python scripts/analyze_vocabulary.py book.epub analysis/vocabulary.json
```

Run the complete Phase 3 tokenizer/report gate with:

```bash
./scripts/phase3-regression.sh
```

The gate first runs Phase 2, then validates both dictionary-disabled schema v1
and synthetic-JMdict-enriched schema v2 output. It generates each report twice,
requires byte identity with its checked-in golden report, and runs the focused
Phase 3 suite. It retains schema v1 reports in `artifacts/phase3/run-a/` and
`run-b/`; the synthetic index and enriched reports are retained under
`artifacts/phase3/jmdict/`. Opt-in schema v3 expression artifacts are under
`artifacts/phase3/jmdict/expressions/`. Opt-in schema v4 JMnedict name
artifacts are retained under `artifacts/phase3/jmnedict/`.

The legal fixture produces 82 tokens and 60 candidates. The synthetic JMdict
matches 4 candidates: 言葉, two publisher-ruby 表舞台 occurrences, and the
inflected 振り返っ token through its 振り返る lemma. Review tokenizer records
with `docs/phase3-report-review-checklist.md` and enriched matches with
`docs/phase3-jmdict-report-review-checklist.md`.

The report consumes the Phase 2 canonical model and records stable token and
candidate IDs, lemmas, readings, parts of speech, context IDs, offsets, and
tokenizer provenance. Publisher ruby remains a single protected token using its
publisher reading. Punctuation, whitespace, and Latin-only tokens are excluded
from candidates.

The current stack is `furigana 0.5` with `mecab-python3 1.0.12` and the system
IPADIC-format dictionary (binary dictionary version 102). Segmentation is
dictionary-dependent: this environment splits `成功体験` into `成功` and `体験`,
where a NEologd dictionary may retain the compound. This slice reports those
boundaries without dictionary lookup or expression merging.

### Optional local JMdict lookup

Build an index from an explicitly supplied local JMdict-compatible XML snapshot:

~~~bash
.venv/bin/python scripts/build_jmdict_index.py \
    data/JMdict.xml data/jmdict.sqlite3 \
    --dataset-id jmdict --dataset-version YYYY-MM-DD
~~~

Then opt into dictionary enrichment:

~~~bash
.venv/bin/python scripts/analyze_vocabulary.py book.epub analysis/vocabulary.json \
    --jmdict-index data/jmdict.sqlite3
~~~

Enable deterministic longest-match expressions explicitly:

~~~bash
.venv/bin/python scripts/analyze_vocabulary.py book.epub analysis/vocabulary.json \
    --jmdict-index data/jmdict.sqlite3 --expressions
~~~

Without `--jmdict-index`, output remains the existing schema v1 tokenizer report.
With an index, schema v2 preserves all existing fields and adds ordered,
restriction-aware JMdict entry and sense matches. Each match retains entry and
sense IDs, written forms, readings, POS, restrictions, English glosses, and
dataset identity/version/SHA-256 provenance.

With `--expressions`, additive schema v3 records deterministic longest matches
across adjacent candidate tokens while retaining every token, candidate, and
single-token match. Expression records include component IDs, exact sentence
and block offsets, normalized lookup form, ordered entries, and senses.

### Optional local JMnedict name lookup

Build an index from an explicitly supplied local JMnedict-compatible snapshot:

~~~bash
.venv/bin/python scripts/build_jmnedict_index.py \
    data/JMnedict.xml data/jmnedict.sqlite3 \
    --dataset-id jmnedict --dataset-version YYYY-MM-DD
~~~

Enable the additive schema v4 name report:

~~~bash
.venv/bin/python scripts/analyze_vocabulary.py book.epub analysis/vocabulary.json \
    --jmdict-index data/jmdict.sqlite3 --expressions \
    --jmnedict-index data/jmnedict.sqlite3
~~~

JMnedict is disabled unless `--jmnedict-index` is supplied. Names remain
separate from JMdict vocabulary and expression matches. Eligible records need
either tokenizer proper-noun evidence or publisher ruby; publisher readings
are authoritative. Selected occurrences retain candidate/token references,
offsets, name types, ordered translations, and provenance. Eligible rejected
candidates receive deterministic diagnostics rather than guessed names.

Tests use a tiny synthetic JMdict-compatible fixture; no production dictionary
is downloaded or committed. Production snapshots must be obtained and stored
locally according to their license, pinned with explicit identity/version, and
rebuilt when updated. Expression matching is limited to eight contiguous
Japanese candidate tokens. It never crosses punctuation, whitespace, Latin
text, sentence boundaries, or publisher ruby. Overlaps use deterministic
longest-match-first selection. Name lookup remains exact and is not merged with
expression records. Entity resolution and sense ranking remain future work.

The checked-in synthetic dataset provenance is
`furiganalyse-synthetic-jmdict`, version `2026-08-16`, index format 1, with
XML SHA-256
`b4952e87b430740d35bd4d5a50b463c764c12535d750ee9a18f5c0c848ad6deb`.
The strict schema-v2 golden is
`tests/phase3_golden/vocabulary-jmdict-v2.json`; compact reviewed expectations
are in `tests/phase3_golden/jmdict-review-cases-v2.json`.

The expression fixture provenance is
`furiganalyse-synthetic-jmdict-expressions`, version `2026-08-16`, index
format 1, SHA-256
`d6c7684e1d58abc65d07bed5525a7c216c617466a5cc988ef2955e1108d4b169`.
The legal fixture selects one expression, `良い天気だ`, normalized to
`良い天気`. Review schema v3 with
`docs/phase3-expression-report-review-checklist.md`.

The synthetic name fixture provenance is
`furiganalyse-synthetic-jmnedict`, version `2026-08-16`, index format 1,
SHA-256
`64ad15610f2c9b717c33ffae86504fb4e4f1136860269f33c027b57fef86f7ca`.
The legal fixture selects one name, `雪乃【ゆきの】`, with four explicit
publisher-candidate diagnostics. Review schema v4 with
`docs/phase3-jmnedict-report-review-checklist.md`. Production JMnedict data
must be obtained, licensed, pinned, and stored locally; none is downloaded or
committed by this project.

## Phase 4 annotation planning

Phase 4 starts with deterministic dictionary-only study selection from the
Phase 3 schema-v4 report; it does not reparse or modify EPUB XHTML. Run:

~~~bash
./scripts/phase4-regression.sh
~~~

The gate runs Phase 3 first, generates the plan twice, requires byte identity
with `tests/phase4_golden/annotation-plan-v1.json`, and runs focused Phase 4
tests. Outputs remain under `artifacts/phase4/`.

The legal fixture selects 5 unique items from 6 occurrences and records 52
exclusion diagnostics. The default limit is 10 unique items per primary
chapter; override it with `scripts/create_study_plan.py --per-chapter-limit N`.
Selection uses the first compatible source-ordered entry and sense or
translation. Publisher readings remain authoritative, names stay distinct from
vocabulary, and repeated lexical items retain ordered occurrence references.
This baseline does not perform contextual sense ranking, learner adaptation, or
EPUB rendering. Review it with
`docs/phase4-annotation-plan-review-checklist.md`.

### Standalone study-note XHTML

Render a validated annotation plan without reparsing the EPUB:

~~~bash
.venv/bin/python scripts/render_study_notes.py \
  artifacts/phase4/run-a/annotation-plan.json \
  artifacts/phase4/notes/study-notes.xhtml
~~~

The enhanced `./scripts/phase4-regression.sh` gate renders two copies under
`artifacts/phase4/notes/run-a/` and `run-b/`, requires byte identity with
`tests/phase4_golden/study-notes-v1.xhtml`, strictly parses the XHTML, and
runs focused plan and rendering tests. The legal fixture produces five ordered
note sections with stable plan-provided anchors.

Each section identifies vocabulary, expressions, or proper names and shows the
authoritative reading, dictionary-only meaning, occurrence count, dataset
identity/version, and selected entry plus sense or translation reference.
Names use JMnedict translations and remain distinct from ordinary vocabulary.
Publisher readings are rendered as text; this document creates no ruby markup.
Its minimal inline CSS is scoped to `study-notes` and `study-note` classes.

This slice deliberately remains standalone: it does not modify source chapters,
add links/backlinks, update OPF/navigation, or package a new EPUB. Review the
rendered result with `docs/phase4-study-notes-review-checklist.md`.

### Standalone linked XHTML set

Generate linked chapter copies plus contextual note backlinks:

~~~bash
.venv/bin/python scripts/render_linked_study_notes.py \
  artifacts/phase2/fixture.epub \
  artifacts/phase2/run-a/book.json \
  artifacts/phase4/run-a/annotation-plan.json \
  artifacts/phase4/linked/manual
~~~

The renderer also accepts an extracted EPUB directory as its first argument.
It writes chapter copies at their canonical source paths and
`EPUB/text/study-notes.xhtml` beneath the output directory. The originals are
never changed. Six legal-fixture occurrences receive unique source anchors,
forward links, exact canonical context sentences, and ordered backlinks to five
notes.

Plain selections must occupy one unambiguous XHTML text slot. Publisher-ruby
selections wrap the complete existing ruby element, preserving its rt/rp and
children. Existing links, emphasis, IDs, namespaces, and visible text are
validated after rendering. Unsafe paths, nested links/ruby, offset mismatches,
ambiguous DOM mappings, overlaps, and broken generated references are rejected.

The Phase 4 gate creates byte-identical linked run-A/run-B trees under
`artifacts/phase4/linked/` and compares all three XHTML files strictly with
`tests/phase4_golden/linked-v1/`. This remains an unpackaged output: OPF,
spine, navigation, resources, archive metadata, and the input EPUB are
unchanged. Review with `docs/phase4-linked-output-review-checklist.md`.

### Deterministic study EPUB

Package the linked output with `scripts/package_study_epub.py INPUT BOOK_JSON
PLAN_JSON OUTPUT.epub`. The Phase 4 gate retains byte-identical outputs under
`artifacts/phase4/epub/`, validates archive structure and every internal
reference, and runs focused packaging tests. The packager adds one
`furiganalyse-study-notes` manifest/spine item and one “Study Notes” TOC
entry after chapter 2 while preserving unrelated resources. ZIP timestamps,
permissions, ordering, compression, and the first uncompressed mimetype entry
are deterministic. See `docs/phase4-packaged-epub-review-checklist.md` for
the next manual Calibre review.

## Phase 5 controlled local-context enrichment

Phase 5 starts with provider-neutral schema v1 request packets, strict response
validation, deterministic per-response cache files, and dictionary-only
fallback. Enrichment is disabled unless both a local provider and cache path are
explicitly supplied. Run `./scripts/phase5-regression.sh`.

Each selected item receives at most the containing sentence plus one adjacent
sentence on either side from the same block. Requests contain ordered supplied
JMdict senses or JMnedict translations, provenance, stable IDs, and a context
hash; they never contain the complete book. Cache keys include provider/model,
prompt and response-schema versions, item, candidates, and context hash.

The only provider in this slice is a local scripted test provider. Invalid,
timed-out, unavailable, or corrupt responses produce concise diagnostics and
retain dictionary-only meanings. Publisher/user provenance outranks dictionary,
which outranks model phrasing. No SDK, network call, API key, XHTML mutation, or
model-produced markup is supported. Artifacts are retained under
`artifacts/phase5/`; review with
`docs/phase5-request-fallback-review-checklist.md`.

### Deterministic prompts and opt-in provider boundary

Render the validated requests without invoking a provider using
`scripts/render_enrichment_prompts.py REQUESTS_JSON OUTPUT_JSON`. Prompt packets
contain only the selected item, bounded same-block context, ordered supplied
dictionary records, provenance, precedence, and a strict response contract.
Their canonical content is hashed and covered by
`tests/phase5_golden/prompts-v1.json`.

`OpenAICompatibleProvider` is disabled unless a caller explicitly supplies a
model, credential, cache directory, and transport. The regression gate injects
only a local fake transport; it performs no network request and uses no real
credential. The optional SDK transport is imported lazily, uses a fixed timeout,
bounded output, deterministic settings, and no automatic retries. The core,
scripted provider, cache-only mode, and dictionary fallback do not require the
SDK. Credentials are confined to the executable transport boundary and are
excluded from prompts, cache keys, reports, diagnostics, and logs.

Production-shaped invocation is intentionally explicit:
`scripts/run_openai_enrichment.py REQUESTS_JSON OUTPUT_JSON --enable-openai-compatible
--model MODEL --cache-dir CACHE_DIR`. It reads the credential from
`OPENAI_API_KEY` by default (or the name supplied with `--api-key-env`) only at
the CLI boundary. The optional `openai` package must be installed separately;
it is not required or exercised by the regression suite.

Run `./scripts/phase5-regression.sh`; provider artifacts are retained under
`artifacts/phase5/provider/`. Review them with
`docs/phase5-provider-prompt-review-checklist.md`. Transport errors, refusals,
malformed JSON, invalid references, and unsupported responses are never cached
and retain dictionary-only meanings.

### Applying validated meanings to the annotation plan

Use `scripts/apply_enrichment_plan.py PLAN REQUESTS ENRICHMENT_REPORT
ENRICHED_OUTPUT FALLBACK_OUTPUT` to apply already validated model or cache
results. The applicator performs no linguistic analysis, prompt rendering,
provider invocation, network access, or EPUB work. Schema-v2 output preserves
the Phase 4 item/occurrence order and protected metadata while retaining an
audit record containing the original dictionary meaning, selected dictionary
references, context hash, prompt/schema versions, cache identity, provider,
model, and provenance precedence.

Only the short display meaning and optional ambiguity note are model-controlled.
Publisher readings, item kinds, source references, offsets, occurrences, and
anchors cannot change. Mixed reports retain dictionary meanings for failed or
missing items. If no validated enrichment is accepted, both output paths are
byte-identical copies of the Phase 4 plan. The regression gate retains reviewed
output under `artifacts/phase5/enriched-plan/`; see
`docs/phase5-enriched-plan-review-checklist.md`.

### Rendering enriched study notes

The existing note, linked-XHTML, and EPUB commands accept either the unchanged
Phase 4 schema-v1 plan or a strictly validated Phase 5 schema-v2 plan. Both use
the same rendering path. Schema v2 changes only the active reader-facing note
meanings: `fine weather` becomes `pleasant weather`, `language` becomes `word`,
and the name label becomes `Yukino (female given name)`.

Provider/model identities, cache keys, context hashes, prompt versions,
dictionary-only audit meanings, and ambiguity metadata are never rendered.
Publisher ruby, contexts, links, backlinks, anchors, styles, resources,
navigation, spine, and deterministic packaging remain unchanged. Schema-v1 and
disabled/failure plans reproduce the Phase 4 XHTML and EPUB bytes exactly.

`./scripts/phase5-regression.sh` retains enriched standalone XHTML, linked
documents, and byte-identical EPUBs under `artifacts/phase5/rendered/`. Review
with `docs/phase5-enriched-rendering-review-checklist.md`; Calibre verification
is a separate acceptance step.

## Phase 6 deterministic book context

Phase 6 begins with a provider-free sentence index over the validated canonical
book, schema-v4 vocabulary report, and schema-v2 enriched annotation plan. It
does not reparse XHTML or repeat linguistic analysis. Build the schema-v1 index:

    .venv/bin/python scripts/build_book_context.py build \
      artifacts/phase2/run-a/book.json \
      artifacts/phase3/jmnedict/run-a/vocabulary.json \
      artifacts/phase5/enriched-plan/run-a/annotation-plan.json \
      artifacts/phase6/manual/context-index.json

Retrieve the reviewed item/occurrence queries:

    .venv/bin/python scripts/build_book_context.py retrieve \
      artifacts/phase6/manual/context-index.json \
      tests/phase6_golden/retrieval-queries-v1.json \
      artifacts/phase6/manual/retrieval.json

Default retrieval includes the exact containing sentence and at most one
previous and following sentence from the same block. Explicit chapter scope may
cross blocks but never chapters. Sentence and character budgets retain whole
sentences only, preserve canonical order, and never return the complete book in
one result.

The index preserves source IDs, offsets, selected item/occurrence references,
JMdict/JMnedict separation, publisher ruby, tokenizer and dictionary
provenance, and stable source/query/result hashes. Precedence is publisher,
user-approved terminology, dictionary, book context, then model evidence.
Book context cannot change approved meanings, readings, dictionary records, or
the Phase 5 plan.

Context is disabled unless explicitly built and queried. Disabled, corrupt, or
incompatible input produces no augmentation; fallback plans remain byte-for-byte
identical to Phase 5. Safe diagnostics contain reason codes rather than raw
context, paths, credentials, or exceptions.

Run `./scripts/phase6-regression.sh`. It runs the Phase 5 gate first, verifies
byte-identical index/retrieval output against checked-in goldens, checks
disabled/failure identity, and retains artifacts under `artifacts/phase6/`.
Review with `docs/phase6-context-retrieval-review-checklist.md`.

This slice has no summaries, entity resolution, terminology decisions,
semantic retrieval, provider calls, network access, or rendering changes.

### Recurring-term and entity evidence

Build the schema-v1 evidence report from validated Phase 6/3/5 inputs:

    .venv/bin/python scripts/build_context_evidence.py build \
      artifacts/phase6/run-a/context-index.json \
      artifacts/phase3/jmnedict/run-a/vocabulary.json \
      artifacts/phase5/enriched-plan/run-a/annotation-plan.json \
      artifacts/phase6/evidence/manual/evidence.json

The default minimum occurrence count is 2. Override it explicitly with
--minimum-occurrences. Evidence groups use exact compatible lemma, normalized
expression, JMnedict identity, or publisher surface/reading keys. They preserve
first-seen source order, exact occurrence references and offsets, ordered
chapter counts, provenance, and deterministic hashes.

JMdict vocabulary, JMdict expressions, JMnedict names, publisher-backed
vocabulary, and publisher-backed names remain distinct. Different publisher
readings never merge. Single-occurrence groups remain visible but are marked
ineligible with safe insufficient-recurrence diagnostics.

This report is evidence only. It does not choose a preferred English label,
resolve aliases or entities, copy full context sentences, generate summaries,
or invoke a provider. Publisher and user provenance still outrank dictionary,
book-context, and model evidence. Disabled or failed generation preserves the
approved Phase 5 plan byte-for-byte.

The enhanced ./scripts/phase6-regression.sh generates evidence twice, compares
it strictly with tests/phase6_golden/evidence-v1.json, exercises thresholds 1
and 2, and retains artifacts under artifacts/phase6/evidence/. Review with
docs/phase6-evidence-review-checklist.md.

### Explicit user terminology registry

Terminology decisions are never inferred. A schema-v1 registry must be supplied
explicitly and every decision records a user reviewer, approval date, evidence
hash, source item/dictionary references, authoritative reading, status, and
decision hash.

Allowed statuses are approved, rejected, and deferred. Only approved decisions
produce an effective terminology term. Rejected and deferred decisions remain
auditable with no effective term. Publisher readings always remain unchanged
and outrank user terminology; user-approved terminology outranks dictionary,
book-context, and model suggestions.

Build the consistency report:

    .venv/bin/python scripts/build_terminology_consistency.py build \
      artifacts/phase6/evidence/run-a/evidence.json \
      artifacts/phase6/run-a/context-index.json \
      artifacts/phase5/enriched-plan/run-a/annotation-plan.json \
      tests/fixtures/phase6-terminology-registry-v1.json \
      artifacts/phase6/terminology/manual/consistency.json

The reviewed fixture explicitly approves 表舞台 as public stage and defers
雪乃. No decision exists for the three single-occurrence groups. Reports retain
all source occurrences and evidence provenance without mutating Phase 5 active
meanings. A differing approved term produces an audit diagnostic only.

Stale hashes, unknown groups, unsafe terms, invalid status/term combinations,
and source mismatches are rejected. Disabled or failed operation produces no
terminology augmentation and preserves the Phase 5 plan byte-for-byte.

The enhanced ./scripts/phase6-regression.sh retains terminology outputs under
artifacts/phase6/terminology/ and compares the reviewed output with
tests/phase6_golden/terminology-consistency-v1.json. Review with
docs/phase6-terminology-review-checklist.md.

This slice performs no automatic terminology selection, entity resolution,
alias merging, summaries, provider calls, network access, or rendering.

### Explicit chapter summaries and bounded retrieval

Build reference-only chapter packets from the validated context, evidence, and
terminology reports:

    .venv/bin/python scripts/build_chapter_summaries.py packets \
      artifacts/phase6/run-a/context-index.json \
      artifacts/phase6/evidence/run-a/evidence.json \
      artifacts/phase6/terminology/run-a/consistency.json \
      artifacts/phase6/summaries/manual/packets.json

Packets preserve canonical chapter order, sentence-record IDs, selected items
and occurrences, evidence and terminology references, publisher readings,
dictionary provenance, precedence, and stable hashes. They do not copy chapter
text. JMdict vocabulary/expressions and JMnedict names remain separate.

Chapter summaries are never generated automatically. The report command
requires an explicit local registry with approved, rejected, or deferred
decisions. Only an approved decision supplies effective summary text. The
checked-in registry is clearly labeled synthetic test-fixture data: chapter 1
has one short approved fixture summary and chapter 2 is deferred.

    .venv/bin/python scripts/build_chapter_summaries.py report \
      artifacts/phase6/summaries/manual/packets.json \
      tests/fixtures/phase6-chapter-summary-registry-v1.json \
      artifacts/phase6/summaries/manual/summary.json

The retrieve command resolves a chapter, study item, or occurrence. It returns
only approved summaries, optionally includes one previous approved chapter,
never includes a following chapter by default, and applies complete-summary
count and character budgets.

Disabled, stale, invalid, or corrupt operation preserves the approved Phase 5
plan byte-for-byte and emits safe reason codes without chapter text, paths,
credentials, cache data, or exceptions. The Phase 6 gate retains artifacts
under artifacts/phase6/summaries/; review them with
docs/phase6-chapter-summary-review-checklist.md.

This slice performs no automatic summarization, provider calls, book-wide
summaries, entity resolution, semantic retrieval, or rendering.

### Editable book-context manifest

The final Phase 6 integration composes the validated context index, evidence,
terminology, chapter packets, and summary report into a deterministic
reference-only manifest. It preserves chapter order, recurring terms, proper
names, publisher readings, explicit decisions, provenance, and hashes without
copying complete chapter text.

Use scripts/build_context_manifest.py to build or validate a manifest, rehash
explicit local edits, export terminology and summary registries, and produce
bounded per-item augmentation for existing Phase 5 requests. Only decision
status, approved short text, reviewer note, reviewer identity, and review date
are editable. Protected source and dictionary fields are rejected if changed.

The checked-in edited manifest is synthetic fixture data. It changes 表舞台 to
“public arena” and approves a short chapter-2 fixture summary while preserving
publisher readings and JMdict/JMnedict separation. Exported registries rebuild
the existing deterministic terminology and summary reports.

Augmentation returns only the lexical or name record matching each study item,
the target approved chapter summary, and optionally one previous approved
summary. It never changes Phase 5 sentence context, prompts, cache keys,
requests, annotation plans, XHTML, or EPUB output. Disabled or failed operation
preserves Phase 5 request and plan bytes exactly. Artifacts are retained under
artifacts/phase6/manifest/ and reviewed with
docs/phase6-context-manifest-review-checklist.md.
## Phase 7 curated grammar candidates

Phase 7 begins with a deterministic grammar-analysis layer over the existing
canonical book, schema-v4 vocabulary report, and schema-v2 annotation plan. It
does not reparse XHTML or modify vocabulary, study plans, notes, or EPUB files.

The initial dataset is a deliberately small synthetic fixture, not a production
grammar resource. Rules use exact ordered token surfaces, never cross sentence,
block, or chapter boundaries, and never inspect publisher `rt`/`rp` text.
Competing matches resolve by longest exact span, explicit rule priority, curated
rule order, and canonical source order. Vocabulary overlaps are retained only as
references in a separate grammar report.

Run the complete gate:

```bash
./scripts/phase7-regression.sh
```

Direct CLI usage:

```bash
.venv/bin/python scripts/analyze_grammar.py \\
  --book artifacts/phase7/run-a/inputs/book.json \\
  --vocabulary artifacts/phase7/run-a/inputs/vocabulary.json \\
  --annotation-plan artifacts/phase7/run-a/inputs/annotation-plan.json \\
  --dataset tests/fixtures/phase7-grammar-rules-v1.json \\
  --output artifacts/phase7/run-a/grammar.json
```

The gate retains deterministic reports, disabled/failure diagnostics, and
compatibility copies under `artifacts/phase7/`. Grammar is disabled unless an
explicit local dataset is supplied. Invalid inputs fail safely, and fallback
plans remain byte-identical. Current limitations include exact synthetic rules
only: no production dataset, fuzzy matching, model inference, grammar notes,
link rendering, or EPUB changes.

### Grammar study-item and overlap planning

The grammar-plan layer consumes the validated grammar report without repeating
detection. It selects the five primary synthetic rules, deduplicates repeated
rules while retaining occurrences, and excludes the standalone synthetic
`〜て` mechanics rule unless test-only inclusion is explicit. The default
per-chapter grammar-item limit is four.

Overlap records classify grammar spans as containing, contained by, exactly
matching, partially overlapping, non-overlapping, or publisher-ruby protected.
Existing vocabulary links always win: containing and exact matches become
grammar-note references, unsafe partial overlaps reject only the grammar link,
and publisher ruby is preserved. These are future link dispositions only; this
slice does not render anchors, XHTML, CSS, notes, or EPUB content.

```bash
.venv/bin/python scripts/create_grammar_plan.py \\
  --book artifacts/phase7/run-a/inputs/book.json \\
  --vocabulary artifacts/phase7/run-a/inputs/vocabulary.json \\
  --annotation-plan artifacts/phase7/run-a/inputs/annotation-plan.json \\
  --grammar-report artifacts/phase7/run-a/grammar.json \\
  --dataset tests/fixtures/phase7-grammar-rules-v1.json \\
  --output artifacts/phase7/grammar-plan/run-a/plan.json \\
  --enabled
```

The enhanced gate retains plans, limit cases, test-only synthetic inclusion,
safe fallback reports, and compatibility evidence under
`artifacts/phase7/grammar-plan/`.

### Standalone grammar study notes

Render a validated grammar plan as deterministic grammar-only XHTML:

```bash
.venv/bin/python scripts/render_grammar_notes.py \
  --plan artifacts/phase7/grammar-plan/run-a/plan.json \
  --dataset tests/fixtures/phase7-grammar-rules-v1.json \
  --output artifacts/phase7/grammar-notes/run-a/grammar-notes.xhtml
```

The default document contains five notes in grammar-plan order. Each note shows
the curated key, label, explanation, formation, optional usage labels, ordered
occurrence references, dataset version, rule hash, and selection provenance.
Stable `grammar-note-*` anchors and CSS scoped to `grammar-notes` and
`grammar-study-note` classes are used only inside this standalone document.

The synthetic `〜て` mechanics rule is rejected unless both the input plan and
the explicitly test-only renderer option enable it. Publisher-ruby-adjacent
occurrences are listed as protected references without copying `rt`/`rp` text
or rendering ruby. This slice creates no source links, backlinks, combined
vocabulary notes, chapter mutations, or EPUB changes. Disabled and invalid
inputs produce safe diagnostics and no XHTML. Existing Phase 4/5 vocabulary
notes remain byte-identical. Outputs are retained under
`artifacts/phase7/grammar-notes/` and reviewed with
`docs/phase7-grammar-notes-review-checklist.md`.

### Linked grammar contexts

Apply only the link dispositions already recorded in a validated grammar plan:

```bash
.venv/bin/python scripts/render_linked_grammar_notes.py \
  --source-dir artifacts/phase7/linked/source \
  --book artifacts/phase7/run-a/inputs/book.json \
  --plan artifacts/phase7/grammar-plan/run-a/plan.json \
  --dataset tests/fixtures/phase7-grammar-rules-v1.json \
  --output-dir artifacts/phase7/linked/run-a \
  --report artifacts/phase7/linked/run-a-report.json
```

The synthetic baseline has seven contexts but only three safe grammar links and
three matching backlinks. Direct and same-sentence non-overlapping occurrences
are linked. Contains-vocabulary and exact-span cases remain note references,
partial overlaps reject only grammar linking, and publisher-ruby cases remain
nonlinked and protected. Existing vocabulary, expression, and name links are
copied unchanged.

The renderer maps exact canonical offsets to an explicit local XHTML directory,
rejects ambiguous DOM insertion, validates every internal fragment, and never
modifies input files. Disabled or failed operation reproduces the input linked
set and emits only safe reason codes. It does not update OPF, navigation, CSS,
archives, or EPUB packages. Deterministic outputs are retained under
`artifacts/phase7/linked/` and reviewed with
`docs/phase7-grammar-linked-output-review-checklist.md`.

### Packaged grammar EPUB

The packaging layer consumes the already validated linked XHTML and a minimal
local vocabulary-only EPUB fixture. It does not rerun grammar or vocabulary
analysis and copies the four approved XHTML members byte-for-byte.

```bash
.venv/bin/python scripts/build_phase7_epub_fixture.py \
  --source-dir artifacts/phase7/linked/source-run-a \
  --output artifacts/phase7/epub/vocabulary-only.epub

.venv/bin/python scripts/package_grammar_epub.py \
  --input-epub artifacts/phase7/epub/vocabulary-only.epub \
  --linked-dir artifacts/phase7/linked/run-a \
  --output artifacts/phase7/epub/run-a.epub \
  --report artifacts/phase7/epub/run-a-report.json \
  --enabled
```

The synthetic package has eight members. Its spine and TOC order are the two
chapters, `Study Notes`, then `Grammar Study Notes`; the vocabulary and grammar
note layers remain separate. The checked-in synthetic package SHA-256 is
`df4c4bf0f072c01ac0a8d8aff316ee92613760c1822274cecd7ec9ce409a9619`.
It retains five grammar notes, seven contexts, three grammar links and matching
backlinks, five existing study links, and the publisher reading for 表舞台.

ZIP ordering, timestamps, permissions, and compression are fixed. Every
manifest, spine, navigation, XHTML, and fragment reference is validated before
writing. Packaging is opt-in; disabled or invalid operation copies the
vocabulary-only EPUB byte-for-byte and emits only a deterministic reason code.
No credentials, provider metadata, remote resources, source paths, OPF dumps,
or raw exceptions enter reports or reader content. The package remains a legal
synthetic mechanics fixture, not production approval of the grammar dataset or
the standalone synthetic `〜て` rule. Artifacts are retained under
`artifacts/phase7/epub/` and await the separate Calibre review documented in
`docs/phase7-packaged-epub-review-checklist.md`.

### Synthetic grammar evaluation

Phase 7 also provides an opt-in, deterministic evaluator for checked-in
synthetic ground truth. The corpus contains exactly 20 positive constructions
(four for each primary curated rule) and 13 negative confounders. One negative
is the explicitly excluded synthetic-mechanics competitor, leaving 12 scored
true negatives. Expected rule,
surface, source, token, and offset labels are fixture data; they are never
derived from detector output.

```bash
.venv/bin/python scripts/evaluate_grammar.py \
  --book artifacts/phase7/evaluation/run-a/inputs/book.json \
  --vocabulary artifacts/phase7/evaluation/run-a/inputs/vocabulary.json \
  --annotation-plan artifacts/phase7/evaluation/run-a/inputs/annotation-plan.json \
  --grammar-report artifacts/phase7/evaluation/run-a/inputs/grammar.json \
  --dataset tests/fixtures/phase7-grammar-rules-v1.json \
  --corpus tests/fixtures/phase7-evaluation-corpus-v1.json \
  --rule-control tests/fixtures/phase7-evaluation-control-v1.json \
  --output artifacts/phase7/evaluation/run-a/evaluation.json
```

Metrics are serialized as integer numerator/denominator pairs. The synthetic
baseline records 20 TP, 0 FP, 0 FN, and 12 TN, with 4/4 recall for each primary
rule. These perfect fixture metrics are regression evidence only and do not
claim production precision, recall, or rule approval.

Rule controls list explicit ordered `disabled_rule_ids` without editing the
curated dataset. The synthetic `〜て` mechanics rule is disabled in the default
profile and excluded from primary metrics. Disabling one primary rule excludes
only its four labeled positives; unaffected result records remain byte-identical.
Unknown, duplicate, stale, invalid, corrupt, or disabled inputs produce concise
safe diagnostics and no scored cases. Reports contain bounded case references,
not complete books, XHTML, EPUB content, credentials, provider data, paths,
caches, or raw exceptions. Evaluation artifacts are retained under
`artifacts/phase7/evaluation/` and reviewed with
`docs/phase7-grammar-evaluation-review-checklist.md`.

Phase 7 is complete: curated grammar detection, planning, standalone notes,
linked contexts, and EPUB packaging are deterministic and remain separate from
vocabulary, expressions, and proper names. Publisher ruby is authoritative,
overlap dispositions are conservative, and rules are independently disableable.
The synthetic evaluation records 20 TP, 0 FP, 0 FN, and 12 TN, but those perfect
fixture metrics do not establish production accuracy. The synthetic `〜て`
mechanics rule remains unapproved for production use.
