# Furiganalyse Light-Novel Learning Project

## 1. Purpose

This document is the source-of-truth implementation guide for extending Furiganalyse from a furigana converter into a Japanese light-novel reading assistant.

The product should help a learner read the original Japanese with the least necessary interruption. It should preserve the book, add reliable readings where useful, identify worthwhile vocabulary and grammar, and provide concise study notes that are easy to reach and easy to leave.

The project is not a machine-translation replacement and should not cover every sentence with English. The Japanese text remains primary. Dictionary data is authoritative; an LLM may later choose and phrase a context-appropriate sense, but must not invent lexical facts.

An explicit Guided Reading mode may cover every safely mappable Japanese token without turning the source chapter into interlinear English. It uses dictionary glosses for words and expressions, JMnedict for names, tokenizer lemmas/readings for form analysis, and curated functional notes for particles and auxiliaries. These are learning aids, not contextual sentence translations. A later opt-in bilingual companion may add model-generated paragraph translations as separate XHTML chapters while leaving the original Japanese untouched.

The central delivery rule is:

> Build one small, observable capability at a time. Do not begin the next phase until the current phase passes automated checks and a real EPUB has been inspected in Calibre.

Anki, elaborate learner modeling, large-scale LLM orchestration, and advanced UI work are intentionally outside the early critical path.

## 2. Product vision

For a selected learning item such as `怪訝`, the reading experience should eventually be:

- the original sentence and publisher formatting remain intact;
- the word displays its reading, when the learner needs it;
- the word links to a compact study note;
- the note shows `怪訝【けげん】`, a short meaning, its source sentence, and a backlink;
- the meaning may be context-specific but remains traceable to a JMdict sense;
- repeated occurrences receive less assistance as the learner becomes familiar with the item.

Definitions should normally be grouped at a chapter boundary or deterministic reading-chunk boundary. Reflowable EPUBs do not have stable screen pages, so “after each page” must not depend on device pagination. Existing publisher `pagebreak` markers may be supported when present.

## 3. Non-goals for early phases

Do not initially:

- rewrite Furiganalyse from scratch or replace its tokenizer without evidence;
- send a whole book to an LLM;
- allow an LLM to edit XHTML or generate EPUB markup;
- add English as a second ruby layer by default;
- implement grammar, adaptive repetition, Anki, and book-wide context together;
- build a complex database or distributed job system before local files are inadequate;
- alter publisher ruby merely to make it more regular;
- require an API key to produce a valid dictionary-only EPUB.

## 4. Architectural principles

### 4.1 Separate analysis from presentation

Use a pipeline with durable, inspectable intermediate data:

```text
input EPUB
  -> safe EPUB extraction and manifest/spine discovery
  -> XHTML traversal and canonical book model
  -> Japanese token and expression analysis
  -> dictionary/name lookup
  -> learning-item selection
  -> optional contextual enrichment
  -> annotation plan
  -> optional guided-reading token/function plan
  -> EPUB renderer
  -> optional separately authorized bilingual-companion renderer
  -> validation and Calibre inspection
```

The same analysis should later support EPUB, reports, HTML, and Anki without re-running unrelated work. Renderers consume structured records; they do not perform linguistic analysis.

### 4.2 Preserve identity and provenance

Every chapter, paragraph, sentence, token, occurrence, and note needs a deterministic ID. Every reading and meaning needs provenance such as `publisher`, `tokenizer`, `JMdict`, `JMnedict`, `book_glossary`, `LLM`, or `user`.

Suggested domain records:

```python
@dataclass
class RubyAnnotation:
    surface: str
    reading: str
    source: str  # publisher or generated

@dataclass
class VocabularyOccurrence:
    id: str
    surface: str
    lemma: str
    reading: str | None
    part_of_speech: str | None
    sentence_id: str
    chapter_id: str
    sentence_text: str
    dictionary_entry_id: str | None
    dictionary_sense_id: int | None
    dictionary_glosses: list[str]
    contextual_gloss: str | None
    gloss_source: str | None
    occurrence_number: int
    is_proper_noun: bool
```

Schema details may change, but stable IDs, offsets, provenance, and a versioned serialized format are required.

### 4.3 Deterministic core, optional enrichment

Given the same input, configuration, dictionary version, and disabled LLM, output should be reproducible. LLM results must be cached by model, prompt/schema version, target item, dictionary candidates, and context hash. If the LLM times out, rejects a request, or returns invalid data, generation continues with dictionary-only notes.

