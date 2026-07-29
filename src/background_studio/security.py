from __future__ import annotations

import io
import re
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

SAFE_SUFFIX = re.compile(r"^\.[a-z0-9]{1,8}$")
IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "TIFF"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v", ".ogg"}


async def read_limited(upload: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(1024 * 1024):
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail="Uploaded file exceeds the configured limit",
            )
        chunks.append(chunk)
    if not chunks:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    return b"".join(chunks)


def validate_image(data: bytes) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in IMAGE_FORMATS:
                raise HTTPException(status_code=415, detail="Unsupported image format")
            image.verify()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=415, detail="Invalid image file") from exc


def safe_video_suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in VIDEO_SUFFIXES or not SAFE_SUFFIX.fullmatch(suffix):
        raise HTTPException(status_code=415, detail="Unsupported video format")
    return suffix
