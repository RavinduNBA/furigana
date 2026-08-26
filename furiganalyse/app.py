import asyncio
import base64
import logging
import os
import random
import shutil
import string
from concurrent.futures.process import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, Optional
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, File, Form, FastAPI, Request, status, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

from furiganalyse.__main__ import main, SUPPORTED_INPUT_EXTS
from furiganalyse.known_words import list_available_word_lists
from furiganalyse.params import OutputFormat, FuriganaMode, WritingMode
from furiganalyse.progress import ProgressWriter, read_progress
from furiganalyse.recent_conversions import load_recent_conversions, record_conversion
from furiganalyse.web_study_pipeline import (
    WebStudyOptions,
    normalize_epub_archive,
    run_dictionary_study_pipeline,
)


class Job(BaseModel):
    uid: UUID = Field(default_factory=uuid4)
    status: str = "in_progress"
    result: str = None
    progress_path: Optional[str] = Field(default=None, exclude=True)


jobs: Dict[UUID, Job] = {}


templates = Jinja2Templates(directory="./furiganalyse/templates")

# Get the root path from environment variable, default to empty for local development
root_path = os.getenv("ROOT_PATH", "")
app = FastAPI(root_path=root_path)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[""],
    allow_credentials=True,
    allow_methods=[""],
    allow_headers=["*"],
)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

OUTPUT_FOLDER = '/tmp/furiganalysed/'
Path(OUTPUT_FOLDER).mkdir(exist_ok=True)

# Maximum size for custom word list uploads (1MB)
MAX_WORD_LIST_SIZE = 1 * 1024 * 1024


def validate_word_list_file(contents: bytes) -> tuple[bool, str]:
    """
    Validate a custom word list file.

    Returns:
        A tuple of (is_valid, error_message).
        If valid, error_message is empty.
    """
    if len(contents) > MAX_WORD_LIST_SIZE:
        return False, f"Word list file too large. Maximum size is {MAX_WORD_LIST_SIZE // 1024}KB."

    try:
        contents.decode("utf-8")
    except UnicodeDecodeError:
        return False, "Word list file must be UTF-8 encoded text."

    return True, ""


@app.get("/", response_class=HTMLResponse)
def get_root(request: Request):
    dictionaries_ready = all(Path(path).is_file() for path in (
        os.environ.get("FURIGANALYSE_JMDICT_INDEX", "data/edrdg/JMdict.sqlite"),
        os.environ.get("FURIGANALYSE_JMNEDICT_INDEX", "data/edrdg/JMnedict.sqlite"),
    ))
    recent_conversions = load_recent_conversions(OUTPUT_FOLDER)
    return templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "supported_input_exts": SUPPORTED_INPUT_EXTS,
            "supported_input_accept": ",".join(sorted(SUPPORTED_INPUT_EXTS)),
            "known_words_lists": list_available_word_lists(),
            "dictionaries_ready": dictionaries_ready,
            "recent_conversions": recent_conversions,
        },
    )


@app.get("/api/recent_conversions")
def get_recent_conversions_api():
    return JSONResponse(load_recent_conversions(OUTPUT_FOLDER))


