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
`artifacts/phase3/jmdict/`.

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

Without `--jmdict-index`, output remains the existing schema v1 tokenizer report.
With an index, schema v2 preserves all existing fields and adds ordered,
restriction-aware JMdict entry and sense matches. Each match retains entry and
sense IDs, written forms, readings, POS, restrictions, English glosses, and
dataset identity/version/SHA-256 provenance.

Tests use a tiny synthetic JMdict-compatible fixture; no production dictionary
is downloaded or committed. Production snapshots must be obtained and stored
locally according to their license, pinned with explicit identity/version, and
rebuilt when updated. This slice supports single-token JMdict lookup only:
JMnedict, expression matching, name classification, and sense ranking remain
future work.

The checked-in synthetic dataset provenance is
`furiganalyse-synthetic-jmdict`, version `2026-08-16`, index format 1, with
XML SHA-256
`b4952e87b430740d35bd4d5a50b463c764c12535d750ee9a18f5c0c848ad6deb`.
The strict schema-v2 golden is
`tests/phase3_golden/vocabulary-jmdict-v2.json`; compact reviewed expectations
are in `tests/phase3_golden/jmdict-review-cases-v2.json`.
