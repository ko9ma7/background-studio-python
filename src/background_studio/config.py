from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True)
class Settings:
    work_dir: Path
    max_image_bytes: int
    max_video_bytes: int
    job_ttl_hours: int
    ffmpeg: str
    ffprobe: str

    @classmethod
    def from_env(cls) -> Settings:
        work_dir = Path(os.getenv("BACKGROUND_STUDIO_WORK_DIR", "./work")).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            work_dir=work_dir,
            max_image_bytes=_positive_int("BACKGROUND_STUDIO_MAX_IMAGE_MB", 25) * 1024 * 1024,
            max_video_bytes=_positive_int("BACKGROUND_STUDIO_MAX_VIDEO_MB", 500) * 1024 * 1024,
            job_ttl_hours=_positive_int("BACKGROUND_STUDIO_JOB_TTL_HOURS", 24),
            ffmpeg=os.getenv("BACKGROUND_STUDIO_FFMPEG", "ffmpeg"),
            ffprobe=os.getenv("BACKGROUND_STUDIO_FFPROBE", "ffprobe"),
        )
