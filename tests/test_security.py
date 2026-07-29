import io

import pytest
from fastapi import HTTPException
from PIL import Image

from background_studio.security import safe_video_suffix, validate_image


def test_validate_image_rejects_non_image() -> None:
    with pytest.raises(HTTPException) as error:
        validate_image(b"not an image")
    assert error.value.status_code == 415


def test_validate_image_accepts_png() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(buffer, "PNG")
    validate_image(buffer.getvalue())


def test_video_suffix_rejects_executable() -> None:
    with pytest.raises(HTTPException):
        safe_video_suffix("payload.exe")
