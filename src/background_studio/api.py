from __future__ import annotations

import io
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from . import __version__
from .config import Settings
from .editing import (
    EditOptions,
    compose,
    media_type_for,
    open_rgba,
    prepare_foreground,
    to_image_bytes,
    to_svg_outline,
)
from .engine import SUPPORTED_MODELS, RembgEngine
from .models import (
    BackgroundMode,
    CanvasAspect,
    ForegroundFilter,
    JobStatus,
    JobStore,
    RenderMode,
)
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
    foreground_filter: ForegroundFilter,
    render_mode: RenderMode,
    subject_scale: float,
    subject_offset_x: float,
    subject_offset_y: float,
    auto_center: bool,
    outline_width: int,
    outline_color: str,
    brightness: float = 1.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    temperature: float = 0.0,
    hue: float = 0.0,
    foreground_opacity: float = 1.0,
    rotation: float = 0.0,
    flip_horizontal: bool = False,
    flip_vertical: bool = False,
    mask_threshold: float = 0.0,
    mask_feather: float = 0.0,
    mask_expansion: int = 0,
    canvas_aspect: CanvasAspect = CanvasAspect.ORIGINAL,
) -> EditOptions:
    options = EditOptions(
        mode=mode,
        color=color,
        blur_radius=blur_radius,
        shadow_blur=shadow_blur,
        shadow_opacity=shadow_opacity,
        shadow_offset_x=shadow_offset_x,
        shadow_offset_y=shadow_offset_y,
        foreground_filter=foreground_filter,
        render_mode=render_mode,
        subject_scale=subject_scale,
        subject_offset_x=subject_offset_x,
        subject_offset_y=subject_offset_y,
        auto_center=auto_center,
        outline_width=outline_width,
        outline_color=outline_color,
        brightness=brightness,
        contrast=contrast,
        saturation=saturation,
        temperature=temperature,
        hue=hue,
        foreground_opacity=foreground_opacity,
        rotation=rotation,
        flip_horizontal=flip_horizontal,
        flip_vertical=flip_vertical,
        mask_threshold=mask_threshold,
        mask_feather=mask_feather,
        mask_expansion=mask_expansion,
        canvas_aspect=canvas_aspect,
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
    foreground_filter: ForegroundFilter = Form(ForegroundFilter.ORIGINAL),
    render_mode: RenderMode = Form(RenderMode.COMPOSITE),
    subject_scale: float = Form(1.0),
    subject_offset_x: float = Form(0.0),
    subject_offset_y: float = Form(0.0),
    auto_center: bool = Form(False),
    outline_width: int = Form(3),
    outline_color: str = Form("#111111"),
    brightness: float = Form(1.0),
    contrast: float = Form(1.0),
    saturation: float = Form(1.0),
    temperature: float = Form(0.0),
    hue: float = Form(0.0),
    foreground_opacity: float = Form(1.0),
    rotation: float = Form(0.0),
    flip_horizontal: bool = Form(False),
    flip_vertical: bool = Form(False),
    mask_threshold: float = Form(0.0),
    mask_feather: float = Form(0.0),
    mask_expansion: int = Form(0),
    canvas_aspect: CanvasAspect = Form(CanvasAspect.ORIGINAL),
    output_format: str = Form("png"),
    quality: int = Form(92),
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
        foreground_filter,
        render_mode,
        subject_scale,
        subject_offset_x,
        subject_offset_y,
        auto_center,
        outline_width,
        outline_color,
        brightness,
        contrast,
        saturation,
        temperature,
        hue,
        foreground_opacity,
        rotation,
        flip_horizontal,
        flip_vertical,
        mask_threshold,
        mask_feather,
        mask_expansion,
        canvas_aspect,
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
    try:
        normalized_format = output_format.lower()
        if normalized_format == "svg":
            if render_mode != RenderMode.OUTLINE:
                raise ValueError("SVG output is available only in outline render mode")
            svg = to_svg_outline(
                prepare_foreground(cutout, options),
                stroke_color=options.outline_color,
                stroke_width=options.outline_width,
            )
            return Response(svg, media_type="image/svg+xml")
        if not 1 <= quality <= 100:
            raise ValueError("quality must be between 1 and 100")
        return Response(
            to_image_bytes(result, normalized_format, quality),
            media_type=media_type_for(normalized_format),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
    output_suffix = f".{options.output_format}"
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
    output_format: str = Form("webm"),
    foreground_filter: ForegroundFilter = Form(ForegroundFilter.ORIGINAL),
    render_mode: RenderMode = Form(RenderMode.COMPOSITE),
    subject_scale: float = Form(1.0),
    subject_offset_x: float = Form(0.0),
    subject_offset_y: float = Form(0.0),
    auto_center: bool = Form(False),
    outline_width: int = Form(3),
    outline_color: str = Form("#111111"),
    brightness: float = Form(1.0),
    contrast: float = Form(1.0),
    saturation: float = Form(1.0),
    temperature: float = Form(0.0),
    hue: float = Form(0.0),
    foreground_opacity: float = Form(1.0),
    rotation: float = Form(0.0),
    flip_horizontal: bool = Form(False),
    flip_vertical: bool = Form(False),
    mask_threshold: float = Form(0.0),
    mask_feather: float = Form(0.0),
    mask_expansion: int = Form(0),
    canvas_aspect: CanvasAspect = Form(CanvasAspect.ORIGINAL),
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
        edit=_edit_options(
            mode,
            color,
            blur_radius,
            0,
            0,
            0,
            0,
            foreground_filter,
            render_mode,
            subject_scale,
            subject_offset_x,
            subject_offset_y,
            auto_center,
            outline_width,
            outline_color,
            brightness,
            contrast,
            saturation,
            temperature,
            hue,
            foreground_opacity,
            rotation,
            flip_horizontal,
            flip_vertical,
            mask_threshold,
            mask_feather,
            mask_expansion,
            canvas_aspect,
        ),
        max_dimension=max_dimension,
        fps=fps,
        output_format=output_format.lower(),
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
    media_type = {
        ".webm": "video/webm",
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".gif": "image/gif",
    }.get(job.output_path.suffix, "application/octet-stream")
    return FileResponse(
        job.output_path,
        media_type=media_type,
        filename=f"background-studio-{job.id}{job.output_path.suffix}",
    )