### 4.4 Preserve the EPUB before enhancing it

Operate only on spine content documents intended for reading. Preserve the package metadata, navigation, manifest relationships, CSS, images, fonts, IDs, links, namespaces, and document order. Avoid serializing untouched XHTML when possible because parsers can produce destructive formatting or namespace changes.

Reject unsafe archive paths during extraction. Preserve the EPUB `mimetype` packaging requirements. Validate links and unique IDs after rendering.

## 5. Existing publisher furigana

Publisher ruby is editorial content and is authoritative. It may encode names, fictional terminology, ateji, jukujikun, wordplay, or an intentionally non-dictionary reading.

Rules:

1. Detect complete existing ruby structures before passing text to morphological analysis.
2. Extract base text separately from `rt`/`rp` annotations. Reading text must never leak into the canonical sentence.
3. Record the publisher surface and reading as one annotation span, even when a tokenizer would split the surface differently.
4. In normal `add` mode, never replace, split, normalize, or nest ruby inside that span.
5. Generate furigana only for eligible uncovered text.
6. Keep explicit legacy `remove` or `replace` modes isolated and covered by regression tests; learning mode defaults to preservation.
7. If malformed or unsupported ruby is encountered, preserve its original markup and report a diagnostic rather than guessing.

Required regression example:

```text
表舞台【おもてぶたい】
```

must remain a single publisher annotation and must not become character-level readings such as `表おもて舞ぶ台たい`.

Test simple ruby, grouped ruby, `rp` fallbacks, nested emphasis/links around ruby, names with unusual readings, and ruby whose reading intentionally differs from a dictionary.

## 6. Dictionary and linguistic data

### JMdict

Use a local, indexed JMdict snapshot as the lexical backbone. Retain entry IDs, written forms, readings, parts of speech, restrictions, sense ordering, and English glosses. Record the dictionary release/version in analysis output.

Lookup must consider normalized lemma, surface inflection, reading, part of speech, and written/reading restrictions. It must return candidates rather than prematurely flattening all glosses into one definition.

After token lookup works, add longest-match expression lookup across adjacent tokens so entries such as `気がする` or `仕方がない` can be learned as units. Resolve overlapping candidates deterministically and keep enough evidence to debug the choice.

### JMnedict

Use JMnedict separately for people, places, organizations, and other proper names. Do not present literal kanji glosses for character names as ordinary vocabulary definitions. A useful name note is closer to `雪乃【ゆきの】 — Yukino, person name`.

Publisher readings and an explicit book glossary outrank generic name-dictionary candidates. Ambiguous name classification should be retained as uncertainty, not silently asserted.

### Furigana resources and tokenizer

Reuse the current Furiganalyse/furigana analysis path first. Expose and test its token boundaries, lemmas, readings, and parts of speech before considering a tokenizer replacement. JmdictFurigana or its JMnedict counterpart may help with word-level reading alignment, especially when readings cannot be divided kanji by kanji, but should be pinned and provenance-recorded like other datasets.

## 7. Context-aware LLM glossing

LLM enrichment is introduced only after dictionary-only notes work end-to-end.

The model receives bounded evidence:

- target surface, lemma, reading, and part of speech;
- previous, current, and next sentence;
- candidate JMdict entries and numbered senses;
- relevant book glossary entries and, later, selected earlier occurrences;
- a strict instruction to select an available sense or return “none”.

The model returns schema-validated data, never HTML:

```json
{
  "occurrence_id": "ch03-s018-v01",
  "selected_entry_id": "...",
  "selected_sense_id": 2,
  "context_gloss": "puzzled",
  "confidence": 0.92,
  "needs_review": false
}
```

Reject output that refers to a candidate not supplied, exceeds gloss length limits, or fails schema validation. Treat confidence as model metadata, not calibrated truth. Store prompt/schema versions for reproducibility and do not send the entire copyrighted book in each request.

Book context is a later, separate phase. Build it during a first pass as structured entities, recurring fictional terms, preferred translations, and concise chapter summaries. In a second pass, retrieve only relevant context. User-approved glossary terms and publisher readings outrank LLM suggestions. A repeated fictional term should receive a consistent preferred gloss across chapters.

## 8. EPUB study-note design

