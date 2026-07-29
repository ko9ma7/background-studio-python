from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

VERSION = "8.1.2"
ARCHIVE_URL = "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.1.2-essentials_build.zip"
EXPECTED_SHA256 = "db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec"


def install_directory() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local / "BackgroundStudio" / "ffmpeg" / VERSION


def resolve(name: str) -> str:
    managed = install_directory() / f"{name}.exe"
    return str(managed) if managed.exists() else name


def is_available() -> bool:
    try:
        result = subprocess.run(  # noqa: S603 - executable is managed or resolved from PATH
            [resolve("ffmpeg"), "-version"],
            check=False,
            capture_output=True,
            timeout=3,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure(progress: Callable[[float], None] | None = None) -> tuple[str, str]:
    target = install_directory()
    ffmpeg = target / "ffmpeg.exe"
    ffprobe = target / "ffprobe.exe"
    if ffmpeg.exists() and ffprobe.exists():
        if progress:
            progress(1.0)
        return str(ffmpeg), str(ffprobe)

    target.parent.mkdir(parents=True, exist_ok=True)
    archive_path = target.parent / f"ffmpeg-{VERSION}.zip.download"
    try:
        with urllib.request.urlopen(ARCHIVE_URL, timeout=60) as response:
            total = int(response.headers.get("Content-Length", "0"))
            written = 0
            digest = hashlib.sha256()
            with archive_path.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
                    if progress and total:
                        progress(min(0.9, written / total * 0.9))
        if digest.hexdigest().lower() != EXPECTED_SHA256:
            raise RuntimeError("FFmpeg 다운로드 체크섬이 일치하지 않습니다.")

        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path) as archive:
            for name in ("ffmpeg.exe", "ffprobe.exe"):
                member = next(
                    (
                        item
                        for item in archive.infolist()
                        if item.filename.lower().endswith(f"/bin/{name}")
                    ),
                    None,
                )
                if member is None:
                    raise RuntimeError(f"FFmpeg 압축 파일에 {name}이 없습니다.")
                with archive.open(member) as source, (target / name).open("wb") as output:
                    shutil.copyfileobj(source, output)
        if progress:
            progress(1.0)
        return str(ffmpeg), str(ffprobe)
    finally:
        archive_path.unlink(missing_ok=True)
