from __future__ import annotations

from pathlib import Path

import typer
from PIL import Image

from .config import Settings
from .editing import EditOptions, compose, prepare_foreground, to_image_bytes, to_svg_outline
from .engine import SUPPORTED_MODELS, RembgEngine
from .models import BackgroundMode, ForegroundFilter, RenderMode
from .video import VideoOptions, VideoProcessor

app = typer.Typer(no_args_is_help=True, help="Local image and video background studio")
engine = RembgEngine()


def _mode(value: str) -> BackgroundMode:
    try:
        return BackgroundMode(value)
    except ValueError as exc:
        raise typer.BadParameter("Use transparent, color, image, or blur") from exc


@app.command(help="Remove an image background and optionally replace it.")
def image(
    source: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    output: Path = typer.Argument(..., dir_okay=False),
    model: str = typer.Option("u2netp", help=f"One of: {', '.join(SUPPORTED_MODELS)}"),
    mode: str = typer.Option("transparent"),
    color: str = typer.Option("#ffffff"),
    background: Path | None = typer.Option(None, exists=True, dir_okay=False),
    blur_radius: float = typer.Option(18.0, min=0, max=100),
    alpha_matting: bool = typer.Option(False),
    foreground_filter: ForegroundFilter = typer.Option(ForegroundFilter.ORIGINAL),
    render_mode: RenderMode = typer.Option(RenderMode.COMPOSITE),
    subject_scale: float = typer.Option(1.0, min=0.1, max=3),
    subject_offset_x: float = typer.Option(0.0, min=-1, max=1),
    subject_offset_y: float = typer.Option(0.0, min=-1, max=1),
    auto_center: bool = typer.Option(False),
    outline_width: int = typer.Option(3, min=1, max=50),
    outline_color: str = typer.Option("#111111"),
) -> None:
    selected_mode = _mode(mode)
    if selected_mode == BackgroundMode.IMAGE and background is None:
        raise typer.BadParameter("--background is required when --mode=image")
    with Image.open(source) as opened:
        original = opened.convert("RGBA")
    cutout = engine.remove(original, model=model, alpha_matting=alpha_matting)
    background_image = Image.open(background).convert("RGBA") if background else None
    options = EditOptions(
        mode=selected_mode,
        color=color,
        blur_radius=blur_radius,
        foreground_filter=foreground_filter,
        render_mode=render_mode,
        subject_scale=subject_scale,
        subject_offset_x=subject_offset_x,
        subject_offset_y=subject_offset_y,
        auto_center=auto_center,
        outline_width=outline_width,
        outline_color=outline_color,
    )
    result = compose(
        original,
        cutout,
        options,
        background_image,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output_format = output.suffix.lower().lstrip(".")
    if output_format == "svg":
        output.write_text(
            to_svg_outline(
                prepare_foreground(cutout, options),
                stroke_color=options.outline_color,
                stroke_width=options.outline_width,
            ),
            encoding="utf-8",
        )
    else:
        output.write_bytes(to_image_bytes(result, output_format))
    typer.echo(f"Saved {output}")


@app.command(help="Process video through FFmpeg; transparent output uses WebM.")
def video(
    source: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    output: Path = typer.Argument(..., dir_okay=False),
    model: str = typer.Option("u2netp"),
    mode: str = typer.Option("transparent"),
    color: str = typer.Option("#ffffff"),
    background: Path | None = typer.Option(None, exists=True, dir_okay=False),
    blur_radius: float = typer.Option(18.0, min=0, max=100),
    max_dimension: int = typer.Option(1280, min=320, max=3840),
    fps: float | None = typer.Option(None, min=1, max=60),
    foreground_filter: ForegroundFilter = typer.Option(ForegroundFilter.ORIGINAL),
    render_mode: RenderMode = typer.Option(RenderMode.COMPOSITE),
    subject_scale: float = typer.Option(1.0, min=0.1, max=3),
    subject_offset_x: float = typer.Option(0.0, min=-1, max=1),
    subject_offset_y: float = typer.Option(0.0, min=-1, max=1),
    auto_center: bool = typer.Option(False),
    outline_width: int = typer.Option(3, min=1, max=50),
    outline_color: str = typer.Option("#111111"),
) -> None:
    settings = Settings.from_env()
    selected_mode = _mode(mode)
    if selected_mode == BackgroundMode.IMAGE and background is None:
        raise typer.BadParameter("--background is required when --mode=image")
    output_format = output.suffix.lower().lstrip(".")
    if output_format not in {"mp4", "webm", "mov", "gif"}:
        raise typer.BadParameter("Use .mp4, .webm, .mov, or .gif output")
    processor = VideoProcessor(engine, settings.ffmpeg, settings.ffprobe)
    processor.process(
        source,
        output,
        VideoOptions(
            model=model,
            edit=EditOptions(
                mode=selected_mode,
                color=color,
                blur_radius=blur_radius,
                foreground_filter=foreground_filter,
                render_mode=render_mode,
                subject_scale=subject_scale,
                subject_offset_x=subject_offset_x,
                subject_offset_y=subject_offset_y,
                auto_center=auto_center,
                outline_width=outline_width,
                outline_color=outline_color,
            ),
            max_dimension=max_dimension,
            fps=fps,
            output_format=output_format,
        ),
        background_path=background,
        on_progress=lambda progress: typer.echo(f"\r{progress:3d}%", nl=progress == 100),
    )
    typer.echo(f"Saved {output}")
