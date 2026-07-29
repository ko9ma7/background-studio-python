from __future__ import annotations

import io
from threading import Lock

from PIL import Image

SUPPORTED_MODELS = (
    "u2net",
    "u2netp",
    "u2net_human_seg",
    "isnet-general-use",
    "isnet-anime",
    "birefnet-general",
    "birefnet-portrait",
)


class RembgEngine:
    def __init__(self) -> None:
        self._locks: dict[str, Lock] = {}
        self._locks_guard = Lock()
        self._sessions: dict[str, object] = {}

    def _session(self, model: str):
        if model not in SUPPORTED_MODELS:
            raise ValueError(f"Unsupported model: {model}")
        with self._locks_guard:
            if model not in self._sessions:
                from rembg import new_session

                self._sessions[model] = new_session(model)
            return self._sessions[model]

    def _lock_for(self, model: str) -> Lock:
        with self._locks_guard:
            return self._locks.setdefault(model, Lock())

    def remove(
        self,
        image: Image.Image,
        *,
        model: str = "u2netp",
        alpha_matting: bool = False,
        foreground_threshold: int = 240,
        background_threshold: int = 10,
        erode_size: int = 10,
        post_process_mask: bool = False,
    ) -> Image.Image:
        from rembg import remove

        if not 0 <= foreground_threshold <= 255:
            raise ValueError("foreground_threshold must be between 0 and 255")
        if not 0 <= background_threshold <= 255:
            raise ValueError("background_threshold must be between 0 and 255")
        if not 0 <= erode_size <= 100:
            raise ValueError("erode_size must be between 0 and 100")

        with self._lock_for(model):
            result = remove(
                image.convert("RGB"),
                session=self._session(model),
                alpha_matting=alpha_matting,
                alpha_matting_foreground_threshold=foreground_threshold,
                alpha_matting_background_threshold=background_threshold,
                alpha_matting_erode_size=erode_size,
                post_process_mask=post_process_mask,
            )
        if isinstance(result, bytes):
            result = Image.open(io.BytesIO(result))
        return result.convert("RGBA")
