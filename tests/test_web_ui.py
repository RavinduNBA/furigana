from uuid import UUID

import pytest
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
        "progress-trans-cache", "bilingual-status-badge", "cancel-button", "cancelled",
        "live-trans-stream", "stream-japanese-text", "stream-english-text", "stream-chapter-tag",
        "discovered-context-panel", "cast-chips-row", "glossary-chips-row",
        "main-download-card", "bilingual-download-card",
        "backend-console-card", "backend-console-logs",
    ):
        assert f'id="{element_id}"' in html
    assert "LLM Bilingual Companion" in html
    assert "Live Translation Stream" in html
    assert "Discovered Cast &amp; Terminology Context" in html
    assert "Backend Pipeline Live Console" in html
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


def test_recent_conversions_deletion_and_orphan_cleanup(tmp_path):
    from furiganalyse.recent_conversions import (
        cleanup_orphaned_conversions,
        record_conversion,
        remove_recent_conversion,
    )

    # 1. Record an in_progress job and an active scratch folder
    uid = "test-uid-1234"
    task_dir = tmp_path / uid
    task_dir.mkdir(parents=True)
    (task_dir / "study-work").mkdir()
    (task_dir / "study-work" / "temp.txt").write_text("scratch", encoding="utf-8")
    (task_dir / "furigana-stage.epub").write_text("stage", encoding="utf-8")

    record_conversion(
        tmp_path,
        uid=uid,
        filename="book.epub",
        output_filename="book - Guided.epub",
        pipeline_mode="guided",
        status="in_progress",
    )

    # 2. Test orphan cleanup marks status as stopped and purges scratch work
    items = cleanup_orphaned_conversions(tmp_path)
    assert len(items) == 1
    assert items[0]["status"] == "stopped"
    assert not (task_dir / "study-work").exists()
    assert not (task_dir / "furigana-stage.epub").exists()

    # 3. Test removing conversion deletes history entry and task folder
    remaining = remove_recent_conversion(tmp_path, uid)
    assert len(remaining) == 0
    assert not task_dir.exists()


@pytest.mark.anyio
async def test_job_cancellation_handler(tmp_path, monkeypatch):
    import uuid
    from furiganalyse.app import Job, cancel_job_handler, jobs

    uid = uuid.uuid4()
    job = Job(uid=uid)
    jobs[uid] = job

    task_dir = tmp_path / str(uid)
    task_dir.mkdir(parents=True)
    (task_dir / "study-work").mkdir()

    monkeypatch.setattr("furiganalyse.app.OUTPUT_FOLDER", str(tmp_path))

    resp = await cancel_job_handler(uid)
    assert resp["status"] == "cancelled"
    assert job.status == "cancelled"
    assert not (task_dir / "study-work").exists()


def test_early_main_download_serves_converted_file_not_input(tmp_path, monkeypatch):
    import json
    import uuid
    from pathlib import Path
    from furiganalyse.app import Job, encode_filepath, get_file, jobs

    uid = uuid.uuid4()
    task_dir = tmp_path / str(uid)
    task_dir.mkdir(parents=True)

    # Place original uploaded input file
    input_file = task_dir / "my_book.epub"
    input_file.write_text("ORIGINAL RAW UNPROCESSED INPUT", encoding="utf-8")

    # Place converted guided output file
    output_file = task_dir / "my_book - Guided.epub"
    output_file.write_text("CONVERTED GUIDED EPUB WITH RUBY & NOTES", encoding="utf-8")

    progress_file = task_dir / "progress.json"
    progress_file.write_text(json.dumps({
        "stage": "bilingual-translation",
        "main_file_ready": True,
    }), encoding="utf-8")

    job = Job(
        uid=uid,
        status="in_progress",
        result=encode_filepath(str(output_file)),
        progress_path=str(progress_file),
    )
    jobs[uid] = job

    monkeypatch.setattr("furiganalyse.app.OUTPUT_FOLDER", str(tmp_path))

    response = get_file(uid)
    assert response.status_code == 200
    assert response.path == str(output_file)
    assert response.filename == "my_book - Guided.epub"
    assert Path(response.path).read_text(encoding="utf-8") == "CONVERTED GUIDED EPUB WITH RUBY & NOTES"


