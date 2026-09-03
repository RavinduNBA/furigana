<div align="center">

# 振 Furiganalyse
### Next-Generation Japanese eBook Enhancement, Lexical Study & Series Memory Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Production%20Ready-009688.svg)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/pytest-506%20passed-brightgreen.svg)](tests/)

[**Live Web Application ➔**](https://furigana.netceylon.xyz/) &nbsp;•&nbsp;
[**Series Memory Dashboard ➔**](https://furigana.netceylon.xyz/series) &nbsp;•&nbsp;
[**Local Ollama Dashboard ➔**](https://furigana.netceylon.xyz/ollama)

<br/>

<img src="assets/furiganalyse.jpg" alt="Furiganalyse Hero Banner" width="800" style="border-radius: 12px; box-shadow: 0 8px 30px rgba(0,0,0,0.12);" />

</div>

---

## 🌟 Introduction

**Furiganalyse** is a modern, high-performance Japanese eBook processing and language-learning platform designed for readers of light novels, web novels, and literature.

It combines **100% deterministic local morphological analysis** (MeCab + IPADIC + offline EDRDG JMdict/JMnedict dictionaries) with an **intelligent Series Memory database** and **multi-provider LLM integrations** to solve complex reading challenges:
* Preserving and propagating author-intended readings (ateji).
* Disambiguating obscure character and family names across multi-volume series.
* Providing in-universe, context-aware lexical glosses.
* Generating clean, interactive popup study notes and bilingual companion volumes without DRM artifacts.

---

## 🏗️ Architectural Overview

Furiganalyse operates on a modular, multi-phase pipeline designed for deterministic execution, high throughput, and zero data leakage:

```
                            ┌──────────────────────────────────────────────┐
                            │              Source Japanese EPUB            │
                            └──────────────────────┬───────────────────────┘
                                                   │
                                                   ▼
                ┌──────────────────────────────────────────────────────────────────────┐
                │ Phase 1: MeCab Morphological Tokenization & Furigana Engine          │
                │ • Full ruby annotation (horizontal-tb or vertical-rl)                │
                │ • Strict preservation of existing publisher-assigned ruby           │
                └──────────────────────────────────┬───────────────────────────────────┘
                                                   │
                                                   ▼
                ┌──────────────────────────────────────────────────────────────────────┐
                │ Module 2: Publisher Ruby Extraction & Propagation                   │
                │ • Extracts author-assigned special readings (ateji)                  │
                │ • Automatically propagates readings to unannotated instances book-wide│
                └──────────────────────────────────┬───────────────────────────────────┘
                                                   │
                                                   ▼
                ┌──────────────────────────────────────────────────────────────────────┐
                │ Phase 2 & 3: Local SQLite Dictionary Indexing                        │
                │ • Exact JMdict word sense lookup & multi-word expression matching   │
                │ • JMnedict proper noun & entity classification                       │
                └──────────────────────────────────┬───────────────────────────────────┘
                                                   │
                                                   ▼
                ┌──────────────────────────────────────────────────────────────────────┐
                │ Module 4: Proper Noun Furigana Disambiguation                        │
                │ • Resolves unindexed character names and world terms                 │
                │ • Cross-references Series Memory + LLM Context                       │
                └──────────────────────────────────┬───────────────────────────────────┘
                                                   │
                                                   ▼
                ┌──────────────────────────────────────────────────────────────────────┐
                │ Module 3: Contextual Study Gloss Enrichment                          │
                │ • Replaces generic dictionary definitions with in-universe meanings  │
                │ • Deep prompt injection using Series Memory synopsis & cast sheets   │
                └──────────────────────────────────┬───────────────────────────────────┘
                                                   │
                                                   ▼
                ┌──────────────────────────────────────────────────────────────────────┐
                │ Phase 4–8: Interactive XHTML Linking & EPUB Packaging                │
                │ • Guided Reading notes layer (function words & grammar notes)        │
                │ • Adaptive density presets (N5–N1 learner filters)                   │
                │ • Bilingual companion chapter generation (optional)                  │
                └──────────────────────────────────┬───────────────────────────────────┘
                                                   │
                                                   ▼
                            ┌──────────────────────────────────────────────┐
                            │        Enhanced / Guided Reading EPUB        │
                            └──────────────────────────────────────────────┘
```

---

## ✨ Key Features

### 🈸 1. Deterministic Furigana Engine & Ruby Propagation
* **Full-Book Morphological Analysis**: Powered by MeCab and IPADIC for accurate kana readings.
* **Layout Awareness**: Supports modern horizontal (`horizontal-tb`) and traditional Japanese vertical (`vertical-rl`) writing modes.
* **Publisher Ruby Propagation (Module 2)**: Detects special author-assigned kanji readings (e.g. 表舞台 $\rightarrow$ 「ステージ」) and propagates them throughout the entire text automatically.

### 🧠 2. Series Memory Local Database (`/series`)
* **Cumulative Series Storage (`data/series/`)**: Tracks character rosters (kanji, reading, romanized name, role, speaking tone, aliases), world glossaries, magic rules, author ruby overrides, and plot memories.
* **Deep Prompt Injection**: Formats dense markdown lore sheets automatically injected into model system prompts for translation and furigana resolution.
* **Full CRUD Management Dashboard**: Dedicated web interface at [`/series`](https://furigana.netceylon.xyz/series) to manage, search, edit, create, and export series profiles as JSON.
* **One-Click Memory Extraction**: Save newly discovered characters and terminology from book conversion results directly into Series Memory.

### 🤖 3. Multi-Provider LLM Intelligence with Auto-Fallback
* **Supported Backends**:
  * **Google AI Studio (Gemini)**: OpenAI-compatible endpoint with `gemini-flash-latest` (auto-resolves API key from `googleaistidioapi.txt` or `GEMINI_API_KEY`).
  * **OpenRouter**: Access Claude 3.5/3.7, DeepSeek, Qwen 2.5 72B, and free tier endpoints (`nvidia/nemotron-3.5-lightning:free`), auto-resolving from `openrouterapi.txt` or `OPENROUTER_API_KEY`.
  * **Hetzner Inference (GPU Cloud)**: Fast, high-throughput cloud GPU inference (`Qwen/Qwen3.6-35B-A3B-FP8`).
  * **Local Ollama**: Run completely private models (`qwen2.5:3b`, `qwen2.5:7b`) with live GPU/VRAM monitoring on [`/ollama`](https://furigana.netceylon.xyz/ollama).
  * **OpenAI & DeepSeek Direct**: Native support for `gpt-4o-mini`, `gpt-4o`, `deepseek-chat`, and `deepseek-reasoner`.
* **Smart Auto-Recovery**: Intercepts HTTP 404/402 errors (e.g. deprecated model identifiers or exhausted credits) and switches automatically to verified fallback models on the fly.

### 📚 4. Guided Reading & Study Notes
* **Interactive Popup Notes**: Generates non-intrusive interactive popups for vocabulary, multi-word expressions, and proper nouns.
* **Function Word & Grammar Notes**: Annotates particles, auxiliaries, conjunctions, and interjections in a distinct layer without nested link collisions.
* **Adaptive Density (N5–N1)**: Bounded learner presets to hide annotations for vocabulary already known to the reader.
* **Bilingual Companion EPUB**: Generates dual-language side-by-side or chapter-by-chapter reading volumes while maintaining character voices.

---

## 🚀 Getting Started

### Prerequisites
* Python 3.11 or higher
* [Poetry](https://python-poetry.org/) (optional, recommended) or standard `pip` / `venv`
* [MeCab](https://taku910.github.io/mecab/) and IPADIC dictionary binaries

### Quick Installation

```bash
# Clone the repository
git clone https://github.com/RavinduNBA/furigana.git
cd furigana

# Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install poetry
poetry install

# Verify installation with test suite (506 tests)
pytest tests/ -q
```

---

## 🌐 Running the Web Application

### Start Local Development Server
```bash
.venv/bin/uvicorn furiganalyse.app:app --host 127.0.0.1 --port 5000 --reload
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

### Production Deployment via Systemd
The service file is pre-configured in [`deploy/furiganalyse.service`](deploy/furiganalyse.service):

```bash
# Link systemd unit
sudo ln -sfn /root/furiganalyse/deploy/furiganalyse.service /etc/systemd/system/furiganalyse.service
sudo systemctl daemon-reload
sudo systemctl enable --now furiganalyse.service

# Restart or check status
sudo systemctl restart furiganalyse.service
sudo systemctl status furiganalyse.service
```

---

## 💻 Command Line Interface (CLI)

### 1. Basic Furigana Generation
```bash
# Add furigana with automatic writing direction detection
.venv/bin/python -m furiganalyse input.epub output_furigana.epub

# Specify explicit writing mode (horizontal-tb or vertical-rl)
.venv/bin/python -m furiganalyse input.epub output_furigana.epub --writing-mode vertical-rl
```

### 2. Extract Canonical Book Structure (Phase 2)
Extract deterministic JSON representation of chapters, sentences, and block structures:
```bash
.venv/bin/python scripts/extract_book.py input.epub analysis/book.json
```

### 3. Analyze Vocabulary & Proper Names (Phase 3)
```bash
.venv/bin/python scripts/analyze_vocabulary.py input.epub analysis/vocabulary.json \
    --jmdict-index data/jmdict.sqlite3 \
    --jmnedict-index data/jmnedict.sqlite3 \
    --expressions
```

### 4. Package Guided Study EPUB
```bash
.venv/bin/python scripts/create_study_plan.py analysis/vocabulary.json analysis/plan.json --per-chapter-limit 50
.venv/bin/python scripts/package_study_epub.py input.epub analysis/book.json analysis/plan.json output_guided.epub
```

---

## 📡 REST API Reference

### 1. Submit Conversion Job
```bash
curl -X POST http://127.0.0.1:5000/submit \
  -F "file=@/path/to/novel.epub" \
  -F "pipeline_mode=guided" \
  -F "furigana_mode=add" \
  -F "series_profile_id=mahouka" \
  -F "llm_provider=google" \
  -F "llm_enrich_nouns=true" \
  -F "llm_enrich_glosses=true"
```
**Response:**
```json
{
  "uid": "acccde09-22e4-4c1f-9adc-d2767dc8521d"
}
```

### 2. Check Conversion Progress
```bash
curl http://127.0.0.1:5000/jobs/acccde09-22e4-4c1f-9adc-d2767dc8521d/status
```
**Response:**
```json
{
  "uid": "acccde09-22e4-4c1f-9adc-d2767dc8521d",
  "status": "complete",
  "progress": {
    "stage": "complete",
    "percent": 100,
    "sections_completed": 31,
    "sections_total": 31,
    "characters_processed": 189795,
    "characters_total": 189795,
    "study_items": 9937,
    "elapsed_seconds": 95.0
  }
}
```

### 3. Download Converted Book
```bash
curl -O http://127.0.0.1:5000/jobs/acccde09-22e4-4c1f-9adc-d2767dc8521d/file
```

### 4. Series Memory API
* `GET /api/series`: List all series profiles.
* `GET /api/series/{series_id}`: Get full series profile JSON.
* `POST /api/series`: Create or update a series profile.
* `DELETE /api/series/{series_id}`: Delete a series profile.

---

## 📁 Repository Structure

```
furiganalyse/
├── assets/                     # Frontend UI assets (CSS tokens, components, JavaScript)
│   ├── styles.css              # Modern responsive CSS design system (Dark & Light)
│   ├── upload.js               # Converter UI state & options management
│   ├── download.js             # Live progress monitor & cast context handling
│   ├── series.js               # Series Memory dashboard client logic (CRUD & JSON export)
│   └── ollama.js               # Ollama dashboard client logic
├── data/                       # Local database & indexes
│   ├── series/                 # Persistent Series Memory JSON database (Schema v2)
│   ├── jmdict.sqlite3          # Local EDRDG JMdict SQLite index
│   └── jmnedict.sqlite3        # Local EDRDG JMnedict SQLite index
├── deploy/                     # Production server configuration
│   ├── furiganalyse.service    # Systemd production unit definition
│   └── nginx.conf              # Production reverse-proxy configuration
├── furiganalyse/               # Core Python application package
│   ├── app.py                  # FastAPI/Starlette web app & routing
│   ├── auth.py                 # Session authentication & security
│   ├── bilingual_context.py    # Bilingual prompt building & cast coordination
│   ├── bilingual_epub.py       # Bilingual EPUB packaging & layout generation
│   ├── contextual_gloss.py     # Module 3 contextual study note enrichment
│   ├── llm_provider.py         # Multi-provider LLM client with auto-fallback
│   ├── proper_noun_resolver.py # Module 4 proper noun furigana correction
│   ├── recent_conversions.py   # Recent job history & storage management
│   ├── ruby_override.py        # Module 2 author ruby propagation & overrides
│   ├── series_glossary.py      # Series Memory database & prompt context builder
│   ├── web_study_pipeline.py   # Core conversion orchestration pipeline
│   └── templates/              # Jinja2 HTML templates
│       ├── upload.html         # Main converter homepage
│       ├── download.html       # Live progress & job completion page
│       ├── series.html         # Series Memory management dashboard
│       ├── ollama.html         # Ollama dashboard
│       └── login.html          # Authentication login page
├── scripts/                    # CLI utilities & regression runners
│   ├── extract_book.py         # Phase 2 canonical extraction utility
│   ├── analyze_vocabulary.py   # Phase 3 vocabulary analysis CLI
│   └── rebuild_all.py          # Full pipeline rebuild & benchmark runner
└── tests/                      # Automated test suite (506 pytest unit tests)
    ├── test_series_glossary.py # Series Memory database & prompt builder tests
    ├── test_llm_providers.py   # Provider key resolution & fallback tests
    ├── test_web_ui.py          # End-to-end web routes & API tests
    └── ...                     # Phase 0-8 regression suites
```

---

## 🧪 Testing & Validation

The codebase is tested across all pipeline phases with 506 unit and integration tests:

```bash
# Run all tests
pytest tests/ -q

# Run specific functional test suites
pytest tests/test_series_glossary.py -v
pytest tests/test_llm_providers.py -v
pytest tests/test_web_ui.py -v

# Run individual phase regression gates
./scripts/phase0-regression.sh
./scripts/phase1-regression.sh
./scripts/phase2-regression.sh
./scripts/phase3-regression.sh
```

---

## ⚖️ License & Acknowledgements

* **License**: This project is licensed under the [MIT License](LICENSE).
* **Attribution & Inspiration**: This project was inspired by and built upon concepts from the original [`furiganalyse`](https://github.com/itsupera/furiganalyse) project by [@itsupera](https://github.com/itsupera).
* **Dictionary Data**: Uses dictionary data from the **Electronic Dictionary Research and Development Group (EDRDG)** [JMdict](http://www.edrdg.org/jmdict/j_jmdict.html) and [JMnedict](http://www.edrdg.org/enamdict/enamdict_doc.html) projects, used in accordance with the group's licence.
* **Morphological Analysis**: Powered by [MeCab](https://taku910.github.io/mecab/) and [IPADIC](https://osdn.net/projects/ipadic/).
