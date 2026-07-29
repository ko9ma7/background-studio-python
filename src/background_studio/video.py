from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from .editing import EditOptions, compose
from .engine import RembgEngine
from .models import BackgroundMode, RenderMode


class VideoDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoOptions:
    model: str = "u2netp"
    edit: EditOptions = EditOptions()
    max_dimension: int = 1280
    fps: float | None = None
    output_format: str = "auto"

    def validate(self) -> None:
        self.edit.validate()
        if not 320 <= self.max_dimension <= 3840:
            raise ValueError("max_dimension must be between 320 and 3840")
        if self.fps is not None and not 1 <= self.fps <= 60:
            raise ValueError("fps must be between 1 and 60")
        if self.output_format not in {"auto", "mp4", "webm", "mov", "gif"}:
            raise ValueError("output_format must be auto, mp4, webm, mov, or gif")


class VideoProcessor:
    def __init__(self, engine: RembgEngine, ffmpeg: str, ffprobe: str) -> None:
        self.engine = engine
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    def ensure_dependencies(self) -> None:
        for executable in (self.ffmpeg, self.ffprobe):
            if shutil.which(executable) is None:
                raise VideoDependencyError(
                    f"{executable} was not found. Install FFmpeg or use the Docker image."
                )

    def _probe(self, source: Path) -> tuple[float, int]:
        result = subprocess.run(
            [
                self.ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=avg_frame_rate,nb_frames",
                "-of",
                "json",
                str(source),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        stream = json.loads(result.stdout)["streams"][0]
        rate = float(Fraction(stream.get("avg_frame_rate") or "30/1"))
        frames = int(stream.get("nb_frames") or 0)
        return rate, frames

    def process(
        self,
        source: Path,
        output: Path,
        options: VideoOptions,
        *,
        background_path: Path | None = None,
        on_progress: Callable[[int], None] | None = None,
    ) -> None:
        options.validate()
        self.ensure_dependencies()
        source_fps, reported_frames = self._probe(source)
        fps = options.fps or source_fps
        output_format = (
            output.suffix.lower().lstrip(".")
            if options.output_format == "auto"
            else options.output_format
        )
        if output_format not in {"mp4", "webm", "mov", "gif"}:
            raise ValueError("video output extension must be mp4, webm, mov, or gif")
        transparent = (
            options.edit.mode == BackgroundMode.TRANSPARENT
            and options.edit.render_mode != RenderMode.MASK
        ) or options.edit.render_mode == RenderMode.OUTLINE
        if transparent and output_format not in {"webm", "mov"}:
            raise ValueError("transparent video requires WebM or MOV output")

        with TemporaryDirectory(prefix="background-studio-") as temp_name:
            temp = Path(temp_name)
            input_frames = temp / "input"
            output_frames = temp / "output"
            input_frames.mkdir()
            output_frames.mkdir()
            scale = (
                f"scale='min({options.max_dimension},iw)':"
                f"'min({options.max_dimension},ih)':force_original_aspect_ratio=decrease"
            )
            subprocess.run(
                [
                    self.ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(source),
                    "-vf",
                    f"fps={fps},{scale}",
                    str(input_frames / "%08d.png"),
                ],
                check=True,
            )
            frame_paths = sorted(input_frames.glob("*.png"))
            total = max(reported_frames, len(frame_paths), 1)
            background = Image.open(background_path).convert("RGBA") if background_path else None
            for index, frame_path in enumerate(frame_paths, start=1):
                with Image.open(frame_path) as frame:
                    original = frame.convert("RGBA")
                    cutout = self.engine.remove(original, model=options.model)
                    result = compose(original, cutout, options.edit, background)
                    result.save(output_frames / frame_path.name, "PNG")
                if on_progress:
                    on_progress(min(95, round(index / total * 95)))

            output.parent.mkdir(parents=True, exist_ok=True)
            if output_format == "webm":
                encode = [
                    "-c:v",
                    "libvpx-vp9",
                    "-pix_fmt",
                    "yuva420p" if transparent else "yuv420p",
                    "-auto-alt-ref",
                    "0",
                    "-b:v",
                    "0",
                    "-crf",
                    "24",
                ]
                audio = ["-c:a", "libopus"]
            elif output_format == "mov" and transparent:
                encode = [
                    "-c:v",
                    "prores_ks",
                    "-profile:v",
                    "4444",
                    "-pix_fmt",
                    "yuva444p10le",
                ]
                audio = ["-c:a", "pcm_s16le"]
            elif output_format == "gif":
                encode = [
                    "-vf",
                    "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
                    "-loop",
                    "0",
                ]
                audio = ["-an"]
            else:
                encode = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20"]
                audio = ["-c:a", "aac"]
            subprocess.run(
                [
                    self.ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-framerate",
                    str(fps),
                    "-i",
                    str(output_frames / "%08d.png"),
                    "-i",
                    str(source),
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a?",
                    *encode,
                    *audio,
                    "-shortest",
                    "-y",
                    str(output),
                ],
                check=True,
            )
            if on_progress:
                on_progress(100)