Default to conservative EPUB-compatible XHTML rather than English ruby. Advanced dual ruby may later be an experimental HTML/output mode after reader compatibility tests.

Each selected occurrence receives a stable source anchor and link:

```html
<a id="src-vocab-42" class="study-link"
   href="study-notes.xhtml#vocab-42">
  <ruby>熟達<rt>じゅくたつ</rt></ruby>
</a>
```

The generated notes document contains:

```html
<section id="vocab-42" class="study-note">
  <h2>熟達<span class="reading">【じゅくたつ】</span></h2>
  <p>mastery; proficiency</p>
  <blockquote>…source sentence…</blockquote>
  <p><a href="chapter-01.xhtml#src-vocab-42">← return to text</a></p>
</section>
```

Requirements:

- forward links and backlinks resolve inside the EPUB;
- source anchors are unique and deterministic;
- existing links/ruby remain valid; avoid illegal nested anchors;
- notes are added to manifest, spine, and navigation as appropriate;
- CSS is namespaced to avoid changing publisher layout;
- a chapter may have its own note document if that improves navigation and size;
- note generation can be disabled without changing linguistic analysis;
- the output opens and navigates correctly in Calibre, with at least one additional reading system tested before claiming broad compatibility.

### Guided Reading mode

Guided Reading is a separate processing mode, not a change to Furigana, Dictionary Study, or Combined behavior. It should optimize for uninterrupted story reading while making every safely analyzable unit inspectable:

- retain longest compatible JMdict expressions as source links;
- expose expression components inside the phrase note instead of creating nested source anchors;
- retain JMdict vocabulary and JMnedict proper names as distinct evidence kinds;
- explain particles, auxiliaries, conjunctions, adnominals, and interjections using a small versioned curated local function-word dataset;
- show surface, lemma, reading, part of speech, and bounded assistance without claiming an exact contextual translation;
- label unmatched Japanese tokens honestly rather than inventing meanings;
- preserve publisher ruby and existing anchors above every generated assistance decision;
- retain every token in the analytical plan even when protected markup prevents an independent source link.

Reflowable EPUB screen pages are unstable. Guided notes therefore use deterministic source-XHTML and sentence-group boundaries, with bounded note documents containing no more than a configured number of local items. A lightweight Guided Reading Notes index is added to navigation; selecting one word must never load a book-wide note document.

Source links must remain non-overlapping. When a dictionary phrase contains independently useful words or particles, the phrase owns the source span and its note lists the components. Never create nested anchors to simulate simultaneous phrase and word links.

### Future bilingual companion

Contextual translation is a later, separately enabled provider boundary. It should translate bounded sentence or paragraph groups and generate companion XHTML immediately after each original chapter, or under a clearly separate Translations navigation layer. It must not replace dictionary evidence, edit Japanese source XHTML, or run implicitly as part of Guided Reading.

Requirements include explicit opt-in before copyrighted text leaves the host, strict schema validation, canonical sentence references, cache keys containing source hash/model/prompt version, bounded retries, cost/token progress, deterministic fallback, and complete separation between source text, dictionary glosses, and model-authored translation. Provider failure must leave a valid provider-free Guided Reading EPUB.

## 9. Learner knowledge model

Reading knowledge and meaning knowledge are independent dimensions. Do not use one `known` Boolean.

```json
{
  "lemma": "適性",
  "reading_knowledge": "unknown",
  "meaning_knowledge": "known"
}
```

Rendering policy:

| Reading knowledge | Meaning knowledge | Furigana | Study note |
|---|---|---:|---:|
| unknown | known | yes | no |
| known | unknown | no | yes |
| unknown | unknown | yes | yes |
| known | known | no | no |

Publisher ruby is preserved regardless of this table. Early phases may use explicit lists and fixed configuration. Later states can include `new`, `seen`, `learning`, `known`, and `ignored`, with separate evidence and timestamps per dimension.

Annotation density should be a target, not a quota. A starting target such as roughly 10 learning items per 1,000 Japanese characters may be tested for an N4 learner, but usefulness and natural expression boundaries outrank filling a number. N-level presets are defaults, not claims that every learner knows the same words.

## 10. Phased implementation plan

Each phase should produce a reviewable artifact, automated tests, and a manual result. Stop if the gate fails.

### Phase 0 — Baseline, fixtures, and one-command regression

