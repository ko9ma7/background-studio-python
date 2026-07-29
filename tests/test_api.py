import io

from fastapi.testclient import TestClient
from PIL import Image

from background_studio import api


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (3, 3), "white").save(buffer, "PNG")
    return buffer.getvalue()


class FakeEngine:
    def remove(self, image, **_kwargs):
        return image.convert("RGBA")


def test_health_reports_local_privacy(monkeypatch) -> None:
    monkeypatch.setattr(api.video_processor, "ensure_dependencies", lambda: None)
    response = TestClient(api.app).get("/healthz")
    assert response.status_code == 200
    assert response.json()["ffmpeg_available"] is True
    assert "locally" in response.json()["privacy"]


def test_image_endpoint_returns_png(monkeypatch) -> None:
    monkeypatch.setattr(api, "engine", FakeEngine())
    response = TestClient(api.app).post(
        "/v1/images/remove",
        files={"file": ("test.png", png_bytes(), "image/png")},
        data={"mode": "color", "color": "#123456"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(response.content)).getpixel((0, 0))[:3] == (255, 255, 255)


def test_image_mode_requires_background(monkeypatch) -> None:
    monkeypatch.setattr(api, "engine", FakeEngine())
    response = TestClient(api.app).post(
        "/v1/images/remove",
        files={"file": ("test.png", png_bytes(), "image/png")},
        data={"mode": "image"},
    )
    assert response.status_code == 422