@app.post("/submit")
async def task_handler(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    furigana_mode: str = Form(default="add"),
    writing_mode: str = Form(default="auto"),
    of: str = Form(),
    known_words_list: str = Form(default=""),
    custom_word_list: UploadFile = File(default=None),
    custom_word_list_limit: int = Form(default=0),
    pipeline_mode: str = Form(default="furigana"),
    experimental_adaptive: bool = Form(default=False),
    assistance_preset: str = Form(default="N5"),
    assistance_reading: str = Form(default="show-reading"),
    assistance_meaning: str = Form(default="show-meaning"),
    assistance_meaning_coverage: str = Form(default="all-selected"),
    per_chapter_item_limit: int = Form(default=50),
    redirect: bool = Form(default=True),
):
    if pipeline_mode not in {"furigana", "study", "combined", "guided"}:
        return JSONResponse(status_code=400, content={"error": "Invalid processing mode."})
    if pipeline_mode in {"study", "combined", "guided"} and (
        per_chapter_item_limit != 0
        and not 1 <= per_chapter_item_limit <= 50
    ):
        return JSONResponse(
            status_code=400,
            content={"error": "Study coverage must be All or between 1 and 50."},
        )
    if pipeline_mode in {"study", "combined", "guided"} and (
        Path(file.filename or "").suffix.lower() != ".epub" or of != "epub"
    ):
        return JSONResponse(
            status_code=400,
            content={
                "error": (
                    "Dictionary Study, Combined, and Guided Reading modes require "
                    "EPUB input and output."
                )
            },
        )
    new_task = Job()
    jobs[new_task.uid] = new_task

    # Free up some space if necessary
    cleanup_output_folder()

    # Write uploaded file to a temporary file
    task_folder = os.path.join(OUTPUT_FOLDER, str(new_task.uid))
    Path(task_folder).mkdir(exist_ok=True)
    # Sanitize filename to prevent path traversal attacks
    safe_filename = os.path.basename(file.filename)
    if not safe_filename:
        safe_filename = "uploaded_file"
    tmpfile = os.path.join(task_folder, safe_filename)
    contents = file.file.read()
    with open(tmpfile, 'wb') as f:
        f.write(contents)
    new_task.progress_path = os.path.join(task_folder, "progress.json")
    ProgressWriter(new_task.progress_path, input_bytes=len(contents))

    output_filename = generate_output_filename(safe_filename, of, pipeline_mode)
    record_conversion(
        OUTPUT_FOLDER,
        uid=str(new_task.uid),
        filename=safe_filename,
        output_filename=output_filename,
        pipeline_mode=pipeline_mode,
        furigana_mode=furigana_mode,
        status="in_progress",
    )

    # Handle custom word list upload
    custom_word_list_path = None
    if known_words_list == "__custom__":
        # Clear the special marker value
        known_words_list = ""
        if custom_word_list and custom_word_list.filename:
            word_list_contents = custom_word_list.file.read()
            is_valid, error_message = validate_word_list_file(word_list_contents)
            if not is_valid:
                # Clean up task folder on validation error
                shutil.rmtree(task_folder)
                del jobs[new_task.uid]
                if redirect:
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"error": error_message},
                    )
                else:
                    return {"error": error_message}

            custom_word_list_path = os.path.join(task_folder, "custom_word_list.txt")
            with open(custom_word_list_path, 'wb') as f:
                f.write(word_list_contents)

    background_tasks.add_task(
        start_furiganalyse_task,
        new_task.uid,
        task_folder,
        safe_filename,
        of,
        furigana_mode,
        writing_mode,
        known_words_list,
        custom_word_list_path,
        custom_word_list_limit,
        pipeline_mode,
        experimental_adaptive,
        assistance_preset,
        assistance_reading,
        assistance_meaning,
        assistance_meaning_coverage,
        per_chapter_item_limit,
    )

    if redirect:
        return RedirectResponse(f"/jobs/{new_task.uid}", status_code=status.HTTP_302_FOUND)
    else:
        return {"uid": new_task.uid}


@app.get("/jobs/{uid}", response_class=HTMLResponse)
def get_download(request: Request, uid: UUID):
    recent_conversions = load_recent_conversions(OUTPUT_FOLDER)
    return templates.TemplateResponse(
        "download.html",
        {
            "request": request,
            "uid": uid,
            "recent_conversions": recent_conversions,
        },
    )


