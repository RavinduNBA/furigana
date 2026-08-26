from uuid import UUID

from starlette.requests import Request

from furiganalyse.app import app, templates


def request(path="/"):
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 5000),
        "app": app,
    })


def test_upload_page_renders_self_contained_converter_and_capability_boundary():
    html = templates.get_template("upload.html").render({
        "request": request(),
        "supported_input_accept": ".azw3,.epub,.html,.mobi,.txt",
        "known_words_lists": [("JLPT_N5.csv", "JLPT N5", 723)],
        "dictionaries_ready": True,
    })

    assert 'accept=".azw3,.epub,.html,.mobi,.txt"' in html
    assert "Exclude JLPT N5 · 723 words" in html
    assert "Available in the web converter" in html
    assert "Dictionary Study EPUB" in html
    assert "Furigana + Dictionary Study" in html
    assert "Guided Reading EPUB" in html
    assert 'id="pipeline-guided"' in html
    assert "All eligible dictionary words" in html
    assert 'option value="0"' in html
    assert "Experimental adaptive assistance" in html
    assert "Dictionary-only initially" in html
    assert "Grammar remains off for personal books" in html
    assert "Bilingual companion" in html
    assert 'id="bilingual_companion"' in html
    assert 'id="bilingual_provider"' in html
    assert "EDRDG" in html
    assert '<script src="https://' not in html
    assert '<link href="https://' not in html


def test_job_page_renders_all_progress_metrics_and_safe_result_states():
    html = templates.get_template("download.html").render({
        "request": request("/jobs/00000000-0000-0000-0000-000000000000"),
        "uid": UUID("00000000-0000-0000-0000-000000000000"),
    })

    for element_id in (
        "conversion-progress", "progress-sections", "progress-characters",
        "progress-remaining", "progress-elapsed", "progress-eta", "progress-rate",
        "progress-size", "progress-words", "progress-matches", "result", "error",
        "bilingual-progress-panel", "progress-trans-model", "progress-trans-paragraphs",
        "progress-trans-cache", "bilingual-status-badge",
    ):
        assert f'id="{element_id}"' in html
    assert "LLM Bilingual Companion" in html
    assert "Why sections, not pages?" in html
    assert "Aggregate telemetry only" in html
    assert '<script src="https://' not in html
    assert '<link href="https://' not in html


def test_web_assets_have_no_remote_runtime_dependencies():
    for asset in ("assets/styles.css", "assets/upload.js", "assets/progress.js"):
        value = open(asset, encoding="utf-8").read()
        assert "https://" not in value
        assert "http://" not in value
        assert "jquery" not in value.lower()
        assert "bootstrap" not in value.lower()


def test_generate_output_filename_includes_mode():
    from furiganalyse.app import generate_output_filename
    from furiganalyse.params import OutputFormat

    assert generate_output_filename("my_book.epub", OutputFormat.epub, "furigana") == "my_book - Furigana.epub"
    assert generate_output_filename("my_book.epub", OutputFormat.epub, "study") == "my_book - Study.epub"
    assert generate_output_filename("my_book.epub", OutputFormat.epub, "combined") == "my_book - Combined.epub"
    assert generate_output_filename("my_book.epub", OutputFormat.epub, "guided") == "my_book - Guided.epub"
    assert generate_output_filename("furiganalysed_novel.azw3", OutputFormat.azw3, "furigana") == "novel - Furigana.azw3"


def test_recent_conversions_lifecycle_and_rendering(tmp_path):
    from furiganalyse.recent_conversions import load_recent_conversions, record_conversion

    # Record 12 items, verify only 10 are kept
    for i in range(12):
        record_conversion(
            tmp_path,
            uid=f"uid-{i:04d}",
            filename=f"book_{i}.epub",
            output_filename=f"book_{i} - Guided.epub",
            pipeline_mode="guided",
            status="complete" if i % 2 == 0 else "in_progress",
            output_bytes=1024 * 1024 * (i + 1),
        )

    recent = load_recent_conversions(tmp_path)
    assert len(recent) == 10
    # Most recent first
    assert recent[0]["uid"] == "uid-0011"
    assert recent[0]["pipeline_mode"] == "guided"
    assert recent[0]["output_filename"] == "book_11 - Guided.epub"

    # Render template with recent conversions
    html = templates.get_template("upload.html").render({
        "request": request(),
        "supported_input_accept": ".epub",
        "known_words_lists": [],
        "dictionaries_ready": True,
        "recent_conversions": recent,
    })
    assert "Recent conversions" in html
    assert "book_11 - Guided.epub" in html
    assert "Download" in html

