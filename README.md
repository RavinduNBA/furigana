<div align="center">

# 振 Furiganalyse
### Modern Japanese eBook Enhancement, Lexical Study & Series Memory Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/pytest-506%20passed-success.svg)](tests/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Production%20Ready-009688.svg)](https://fastapi.tiangolo.com/)

[**Live Web App ➔**](https://furigana.netceylon.xyz/) &nbsp;•&nbsp;
[**Series Memory Dashboard ➔**](https://furigana.netceylon.xyz/series) &nbsp;•&nbsp;
[**Ollama GPU Dashboard ➔**](https://furigana.netceylon.xyz/ollama)

<br/>

<img src="assets/furiganalyse.jpg" alt="Furiganalyse Banner" width="800" style="border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);" />

</div>

---

## 🌟 Overview

**Furiganalyse** transforms Japanese digital books (EPUB, AZW3, MOBI) into rich, interactive reading and language learning experiences. It blends **100% deterministic local morphological analysis** (MeCab + IPADIC + EDRDG JMdict/JMnedict) with **optional context-aware LLM intelligence** and a **persistent Series Memory database** for long-running light novel series.

Whether you want clean, broad furigana annotations on every kanji, interactive pop-up study notes, a curated function-word layer, side-by-side bilingual companion chapters, or canon-accurate character name pronunciation across a 30-volume series, Furiganalyse provides a modular, production-ready pipeline.

---

## 🚀 Core Features & Capabilities

```
                  ┌─────────────────────────────────────────────────────────┐
                  │                 Source Japanese EPUB                    │
                  └────────────────────────────┬────────────────────────────┘
                                               │
                                               ▼
     ┌───────────────────────────────────────────────────────────────────────────────────┐
     │ Phase 1: MeCab Morphological Tokenization & Deterministic Furigana Engine        │
     └─────────────────────────────────────────┬─────────────────────────────────────────┘
                                               │
                                               ▼
     ┌───────────────────────────────────────────────────────────────────────────────────┐
     │ Module 2: Publisher Ruby Propagation (Book-Wide Author Reading Extraction)        │
     └─────────────────────────────────────────┬─────────────────────────────────────────┘
                                               │
                                               ▼
     ┌───────────────────────────────────────────────────────────────────────────────────┐
     │ Phase 2 & 3: Local SQLite Dictionary Indexing (JMdict + JMnedict + Expressions)   │
     └─────────────────────────────────────────┬─────────────────────────────────────────┘
                                               │
                                               ▼
     ┌───────────────────────────────────────────────────────────────────────────────────┐
     │ Module 4: Proper Noun Furigana Disambiguation (Series Memory + JMnedict + LLM)    │
     └─────────────────────────────────────────┬─────────────────────────────────────────┘
                                               │
                                               ▼
     ┌───────────────────────────────────────────────────────────────────────────────────┐
     │ Module 3: Contextual Study Gloss Enrichment (Book Context + In-Universe Senses)  │
     └─────────────────────────────────────────┬─────────────────────────────────────────┘
                                               │
                                               ▼
     ┌───────────────────────────────────────────────────────────────────────────────────┐
     │ Phase 4-8: Interactive Linked XHTML Notes, Adaptive Density & Bilingual Companion │
     └─────────────────────────────────────────┬─────────────────────────────────────────┘
                                               │
                                               ▼
                  ┌─────────────────────────────────────────────────────────┐
                  │            Enhanced / Guided Reading EPUB               │
                  └─────────────────────────────────────────────────────────┘
```

### 1. 🈸 Furigana & Reading Assistance (Module 1 & 2)
* **Deterministic Furigana Engine**: Rule-based MeCab morphological segmentation and kana generation without network dependencies.
* **Writing Mode Adaptation**: Generates valid horizontal (`horizontal-tb`) and vertical (`vertical-rl`) EPUB layouts.
* **Publisher Ruby Preservation & Propagation (Module 2)**: Extracts author-assigned `<ruby>` readings (e.g., deliberate kanji ateji) and automatically propagates them to all unannotated occurrences book-wide.

### 2. 🧠 Series Memory Database & Lore Management (`/series`)
* **Persistent Series Profiles (`data/series/`)**: Tracks cumulative lore, character names, readings, speaking tones, character roles, world terminology, author ruby overrides, and plot memories across multi-volume series.
* **Deep Prompt Injection**: Injects canon cast sheets and world settings directly into LLM prompts for character reading disambiguation, contextual glossing, and bilingual translation.
* **Interactive Web Manager**: Dedicated web UI (`/series`) for searching, filtering, editing, and exporting series profiles as JSON.
* **One-Click Memory Extraction**: Save newly discovered characters and terminology from conversion results directly into Series Memory.

### 3. 🤖 Multi-Provider LLM Intelligence & Auto-Fallback
* **Google AI Studio / Gemini**: OpenAI-compatible endpoint with `gemini-flash-latest` (also supports `gemini-pro-latest`), with automatic API key resolution from `/root/furiganalyse/googleaistidioapi.txt` or `GEMINI_API_KEY`.
* **OpenRouter**: Access Claude 3.5/3.7, DeepSeek V3/R1, Qwen 2.5 72B, Llama 3.3, and free models (`nvidia/nemotron-3.5-lightning:free`), with automatic key fallback from `/root/furiganalyse/openrouterapi.txt` or `OPENROUTER_API_KEY`.
* **Hetzner GPU Cloud Inference**: High-speed cloud GPU endpoint (`Qwen/Qwen3.6-35B-A3B-FP8`).
* **Local Ollama**: Run completely offline with `qwen2.5:3b`, `qwen2.5:7b`, or custom models, accompanied by a real-time GPU/VRAM monitoring dashboard (`/ollama`).
* **OpenAI & DeepSeek Direct**: Native support for `gpt-4o-mini`, `gpt-4o`, `deepseek-chat`, and `deepseek-reasoner`.
* **Smart Auto-Fallback**: Automatically detects model deprecation or credit issues (HTTP 404/402), switching to working fallback models on the fly without failing conversions.

### 4. 📖 Guided Reading & Study Modes
* **Guided Reading EPUB**: Interactive popups on eligible vocabulary, multi-word expressions, character names, and a dedicated function-word layer (particles, auxiliaries, conjunctions) without nested links.
* **Deterministic Dictionary Study**: Lightweight per-chapter note pages (at most 25 items per page) linked cleanly to source sentences.
* **Adaptive Meaning Density**: Explainable N5–N1 learner density presets to reduce annotation clutter for known vocabulary.
* **Bilingual Companion**: Generates side-by-side or chapter-by-chapter bilingual Japanese/English volumes preserving narrative tone and character voice.

---

## 🛠️ Technology Stack

* **Backend & API**: Python 3.11+, [FastAPI](https://fastapi.tiangolo.com/), [Starlette](https://www.starlette.io/), [Uvicorn](https://www.uvicorn.org/)
* **NLP & Morphological Analysis**: `mecab-python3` (IPADIC), `furigana`, SQLite3 local dictionary indexes (JMdict, JMnedict)
* **Frontend**: Semantic HTML5, Vanilla CSS Design System (Light/Dark themes, responsive tables, modal dialogs), Vanilla JS (Fetch API, Server-Sent Events / WebSockets)
* **Database & Persistence**: Local JSON Series Storage Schema v2, SQLite EDRDG Indexes
* **Quality & Testing**: 506 unit & integration tests (`pytest`), automated Playwright browser test suite, deterministic byte-level EPUB golden regressions

---

## 📦 Installation & Setup

### Option 1: Local Virtual Environment (Recommended for Development)

```bash
# Clone repository
git clone https://github.com/RavinduNBA/furigana.git
cd furigana

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -U pip poetry
poetry install

# Run the test suite (506 tests)
pytest tests/ -q
```

### Option 2: Docker & Docker Compose

```bash
# Build Docker image
docker compose build

# Start the web server in background
docker compose up -d
```
Then open `http://127.0.0.1:5000` in your web browser.

---

## 💻 Running the Web Application

### Start Development Server
```bash
.venv/bin/uvicorn furiganalyse.app:app --host 127.0.0.1 --port 5000 --reload
```

### Production Deployment via Systemd (`furiganalyse.service`)
```bash
# Link systemd service
sudo ln -sfn /root/furiganalyse/deploy/furiganalyse.service /etc/systemd/system/furiganalyse.service
sudo systemctl daemon-reload
sudo systemctl enable --now furiganalyse.service

# Check status or restart
sudo systemctl status furiganalyse.service
sudo systemctl restart furiganalyse.service
```

---

## 🖥️ Command-Line Interface (CLI)

### 1. Basic Furigana Conversion
```bash
# Add furigana and output EPUB
.venv/bin/python -m furiganalyse input_book.epub output_book.epub

# Specify writing direction (horizontal-tb or vertical-rl)
.venv/bin/python -m furiganalyse input_book.epub output_book.epub --writing-mode horizontal-tb
```

### 2. Canonical Book Extraction (Phase 2)
Extract deterministic, versioned chapter and block JSON without modifying the source book:
```bash
.venv/bin/python scripts/extract_book.py input_book.epub analysis/book.json
```

### 3. Vocabulary & Proper Noun Analysis (Phase 3)
```bash
.venv/bin/python scripts/analyze_vocabulary.py input_book.epub analysis/vocabulary.json \
    --jmdict-index data/jmdict.sqlite3 \
    --jmnedict-index data/jmnedict.sqlite3 \
    --expressions
```

### 4. Build Guided Reading Study EPUB
```bash
.venv/bin/python scripts/create_study_plan.py analysis/vocabulary.json analysis/plan.json --per-chapter-limit 50
.venv/bin/python scripts/package_study_epub.py input_book.epub analysis/book.json analysis/plan.json output_guided.epub
```

---

## 🌐 API Reference

### Submit a Conversion Job
```bash
curl -X POST http://127.0.0.1:5000/submit \
    -F "file=@/path/to/book.epub" \
    -F "pipeline_mode=guided" \
    -F "furigana_mode=add" \
    -F "series_profile_id=mahouka" \
    -F "llm_provider=google" \
    -F "llm_enrich_nouns=true" \
    -F "llm_enrich_glosses=true"
```
**Response**:
```json
{
  "uid": "acccde09-22e4-4c1f-9adc-d2767dc8521d"
}
```

### Check Job Progress
```bash
curl http://127.0.0.1:5000/jobs/acccde09-22e4-4c1f-9adc-d2767dc8521d/status
```
**Response**:
```json
{
  "uid": "acccde09-22e4-4c1f-9adc-d2767dc8521d",
  "status": "in_progress",
  "progress": {
    "stage": "linked-rendering",
    "percent": 95,
    "characters_processed": 189795,
    "characters_total": 189795,
    "study_items": 9937,
    "elapsed_seconds": 95.0
  }
}
```

### Download Converted EPUB
```bash
curl -O http://127.0.0.1:5000/jobs/acccde09-22e4-4c1f-9adc-d2767dc8521d/file
```

### Series Memory CRUD API
* `GET /api/series`: List all series profiles.
* `GET /api/series/{series_id}`: Retrieve full profile JSON (characters, glossary, overrides, synopsis).
* `POST /api/series`: Create or merge updates into a series profile.
* `DELETE /api/series/{series_id}`: Delete a series profile.

---

## 🗂️ Project Structure

```
furiganalyse/
├── assets/                     # Frontend static assets
│   ├── styles.css              # Custom CSS design system (tokens, components, tables, modals)
│   ├── upload.js               # Converter UI state & options management
│   ├── download.js             # Real-time progress monitor & cast context handling
│   ├── series.js               # Series Memory dashboard client logic (CRUD & JSON export)
│   └── ollama.js               # Ollama dashboard client logic
├── data/                       # Local database & indexes
│   ├── series/                 # Persistent Series Memory JSON profiles (Schema v2)
│   ├── jmdict.sqlite3          # Local EDRDG JMdict SQLite index
│   └── jmnedict.sqlite3        # Local EDRDG JMnedict SQLite index
├── deploy/                     # Deployment configurations
│   ├── furiganalyse.service    # Systemd production unit definition
│   └── nginx.conf              # Production reverse-proxy configuration
├── furiganalyse/               # Core Python application package
│   ├── app.py                  # FastAPI/Starlette web application & routes
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
└── tests/                      # Comprehensive test suite (506 pytest unit tests)
    ├── test_series_glossary.py # Series Memory database & prompt builder tests
    ├── test_llm_providers.py   # Provider key resolution & fallback tests
    ├── test_web_ui.py          # End-to-end web routes & API tests
    └── ...                     # Phase 0-8 regression suites
```

---

## 🧪 Testing & Validation

Furiganalyse maintains a rigorous testing standard:

```bash
# Run the full automated test suite
.venv/bin/pytest tests/ -q

# Run specific test suites
.venv/bin/pytest tests/test_series_glossary.py -v
.venv/bin/pytest tests/test_llm_providers.py -v
.venv/bin/pytest tests/test_web_ui.py -v

# Run phase regression gates
./scripts/phase0-regression.sh
./scripts/phase1-regression.sh
./scripts/phase2-regression.sh
./scripts/phase3-regression.sh
```

---

## 📜 License & Acknowledgements

* **Furiganalyse** is licensed under the [MIT License](LICENSE).
* **Dictionary Data**: Uses data from the **Electronic Dictionary Research and Development Group (EDRDG)** [JMdict](http://www.edrdg.org/jmdict/j_jmdict.html) and [JMnedict](http://www.edrdg.org/enamdict/enamdict_doc.html) projects, used in accordance with the group's licence.
* **Morphological Analysis**: Powered by [MeCab](https://taku910.github.io/mecab/) and [IPADIC](https://osdn.net/projects/ipadic/).