def furiganalyse_task(
    task_folder: Path,
    filename: str,
    output_format: str,
    furigana_mode: str,
    writing_mode: str,
    known_words_list: str = "",
    custom_word_list_path: str = None,
    custom_word_list_limit: int = 0,
    pipeline_mode: str = "furigana",
    experimental_adaptive: bool = False,
    assistance_preset: str = "N5",
    assistance_reading: str = "show-reading",
    assistance_meaning: str = "show-meaning",
    assistance_meaning_coverage: str = "all-selected",
    per_chapter_item_limit: int = 50,
) -> str:
    input_filepath = os.path.join(task_folder, filename)
    output_filename = generate_output_filename(filename, output_format, pipeline_mode)
    output_filepath = os.path.join(task_folder, output_filename)
    path_hash = encode_filepath(output_filepath)
    progress = ProgressWriter(
        os.path.join(task_folder, "progress.json"),
        input_bytes=os.path.getsize(input_filepath),
    )

    try:
        if pipeline_mode in {"study", "combined", "guided"}:
            assisted_furigana = pipeline_mode in {"combined", "guided"}
            study_input = input_filepath
            if assisted_furigana:
                furi_stage = Path(task_folder) / "furigana-stage.epub"

                def furigana_progress(event):
                    progress.update({
                        **event,
                        "pipeline_mode": pipeline_mode,
                        "combined_phase": "furigana",
                    })

                progress.update({
                    "stage": "preparing",
                    "pipeline_mode": pipeline_mode,
                    "combined_phase": "furigana",
                })
                main(
                    input_filepath,
                    str(furi_stage),
                    furigana_mode=FuriganaMode(furigana_mode),
                    output_format=OutputFormat.epub,
                    writing_mode=WritingMode(writing_mode),
                    known_words_list=(
                        known_words_list if known_words_list else None
                    ),
                    custom_word_list_path=custom_word_list_path,
                    custom_word_list_limit=(
                        custom_word_list_limit
                        if custom_word_list_limit > 0
                        else None
                    ),
                    progress_callback=furigana_progress,
                )
                study_input = str(furi_stage)

            progress.update({
                "stage": "preparing",
                "pipeline_mode": pipeline_mode,
                "combined_phase": "dictionary" if assisted_furigana else None,
            })
            study_output = (
                output_filepath
                if pipeline_mode == "study"
                else str(Path(task_folder) / "study-work" / "annotated-stage.epub")
            )

            def dictionary_progress(event):
                progress.update({
                    **event,
                    "pipeline_mode": pipeline_mode,
                    "combined_phase": (
                        "dictionary" if assisted_furigana else None
                    ),
                })

            run_dictionary_study_pipeline(
                study_input,
                study_output,
                Path(task_folder) / "study-work",
                WebStudyOptions(
                    per_chapter_item_limit=(0 if pipeline_mode == "guided" else per_chapter_item_limit),
                    experimental_adaptive=(experimental_adaptive if pipeline_mode != "guided" else False),
                    preset_level=assistance_preset,
                    reading_state=assistance_reading,
                    meaning_state=assistance_meaning,
                    meaning_coverage=assistance_meaning_coverage,
                    guided_reading=pipeline_mode == "guided",
                ),
                progress_callback=dictionary_progress,
            )
            if assisted_furigana:
                progress.update({
                    "stage": "packaging",
                    "pipeline_mode": pipeline_mode,
                    "combined_phase": "dictionary",
                })
                normalize_epub_archive(Path(study_output), output_filepath)
            progress.update({
                "stage": "complete",
                "pipeline_mode": pipeline_mode,
                "combined_phase": (
                    "dictionary" if assisted_furigana else None
                ),
                "output_bytes": os.path.getsize(output_filepath),
            })
        else:
            main(
                input_filepath,
                output_filepath,
                furigana_mode=FuriganaMode(furigana_mode),
                output_format=OutputFormat(output_format),
                writing_mode=WritingMode(writing_mode),
                known_words_list=known_words_list if known_words_list else None,
                custom_word_list_path=custom_word_list_path,
                custom_word_list_limit=custom_word_list_limit if custom_word_list_limit > 0 else None,
                progress_callback=progress.update,
            )
    except Exception:
        progress.update({"stage": "error"})
        logging.error("Conversion worker failed")
        raise

    return path_hash


@app.get("/jobs/{uid}/status")
async def status_handler(uid: UUID):
    job = jobs.get(uid)
    if not job:
        return Response("Uid not found!", status_code=404)
    value = job.model_dump()
    value["progress"] = read_progress(job.progress_path) if job.progress_path else None
    return value


@app.get('/jobs/{uid}/file')
def get_file(uid: UUID):
    job = jobs.get(uid)
    if not job:
        return Response("Uid not found!", status_code=404)

    if job.status != "complete":
        return Response("Job not completed yet!", status_code=400)

    if not job.result:
        return Response("Something went wrong!", status_code=500)

    path_hash = job.result
    file_path = decode_filepath(path_hash)
    filename = os.path.basename(file_path)
    return FileResponse(path=file_path, filename=filename)