Build a tiny legal test EPUB with multiple chapters, navigation, CSS, image, punctuation, dialogue, emphasis, ordinary kanji, publisher ruby, unusual ruby, links, and non-Japanese text. Capture current behavior and add a repeatable unpack/inspect/validate test path.

Acceptance tests:

- fixture opens in Calibre before and after the existing conversion;
- text, chapter order, navigation, image, styling, punctuation, and links survive;
- EPUB structure and internal references pass available validators/checks;
- one documented command runs the regression suite;
- failures retain useful unpacked/debug artifacts.

Do not add vocabulary or LLM code in this phase.

### Phase 1 — Preserve publisher ruby

Introduce ruby-aware traversal and provenance while keeping ordinary conversion behavior stable.

Acceptance tests:

- publisher ruby is byte-equivalent where practical, otherwise semantically and structurally equivalent;
- generated ruby never overlaps or nests within preserved ruby;
- canonical visible text excludes `rt` and `rp` text;
- grouped and unusual ruby fixtures retain exact publisher readings;
- legacy add/remove/replace behavior has explicit regression coverage;
- manual Calibre comparison shows no publisher-ruby regressions.

### Phase 2 — Canonical book extraction

Create a versioned JSON analysis artifact: book, ordered chapters, blocks/paragraphs, sentences, text spans, existing ruby, source document, source anchors, and offsets. No dictionary, LLM, or note rendering.

Acceptance tests:

- extracted chapter/spine order matches the book;
- reconstructed visible text equals normalized original visible text;
- punctuation and paragraph boundaries survive;
- ruby readings are attached to spans but absent from sentence text;
- IDs and serialized output are deterministic across two runs;
- the sample passage can be manually traced from XHTML to JSON.

### Phase 3 — Vocabulary candidates and dictionary lookup report

Expose the existing tokenizer output, normalize inflections to lemmas, index JMdict, query JMnedict for name candidates, and produce a report only. Add expression matching after single-token lookup is reliable.

Acceptance tests:

- representative inflected verbs map to their dictionary forms;
- compounds and selected multi-token expressions map to appropriate entries;
- JMdict restrictions and parts of speech prevent obvious wrong matches;
- likely proper names are separated from ordinary vocabulary;
- every gloss is traceable to dataset version, entry, and sense;
- a manually reviewed gold set reports precision/coverage and known failure cases.

Do not yet write these results into the EPUB.

### Phase 4 — Dictionary-only clickable study notes

Select a small, configurable candidate set and render Calibre-friendly links, note entries, context sentences, and backlinks. Start with chapter grouping.

Acceptance tests:

- click a word in Calibre to reach the correct note;
- click the backlink to return to the exact source occurrence;
- generated IDs are unique and all links resolve;
- publisher ruby and layout remain intact;
- generation succeeds with no network or API key;
- a learner can read one complete chapter and report whether the notes are usable rather than noisy.

This is the first useful product milestone.

### Phase 5 — Local-context LLM sense selection

Add an optional provider interface, strict output schema, validation, retries with limits, caching, and dictionary-only fallback. Provide only adjacent sentence context and dictionary candidates.

Acceptance tests:

- manually review 20–50 deliberately ambiguous occurrences;
- selected senses always belong to supplied candidates or explicitly return none;
- invalid, unavailable, rate-limited, and timed-out calls cannot break EPUB generation;
- a second identical run uses the cache and produces equivalent notes;
- disabling LLM enrichment produces a valid dictionary-only EPUB;
- secrets never enter source control, logs, fixtures, or cached prompt records.

### Phase 6 — Book-wide context and terminology consistency

Add a separate first pass that identifies recurring entities and fictional terminology, producing an editable `book_context.json`. Retrieve only relevant entries for each occurrence.

Acceptance tests:

- selected recurring terms have consistent readings and glosses across chapters;
- publisher/user-approved glossary values override model output;
- rebuilding the same context is deterministic apart from explicitly cached enrichment;
- context can be manually edited and the changes are honored;
- local-only LLM mode from Phase 5 still works when book context is disabled.

### Phase 7 — Grammar expressions

Create a grammar-item type and detector independent of vocabulary. Begin with a small curated grammar dataset/rule set; use an LLM only for later disambiguation if evidence warrants it.

Acceptance tests:

