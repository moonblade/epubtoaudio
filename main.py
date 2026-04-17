import asyncio
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse
from starlette.requests import Request

from config import UPLOAD_PATH, OUTPUT_PATH, JOBS_PATH, TEMPLATES_PATH, STATIC_PATH, DEFAULT_VOICE
from models import JobStatus, JobResponse, UploadResponse, VoiceOption, VOICE_DISPLAY_NAMES, LogEvent, PreprocessResponse, ChapterResponse, SegmentResponse
from job_manager import JobManager
from converter import ConversionJob, extract_chapters_with_html
from preprocessor import ExpressivePreprocessor
from log_store import LogStore
from logger import logger

app = FastAPI(title="EPUB to Audio Converter")

app.mount("/static", StaticFiles(directory=str(STATIC_PATH)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_PATH))

job_manager = JobManager(JOBS_PATH)
log_store = LogStore(JOBS_PATH)
executor = ThreadPoolExecutor(max_workers=2)

active_jobs: dict[str, ConversionJob] = {}
log_queues: dict[str, asyncio.Queue[LogEvent]] = {}


def get_paths(
    upload_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> tuple[Path, Path]:
    up = Path(upload_path) if upload_path else UPLOAD_PATH
    op = Path(output_path) if output_path else OUTPUT_PATH
    up.mkdir(parents=True, exist_ok=True)
    op.mkdir(parents=True, exist_ok=True)
    return up, op


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    jobs = job_manager.list_jobs()
    job_list = [
        JobResponse(
            job_id=j.job_id,
            status=j.status,
            voice=j.voice,
            epub_filename=j.epub_filename,
            progress=j.progress,
            current_chapter=j.current_chapter,
            total_chapters=j.total_chapters,
            error=j.error,
            created_at=j.created_at.isoformat(),
            updated_at=j.updated_at.isoformat(),
        )
        for j in jobs
    ]
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "jobs": job_list,
            "voices": VOICE_DISPLAY_NAMES,
            "default_voice": DEFAULT_VOICE,
        },
    )