@app.on_event("startup")
async def startup_event():
    workers = max(1, int(os.environ.get("FURIGANALYSE_WORKERS", "1")))
    app.state.executor = ProcessPoolExecutor(max_workers=workers)


@app.on_event("shutdown")
async def on_shutdown():
    app.state.executor.shutdown()


OUTPUT_FORMAT_TO_EXTENSION = {
    OutputFormat.epub: ".epub",
    OutputFormat.mobi: ".mobi",
    OutputFormat.azw3: ".azw3",
    OutputFormat.many_txt: ".zip",
    OutputFormat.single_txt: ".txt",
    OutputFormat.apkg: ".apkg",
    OutputFormat.html: ".html",
}


def generate_output_filename(
    input_filename: str,
    output_format: OutputFormat | str,
    pipeline_mode: str = "furigana",
) -> str:
    filename_without_ext = os.path.splitext(input_filename)[0]
    format_enum = OutputFormat(output_format) if isinstance(output_format, str) else output_format
    extension = OUTPUT_FORMAT_TO_EXTENSION[format_enum]
    mode_labels = {
        "furigana": "Furigana",
        "study": "Study",
        "combined": "Combined",
        "guided": "Guided",
    }
    mode_suffix = mode_labels.get(pipeline_mode, "Furigana")
    if filename_without_ext.startswith("furiganalysed_"):
        filename_without_ext = filename_without_ext[len("furiganalysed_"):]
    return f"{filename_without_ext} - {mode_suffix}{extension}"


def generate_random_key(length):
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))


def encode_filepath(filepath):
    return str(base64.urlsafe_b64encode(filepath.encode("utf-8")), "utf-8")


def decode_filepath(hashed_path):
    return str(base64.urlsafe_b64decode(hashed_path.encode("utf-8")), "utf-8")


def cleanup_output_folder(force: bool = False):
    """
    Keep the total size of output folder below a threshold, thrashing from the older files when needed.
    """
    size_threshold = int(os.environ.get("FURIGANALYSE_CLEANUP_THRESHOLD_IN_MB", 100)) * 1_000_000

    output_folder = Path(OUTPUT_FOLDER)
    paths = sorted(output_folder.iterdir(), key=os.path.getctime)

    path_and_sizes = []
    total_size = 0
    for path in paths:
        if path.is_dir():
            size = sum(f.stat().st_size for f in path.glob('**/*') if f.is_file())
            path_and_sizes.append((path, size))
            total_size += size

    if total_size < size_threshold and not force:
        return

    for path, size in path_and_sizes:
        logging.info(f"Removing {path} to free up space")

        try:
            uid = UUID(os.path.basename(path))
            if uid in jobs:
                logging.info(f"Deleting associated job {uid}")
                del jobs[uid]
        except ValueError:
            pass

        shutil.rmtree(path)
        total_size -= size
        if total_size < size_threshold and not force:
            break


async def run_in_process(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(app.state.executor, fn, *args)  # wait and return result


async def start_furiganalyse_task(
    uid: UUID,
    task_folder: str,
    safe_filename: str,
    of: str,
    furigana_mode: str,
    *args,
) -> None:
    pipeline_mode = args[5] if len(args) > 5 else "furigana"
    output_filename = generate_output_filename(safe_filename, of, pipeline_mode)
    try:
        jobs[uid].result = await run_in_process(
            furiganalyse_task,
            task_folder,
            safe_filename,
            of,
            furigana_mode,
            *args,
        )
        jobs[uid].status = "complete"
        output_path = decode_filepath(jobs[uid].result)
        output_bytes = os.path.getsize(output_path) if os.path.isfile(output_path) else None
        record_conversion(
            OUTPUT_FOLDER,
            uid=str(uid),
            filename=safe_filename,
            output_filename=output_filename,
            pipeline_mode=pipeline_mode,
            furigana_mode=furigana_mode,
            status="complete",
            output_bytes=output_bytes,
        )
    except Exception:
        logging.error("Error occurred for job %s", uid)
        jobs[uid].status = "error"
        record_conversion(
            OUTPUT_FOLDER,
            uid=str(uid),
            filename=safe_filename,
            output_filename=output_filename,
            pipeline_mode=pipeline_mode,
            furigana_mode=furigana_mode,
            status="error",
        )