- a fixture containing at least 20 known constructions measures true and false positives;
- overlapping vocabulary and grammar links do not create invalid XHTML;
- grammar notes are visually distinct and have working backlinks;
- enabling grammar does not change vocabulary-analysis results;
- noisy rules can be disabled independently.

### Phase 8 — Independent learner profile and adaptive density

Implement separate reading/meaning states, explicit overrides, level presets, occurrence exposure, and configurable density.

Acceptance tests:

- all four combinations in the rendering table behave correctly;
- publisher ruby is never removed by learner settings;
- explicit user overrides outrank presets and frequency heuristics;
- the same chapter produces meaningfully different, explainable N5/N4/N3 defaults;
- repeated exposure changes only the configured assistance dimension;
- selection reports explain why each item was included or excluded.

### Phase 9 — Guided Reading for every safe linguistic unit

Add a fourth provider-free processing mode over validated canonical, vocabulary, expression, name, and publisher-ruby records. Build a separate versioned guided-reading plan for uncovered function words and unmatched Japanese tokens. Keep longest expressions as source links and list their components in the phrase note. Render bounded source-local note pages and a lightweight navigation index.

Acceptance tests:

- existing Furigana, Dictionary Study, Combined, Phase 3–8 reports, and approved EPUB outputs remain unchanged;
- every safely mapped Japanese token is represented by dictionary, expression, name, function-word, unmatched, component-only, or protected-markup evidence;
- common particles and auxiliaries receive curated functional explanations without being misclassified as vocabulary;
- expression components are visible without nested or overlapping source links;
- note pages have deterministic item/size bounds and selecting one word never loads a book-wide note layer;
- all forward links, backlinks, IDs, manifests, spine entries, and navigation targets resolve;
- publisher ruby, canonical visible text, existing emphasis, and unrelated links remain unchanged;
- no provider, SDK, model, network lookup, or contextual-translation claim is involved;
- the legal fixture and a personal large EPUB are inspected for opening, movement, popup, and backlink responsiveness.

### Phase 10 — Optional bilingual LLM companion chapters

Add an explicit provider interface over canonical sentence/paragraph batches. Produce schema-validated translation records first, then separate companion XHTML without editing original chapters. Cache by canonical content hash, provider, model, prompt/schema version, and translation policy.

Acceptance tests:

- provider use requires explicit enablement and credentials supplied outside files and logs;
- original Japanese, publisher ruby, dictionary notes, and Guided Reading notes remain unchanged;
- each translation paragraph maps exactly to ordered canonical source references;
- invalid, unavailable, rate-limited, or interrupted calls fail safely without a partially translated EPUB;
- cached identical runs avoid provider calls and produce equivalent companion chapters;
- navigation clearly distinguishes original chapters, Guided Reading Notes, and model-authored translations;
- progress records batches, sentences, characters, cache hits, estimated tokens, and estimated cost without logging book text;
- manual review records translation usefulness, omissions, terminology consistency, and model limitations rather than claiming objective correctness.

### Phase 11 — Optional Anki export

Keep Anki as an adapter over existing analysis records. Generate candidate cards rather than silently exporting every unknown word. Include word, reading, source sentence, dictionary sense, contextual gloss, book/chapter, and stable source ID.

Acceptance tests:

- generate and manually import a small deck of approximately ten cards;
- Unicode, formatting, fields, and tags render correctly;
- regeneration has stable IDs and does not create avoidable duplicates;
- EPUB generation and all earlier phases work with Anki disabled;
- no Anki-specific state leaks into core analysis.

## 11. Testing strategy

Maintain three levels:

1. Unit tests for ruby parsing, normalization, dictionary restrictions, candidate ranking, stable IDs, schemas, and link generation.
2. Golden/integration tests using the tiny EPUB and checked-in expected JSON/structural assertions. Avoid brittle comparisons of irrelevant ZIP timestamps or serializer whitespace.
3. Manual reader tests in Calibre after every EPUB-writing phase. Record the application/version, book fixture, checklist, and result.

Add property/invariant checks where useful: no duplicate IDs, no unresolved internal links, no nested anchors, no analysis span outside its source text, no publisher ruby overlap, and no annotation text included in canonical Japanese text.

Use a small reviewed corpus of light-novel-like sentences for vocabulary and grammar evaluation. Keep copyrighted production books out of the repository, CI artifacts, logs, and bug reports.

## 12. Configuration and data layout

Prefer clear files until a database is justified:

