from __future__ import annotations

from pathlib import Path

import typer
from PIL import Image

from .config import Settings
from .editing import EditOptions, compose
from .engine import SUPPORTED_MODELS, RembgEngine
from .models import BackgroundMode
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
) -> None:
    selected_mode = _mode(mode)
    if selected_mode == BackgroundMode.IMAGE and background is None:
        raise typer.BadParameter("--background is required when --mode=image")
    with Image.open(source) as opened:
        original = opened.convert("RGBA")
    cutout = engine.remove(original, model=model, alpha_matting=alpha_matting)
    background_image = Image.open(background).convert("RGBA") if background else None
    result = compose(
        original,
        cutout,
        EditOptions(mode=selected_mode, color=color, blur_radius=blur_radius),
        background_image,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output, "PNG")
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
) -> None:
    settings = Settings.from_env()
    selected_mode = _mode(mode)
    if selected_mode == BackgroundMode.IMAGE and background is None:
        raise typer.BadParameter("--background is required when --mode=image")
    expected = ".webm" if selected_mode == BackgroundMode.TRANSPARENT else ".mp4"
    if output.suffix.lower() != expected:
        raise typer.BadParameter(f"Use {expected} output for {selected_mode.value} mode")
    processor = VideoProcessor(engine, settings.ffmpeg, settings.ffprobe)
    processor.process(
        source,
        output,
        VideoOptions(
            model=model,
            edit=EditOptions(mode=selected_mode, color=color, blur_radius=blur_radius),
            max_dimension=max_dimension,
            fps=fps,
        ),
        background_path=background,
        on_progress=lambda progress: typer.echo(f"\r{progress:3d}%", nl=progress == 100),
    )
    typer.echo(f"Saved {output}")
