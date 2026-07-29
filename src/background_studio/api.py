from __future__ import annotations

import io
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from . import __version__
from .config import Settings
from .editing import EditOptions, compose, open_rgba, to_png_bytes
from .engine import SUPPORTED_MODELS, RembgEngine
from .models import BackgroundMode, JobStatus, JobStore
from .sam3_adapter import Sam3ImageAdapter, Sam3Unavailable
from .security import read_limited, safe_video_suffix, validate_image
from .video import VideoDependencyError, VideoOptions, VideoProcessor

settings = Settings.from_env()
engine = RembgEngine()
jobs = JobStore()
video_processor = VideoProcessor(engine, settings.ffmpeg, settings.ffprobe)
sam3 = Sam3ImageAdapter()

app = FastAPI(
    title="Background Studio API",
    version=__version__,
    description="Local-first background removal and compositing for images and videos.",
)


def _edit_options(
    mode: BackgroundMode,
    color: str,
    blur_radius: float,
    shadow_blur: float,
    shadow_opacity: int,
    shadow_offset_x: int,
    shadow_offset_y: int,
) -> EditOptions:
    options = EditOptions(
        mode=mode,
        color=color,
        blur_radius=blur_radius,
        shadow_blur=shadow_blur,
        shadow_opacity=shadow_opacity,
        shadow_offset_x=shadow_offset_x,
        shadow_offset_y=shadow_offset_y,
    )
    try:
        options.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return options


@app.get("/healthz")
def health() -> dict[str, object]:
    try:
        video_processor.ensure_dependencies()
        ffmpeg_available = True
    except VideoDependencyError:
        ffmpeg_available = False
    return {
        "status": "ok",
        "version": __version__,
        "models": SUPPORTED_MODELS,
        "ffmpeg_available": ffmpeg_available,
        "privacy": "Files are processed locally and are not sent to a third-party API.",
    }


@app.post("/v1/images/remove")
async def remove_image(
    file: UploadFile = File(...),
    background: UploadFile | None = File(None),
    model: str = Form("u2netp"),
    mode: BackgroundMode = Form(BackgroundMode.TRANSPARENT),
    color: str = Form("#ffffff"),
    blur_radius: float = Form(18.0),
    alpha_matting: bool = Form(False),
    foreground_threshold: int = Form(240),
    background_threshold: int = Form(10),
    erode_size: int = Form(10),
    post_process_mask: bool = Form(False),
    shadow_blur: float = Form(0.0),
    shadow_opacity: int = Form(80),
    shadow_offset_x: int = Form(0),
    shadow_offset_y: int = Form(12),
) -> Response:
    data = await read_limited(file, settings.max_image_bytes)
    validate_image(data)
    original = open_rgba(data)
    options = _edit_options(
        mode,
        color,
        blur_radius,
        shadow_blur,
        shadow_opacity,
        shadow_offset_x,
        shadow_offset_y,
    )
    background_image = None
    if background is not None:
        background_data = await read_limited(background, settings.max_image_bytes)
        validate_image(background_data)
        background_image = open_rgba(background_data)
    if mode == BackgroundMode.IMAGE and background_image is None:
        raise HTTPException(status_code=422, detail="background file is required for image mode")

    try:
        cutout = engine.remove(
            original,
            model=model,
            alpha_matting=alpha_matting,
            foreground_threshold=foreground_threshold,
            background_threshold=background_threshold,
            erode_size=erode_size,
            post_process_mask=post_process_mask,
        )
        result = compose(original, cutout, options, background_image)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(to_png_bytes(result), media_type="image/png")


@app.post("/v1/images/concept-mask")
async def concept_mask(
    file: UploadFile = File(...),
    prompt: str = Form(..., min_length=1, max_length=200),
    score_threshold: float = Form(0.5, ge=0, le=1),
) -> Response:
    data = await read_limited(file, settings.max_image_bytes)
    validate_image(data)
    try:
        mask = sam3.isolate(open_rgba(data), prompt, score_threshold)
    except Sam3Unavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    output = io.BytesIO()
    mask.save(output, "PNG")
    return Response(output.getvalue(), media_type="image/png")


def _run_video_job(
    job_id: str,
    options: VideoOptions,
    background_path: Path | None,
) -> None:
    job = jobs.get(job_id)
    if job is None:
        return
    output_suffix = ".webm" if options.edit.mode == BackgroundMode.TRANSPARENT else ".mp4"
    output = settings.work_dir / f"{job_id}{output_suffix}"
    jobs.update(job_id, status=JobStatus.PROCESSING, progress=1)
    try:
        video_processor.process(
            job.source_path,
            output,
            options,
            background_path=background_path,
            on_progress=lambda progress: jobs.update(job_id, progress=progress),
        )
        jobs.update(job_id, status=JobStatus.COMPLETE, output_path=output, progress=100)
    except Exception as exc:
        jobs.update(job_id, status=JobStatus.FAILED, error=str(exc), progress=0)
    finally:
        job.source_path.unlink(missing_ok=True)
        if background_path:
            background_path.unlink(missing_ok=True)


@app.post("/v1/videos/remove", status_code=202)
async def remove_video(
    tasks: BackgroundTasks,
    file: UploadFile = File(...),
    background: UploadFile | None = File(None),
    model: str = Form("u2netp"),
    mode: BackgroundMode = Form(BackgroundMode.TRANSPARENT),
    color: str = Form("#ffffff"),
    blur_radius: float = Form(18.0),
    max_dimension: int = Form(1280),
    fps: float | None = Form(None),
) -> dict[str, object]:
    video_processor.ensure_dependencies()
    suffix = safe_video_suffix(file.filename)
    data = await read_limited(file, settings.max_video_bytes)
    stem = Path(file.filename or "video").stem[:40]
    source = settings.work_dir / f"upload-{stem}-{id(data)}{suffix}"
    source.write_bytes(data)
    background_path = None
    if background is not None:
        background_data = await read_limited(background, settings.max_image_bytes)
        validate_image(background_data)
        background_path = settings.work_dir / f"background-{id(background_data)}.png"
        background_path.write_bytes(background_data)
    if mode == BackgroundMode.IMAGE and background_path is None:
        source.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="background file is required for image mode")
    options = VideoOptions(
        model=model,
        edit=_edit_options(mode, color, blur_radius, 0, 0, 0, 0),
        max_dimension=max_dimension,
        fps=fps,
    )
    try:
        options.validate()
    except ValueError as exc:
        source.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    job = jobs.create(source)
    tasks.add_task(_run_video_job, job.id, options, background_path)
    return job.public()


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, object]:
    jobs.delete_expired(settings.job_ttl_hours)
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.public()


@app.get("/v1/jobs/{job_id}/download")
def download_job(job_id: str) -> FileResponse:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.COMPLETE or not job.output_path or not job.output_path.exists():
        raise HTTPException(status_code=409, detail="Job output is not ready")
    media_type = "video/webm" if job.output_path.suffix == ".webm" else "video/mp4"
    return FileResponse(
        job.output_path,
        media_type=media_type,
        filename=f"background-studio-{job.id}{job.output_path.suffix}",
    )