def test_clear_all_recent_conversions(tmp_path, monkeypatch):
    from furiganalyse.recent_conversions import (
        record_conversion,
        load_recent_conversions,
        clear_all_recent_conversions,
        remove_recent_conversion,
    )

    record_conversion(
        output_folder=tmp_path,
        uid="job-1",
        filename="test1.epub",
        furigana_mode="add",
        output_filename="test1_out.epub",
        status="complete",
        pipeline_mode="study",
        output_bytes=100,
    )
    record_conversion(
        output_folder=tmp_path,
        uid="job-2",
        filename="test2.epub",
        furigana_mode="add",
        output_filename="test2_out.epub",
        status="complete",
        pipeline_mode="guided",
        output_bytes=200,
    )

    task1 = tmp_path / "job-1"
    task1.mkdir(exist_ok=True)
    (task1 / "test1.epub").write_text("dummy", encoding="utf-8")

    task2 = tmp_path / "job-2"
    task2.mkdir(exist_ok=True)
    (task2 / "test2.epub").write_text("dummy", encoding="utf-8")

    items = load_recent_conversions(tmp_path)
    assert len(items) == 2

    # Remove single item
    items_after_remove = remove_recent_conversion(tmp_path, "job-1")
    assert len(items_after_remove) == 1
    assert items_after_remove[0]["uid"] == "job-2"
    assert not task1.exists()
    assert task2.exists()

    # Clear all
    items_after_clear = clear_all_recent_conversions(tmp_path)
    assert items_after_clear == []
    assert load_recent_conversions(tmp_path) == []
    assert not task2.exists()


def test_series_dashboard_and_api(tmp_path, monkeypatch):
    import furiganalyse.series_glossary as sg
    from furiganalyse import auth
    from starlette.testclient import TestClient
    from furiganalyse.app import app

    monkeypatch.setattr(sg, "DEFAULT_STORAGE_DIR", tmp_path / "series")

    token = auth.create_session_token("testadmin")
    client = TestClient(app, cookies={"furiganalyse_session": token})

    # Check GET /series
    resp = client.get("/series")
    assert resp.status_code == 200
    assert "Series Memory &amp; Lore Database" in resp.text

    # Post new series profile
    resp_post = client.post("/api/series", json={
        "series_id": "test-series",
        "title": "Test Series Title",
        "synopsis": "A fantasy world...",
        "world_setting": "Magic circuits...",
        "characters": {
            "主人公": {"kanji": "主人公", "reading": "しゅじんこう", "role": "Hero"}
        },
        "glossary": {
            "魔法": {"japanese": "魔法", "preferred_translation": "Magic"}
        },
        "ruby_overrides": {"術式": "じゅつしき"}
    })
    assert resp_post.status_code == 200
    assert resp_post.json()["series_id"] == "test-series"

    # Get single profile
    resp_get = client.get("/api/series/test-series")
    assert resp_get.status_code == 200
    data = resp_get.json()
    assert data["title"] == "Test Series Title"
    assert "主人公" in data["characters"]

    # Test suggest API
    resp_sug = client.get("/api/series/suggest?query=%E9%AD%94%E6%B3%95%E7%A7%91%E9%AB%98%E6%A0%A1%E3%81%AE%E5%8A%A3%E7%AD%89%E7%94%9F%203.epub")
    assert resp_sug.status_code == 200
    sug_data = resp_sug.json()
    assert sug_data["title"] == "魔法科高校の劣等生"
    assert sug_data["volume_name"] == "Volume 3"

    # Delete profile
    resp_del = client.delete("/api/series/test-series")
    assert resp_del.status_code == 200
    assert resp_del.json()["deleted"] is True