```text
config/
  learning.yaml
data/                       # downloaded/pinned datasets; normally not committed
analysis/<book-id>/
  book.json
  vocabulary.json
  book_context.json
  enrichment-cache.jsonl
reports/<book-id>/
tests/fixtures/
tests/golden/
```

Configuration should eventually cover:

- ruby mode and learner thresholds;
- vocabulary/grammar enablement and density;
- chapter, reading-chunk, or publisher-pagebreak grouping;
- dictionary paths and versions;
- LLM provider/model, disabled by default in tests;
- cache and output paths;
- log verbosity and privacy-safe diagnostics.

Do not commit generated books, private learner profiles, API keys, model prompts containing copyrighted passages, or downloaded dictionary data unless licensing and repository policy explicitly allow it.

## 13. VPS development and deployment workflow

GitHub should remain the source of truth. Develop through small branches and pull requests with one phase or tightly scoped slice per change. The VPS is a reproducible staging environment, not the only copy of working state.

Recommended flow:

```text
feature branch -> local/unit tests -> CI fixture tests
  -> merge/deploy candidate -> VPS staging
  -> upload test EPUB -> download result -> inspect in Calibre
  -> record acceptance result -> begin next phase
```

VPS guidance:

- create a dedicated non-root deployment user with access only to the application and required container/runtime resources;
- use SSH keys or CI deployment credentials; never paste passwords or private keys into chat or commit them;
- pin runtime and dictionary versions, preferably with Docker/Compose once the baseline is understood;
- keep secrets in VPS/CI secret storage and provide a committed `.env.example` with names only;
- separate staging data, uploads, generated books, caches, and logs from the source checkout;
- set upload size, job timeout, concurrency, and disk-retention limits;
- do not expose development/debug endpoints publicly;
- use HTTPS and authentication before processing private books over a network;
- back up only irreplaceable configuration/profile data; builds and caches should be reproducible;
- provide a health check and a documented rollback to the previous known-good image/revision.

Start deployment automation only after Phase 0 can run locally. A minimal repeatable staging deployment is preferable to a large production platform.

## 14. Concrete guidance for Codex

Before changing code:

1. Read repository instructions, README, dependency files, entry points, EPUB parsing/rendering code, tests, and current add/remove/replace ruby behavior.
2. Run the current tests and a baseline conversion. Record failures that predate the change.
3. Map the actual code to this document; do not assume names or modules described here already exist.
4. State which single phase and acceptance criterion the change addresses.

For each implementation slice:

- keep the diff small enough to review and revert;
- add or update a failing test before/following the implementation as appropriate;
- preserve public behavior unless the phase explicitly changes it;
- prefer pure transformations and typed domain records at analysis boundaries;
- isolate external tools, dictionaries, EPUB packaging, and model providers behind narrow interfaces;
- never let the LLM manipulate files or XHTML directly;
- include provenance and deterministic IDs at creation time;
- log decisions using IDs and reasons, not full private book contents;
- add dependencies only when their role, license, size, and deployment impact are understood;
- do not perform a tokenizer/framework/database rewrite as incidental cleanup;
- update this document if an agreed architectural decision changes.

After each slice:

1. Run focused tests, then the complete relevant suite.
2. Inspect the generated analysis/report or unpacked EPUB rather than relying only on exit status.
3. Run EPUB structural/link validation.
4. For rendering changes, produce the fixture output and complete the Calibre checklist.
5. Report exactly which acceptance criteria passed, what remains, and any newly documented limitations.
6. Stop at the phase boundary and request human verification before broadening scope.

Suggested first Codex task:

> Implement Phase 0 only. Inspect the current repository, create the smallest representative EPUB fixture and one-command regression workflow, capture baseline behavior, and document how to verify the output in Calibre. Do not add vocabulary, dictionaries, LLM calls, learner profiles, grammar, or Anki changes.

## 15. Definition of done

A phase is done only when:

- its listed automated acceptance tests pass;
- a reviewable artifact demonstrates the feature;
- relevant output has been manually checked in Calibre;
- security/privacy and fallback behavior have been considered;
- limitations and dataset/tool versions are documented;
- no unrelated later-phase machinery was added “for completeness”.

The project succeeds by accumulating trustworthy layers. A smaller feature with observable inputs, outputs, and fallbacks is more valuable than a broad pipeline whose errors cannot be located.
