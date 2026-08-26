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
    assert "Experimental adaptive assistance" in html
    assert "Dictionary-only initially" in html
    assert "Grammar remains off for personal books" in html
    assert "EDRDG" in html
    assert "No provider or model calls" in html
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
    ):
        assert f'id="{element_id}"' in html
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
