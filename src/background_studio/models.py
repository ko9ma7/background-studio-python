from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from threading import Lock
from time import time
from uuid import uuid4


class BackgroundMode(StrEnum):
    TRANSPARENT = "transparent"
    COLOR = "color"
    IMAGE = "image"
    BLUR = "blur"


class ForegroundFilter(StrEnum):
    ORIGINAL = "original"
    BRIGHT = "bright"
    VIVID = "vivid"
    WARM = "warm"
    COOL = "cool"
    GRAYSCALE = "grayscale"
    COMIC = "comic"


class RenderMode(StrEnum):
    COMPOSITE = "composite"
    MASK = "mask"
    OUTLINE = "outline"


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class VideoJob:
    id: str
    status: JobStatus
    created_at: float
    updated_at: float
    source_path: Path
    output_path: Path | None = None
    progress: int = 0
    error: str | None = None

    def public(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("source_path")
        payload["output_path"] = None
        payload["download_url"] = (
            f"/v1/jobs/{self.id}/download" if self.status == JobStatus.COMPLETE else None
        )
        return payload


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, VideoJob] = {}
        self._lock = Lock()

    def create(self, source_path: Path) -> VideoJob:
        now = time()
        job = VideoJob(
            id=uuid4().hex,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
            source_path=source_path,
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> VideoJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **changes: object) -> VideoJob:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in changes.items():
                if not hasattr(job, key):
                    raise AttributeError(key)
                setattr(job, key, value)
            job.updated_at = time()
            return job

    def delete_expired(self, ttl_hours: int) -> None:
        cutoff = time() - ttl_hours * 3600
        with self._lock:
            expired = [job_id for job_id, job in self._jobs.items() if job.updated_at < cutoff]
            for job_id in expired:
                job = self._jobs.pop(job_id)
                for path in (job.source_path, job.output_path):
                    if path and path.exists():
                        path.unlink(missing_ok=True)
