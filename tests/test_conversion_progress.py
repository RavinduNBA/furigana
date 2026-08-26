import asyncio
import json
from pathlib import Path
from uuid import uuid4

from furiganalyse.app import Job, jobs, status_handler
from furiganalyse.epub_format import collect_epub_progress_metrics, process_epub_file
from furiganalyse.params import FuriganaMode, OutputFormat
from furiganalyse.progress import ProgressWriter, read_progress


XHTML = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><style>hidden</style></head>
<body><p>本を読む。<ruby>表舞台<rt>おもてぶたい</rt></ruby>次。</p></body></html>
"""


def test_collects_deterministic_section_and_visible_character_metrics(tmp_path):
    (tmp_path / "b.xhtml").write_text(XHTML, encoding="utf-8")
    (tmp_path / "a.xhtml").write_text(XHTML.replace("本を読む。", "前。"), encoding="utf-8")

    metrics = collect_epub_progress_metrics(str(tmp_path))

    assert [value["document"] for value in metrics] == ["a.xhtml", "b.xhtml"]
    assert all("hidden" not in json.dumps(value) for value in metrics)
    assert metrics[0]["characters"] == len("前。表舞台次。")
    assert metrics[1]["characters"] == len("本を読む。表舞台次。")


def test_processing_reports_sections_characters_and_completion(tmp_path):
    (tmp_path / "chapter.xhtml").write_text(XHTML, encoding="utf-8")
    events = []

    process_epub_file(
        str(tmp_path), FuriganaMode.remove, None, OutputFormat.epub,
        progress_callback=events.append,
    )

    assert events[0]["stage"] == "processing"
    assert events[0]["sections_total"] == 1
    assert events[-1]["sections_completed"] == 1
    assert events[-1]["characters_processed"] == events[-1]["characters_total"]
    assert "document" not in events[-1]


def test_progress_snapshot_is_atomic_bounded_and_exposed_by_status(tmp_path):
    progress_path = tmp_path / "progress.json"
    writer = ProgressWriter(progress_path, input_bytes=123)
    writer.update({
        "stage": "processing",
        "sections_total": 4,
        "sections_completed": 1,
        "characters_total": 100,
        "characters_processed": 25,
        "source_text": "must not be recorded",
    })
    progress = read_progress(progress_path)

    assert progress["percent"] == 30
    assert progress["sections_remaining"] == 3
    assert progress["characters_remaining"] == 75
    assert "source_text" not in progress
    assert not progress_path.with_suffix(".tmp").exists()

    uid = uuid4()
    jobs[uid] = Job(uid=uid, progress_path=str(progress_path))
    try:
        response = asyncio.run(status_handler(uid))
        assert response["progress"] == progress
        assert "progress_path" not in response
    finally:
        del jobs[uid]


def test_complete_snapshot_records_output_size(tmp_path):
    progress_path = Path(tmp_path) / "progress.json"
    writer = ProgressWriter(progress_path)
    writer.update({"stage": "complete", "output_bytes": 456})

    value = read_progress(progress_path)
    assert value["stage"] == "complete"
    assert value["percent"] == 100
    assert value["output_bytes"] == 456