@app.post("/upload", response_model=UploadResponse)
async def upload_epub(
    file: UploadFile = File(...),
    voice: str = Form(default=DEFAULT_VOICE),
    upload_path: Optional[str] = Form(default=None),
    output_path: Optional[str] = Form(default=None),
):
    if not file.filename.lower().endswith(".epub"):
        raise HTTPException(status_code=400, detail="Only EPUB files are allowed")
    
    try:
        VoiceOption(voice)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid voice: {voice}")
    
    up, op = get_paths(upload_path, output_path)
    
    job_id = str(uuid.uuid4())[:8]
    epub_path = up / f"{job_id}.epub"
    output_dir = op / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(epub_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    job_state = job_manager.create_job(
        job_id=job_id,
        epub_path=str(epub_path),
        epub_filename=file.filename,
        output_dir=str(output_dir),
        voice=voice,
    )
    
    logger.info(f"Created job {job_id} for {file.filename} with voice {voice}")
    
    log_queue: asyncio.Queue[LogEvent] = asyncio.Queue(maxsize=1000)
    log_queues[job_id] = log_queue
    
    conversion_job = ConversionJob(job_state, job_manager, log_queue, log_store)
    active_jobs[job_id] = conversion_job
    
    executor.submit(lambda: conversion_job.run())
    
    return UploadResponse(
        job_id=job_id,
        status="started",
        message=f"Conversion started for {file.filename}",
    )


@app.get("/jobs")
async def list_jobs():
    jobs = job_manager.list_jobs()
    return [
        JobResponse(
            job_id=j.job_id,
            status=j.status,
            voice=j.voice,
            epub_filename=j.epub_filename,
            progress=j.progress,
            current_chapter=j.current_chapter,
            total_chapters=j.total_chapters,
            error=j.error,
            created_at=j.created_at.isoformat(),
            updated_at=j.updated_at.isoformat(),
        )
        for j in jobs
    ]


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(
        job_id=job.job_id,
        status=job.status,
        voice=job.voice,
        epub_filename=job.epub_filename,
        progress=job.progress,
        current_chapter=job.current_chapter,
        total_chapters=job.total_chapters,
        error=job.error,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )


@app.post("/jobs/{job_id}/stop")
async def stop_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job_id in active_jobs:
        active_jobs[job_id].stop()
    
    job_manager.update_job(job_id, status=JobStatus.PAUSED)
    logger.info(f"Job {job_id} paused")
    return {"status": "paused", "job_id": job_id}


@app.post("/jobs/{job_id}/resume")
async def resume_job(
    job_id: str,
    upload_path: Optional[str] = Query(default=None),
    output_path: Optional[str] = Query(default=None),
):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status not in [JobStatus.PAUSED, JobStatus.FAILED]:
        raise HTTPException(status_code=400, detail="Job cannot be resumed")
    
    log_queue = log_queues.get(job_id) or asyncio.Queue(maxsize=1000)
    log_queues[job_id] = log_queue
    
    conversion_job = ConversionJob(job, job_manager, log_queue, log_store)
    active_jobs[job_id] = conversion_job
    
    executor.submit(lambda: conversion_job.run())
    logger.info(f"Job {job_id} resumed")
    
    return {"status": "resumed", "job_id": job_id}


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job_id in active_jobs:
        active_jobs[job_id].stop()
        del active_jobs[job_id]
    
    if job_id in log_queues:
        del log_queues[job_id]
    
    log_store.delete(job_id)
    
    if job.epub_path and Path(job.epub_path).exists():
        Path(job.epub_path).unlink()
    
    if job.output_dir and Path(job.output_dir).exists():
        shutil.rmtree(job.output_dir, ignore_errors=True)
    
    job_manager.delete_job(job_id)
    logger.info(f"Job {job_id} deleted")
    return {"status": "deleted", "job_id": job_id}


@app.get("/jobs/{job_id}/logs")
async def stream_logs(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    async def event_generator():
        stored_logs = log_store.get_all(job_id)
        for event in stored_logs:
            yield {
                "event": "log",
                "data": event.model_dump_json(),
            }
        
        current_job = job_manager.get_job(job_id)
        if current_job and current_job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            yield {
                "event": "done",
                "data": current_job.status,
            }
            return
        
        queue = log_queues.get(job_id)
        if not queue:
            queue = asyncio.Queue(maxsize=1000)
            log_queues[job_id] = queue
        
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield {
                    "event": "log",
                    "data": event.model_dump_json(),
                }
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": ""}
                
                current_job = job_manager.get_job(job_id)
                if current_job and current_job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                    yield {
                        "event": "done",
                        "data": current_job.status,
                    }
                    break
    
    return EventSourceResponse(event_generator())


@app.get("/jobs/{job_id}/logs-page", response_class=HTMLResponse)
async def logs_page(request: Request, job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse(
        request=request,
        name="logs.html",
        context={"job": job},
    )


@app.get("/jobs/{job_id}/audio/{chapter}")
async def download_chapter_audio(job_id: str, chapter: int):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    chapter_audio = Path(job.output_dir) / f"chapter_{chapter:03d}.mp3"
    if not chapter_audio.exists():
        raise HTTPException(status_code=404, detail="Chapter audio not found")
    
    return FileResponse(
        str(chapter_audio),
        media_type="audio/mpeg",
        filename=f"{job.epub_filename.replace('.epub', '')}_chapter_{chapter}.mp3",
    )


@app.get("/voices")
async def list_voices():
    return VOICE_DISPLAY_NAMES


@app.post("/preprocess", response_model=PreprocessResponse)
async def preprocess_epub(
    file: UploadFile = File(...),
    voice: str = Form(default=DEFAULT_VOICE),
    chapter: Optional[int] = Query(default=None, description="Process only this chapter (1-indexed)"),
):
    if not file.filename.lower().endswith(".epub"):
        raise HTTPException(status_code=400, detail="Only EPUB files are allowed")

    try:
        VoiceOption(voice)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid voice: {voice}")

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        raw_chapters = extract_chapters_with_html(tmp_path)

        if chapter is not None:
            if chapter < 1 or chapter > len(raw_chapters):
                raise HTTPException(
                    status_code=400,
                    detail=f"Chapter {chapter} not found. Book has {len(raw_chapters)} chapters."
                )
            raw_chapters = [raw_chapters[chapter - 1]]

        preprocessor = ExpressivePreprocessor(
            narrator_voice=voice,
            enable_speaker_detection=False,
            use_booknlp=False,
        )

        chapters_response = []
        for raw in raw_chapters:
            processed = preprocessor.process_chapter_html(
                raw["html_content"],
                raw["title"],
                raw["order"],
            )

            speakers_in_chapter = list({
                seg.speaker for seg in processed.segments if seg.speaker
            })

            segments = [
                SegmentResponse(
                    text=seg.text,
                    segment_type=seg.segment_type.value,
                    speaker=seg.speaker,
                    pause_before_seconds=seg.pause_before_seconds,
                    pause_after_seconds=seg.pause_after_seconds,
                    speed=seg.speed,
                    pitch_shift=seg.pitch_shift,
                )
                for seg in processed.segments
            ]

            chapters_response.append(ChapterResponse(
                title=processed.title,
                order=processed.order,
                segment_count=len(segments),
                speakers=speakers_in_chapter,
                segments=segments,
            ))

        return PreprocessResponse(
            filename=file.filename,
            total_chapters=len(raw_chapters) if chapter is None else len(extract_chapters_with_html(tmp_path)),
            chapters=chapters_response,
            speaker_pitch_map=preprocessor.get_speaker_pitch_map(),
        )
    finally:
        import os
        os.unlink(tmp_path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3002)
