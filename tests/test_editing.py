from PIL import Image

from background_studio.editing import EditOptions, compose
from background_studio.models import BackgroundMode


def test_color_composite_keeps_foreground_and_replaces_background() -> None:
    original = Image.new("RGBA", (4, 4), (20, 30, 40, 255))
    cutout = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    cutout.putpixel((1, 1), (255, 0, 0, 255))

    result = compose(
        original,
        cutout,
        EditOptions(mode=BackgroundMode.COLOR, color="#00ff00"),
    )

    assert result.getpixel((0, 0)) == (0, 255, 0, 255)
    assert result.getpixel((1, 1)) == (255, 0, 0, 255)


def test_image_background_uses_cover_crop() -> None:
    original = Image.new("RGBA", (4, 4), "white")
    cutout = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    background = Image.new("RGBA", (8, 2), "blue")

    result = compose(
        original,
        cutout,
        EditOptions(mode=BackgroundMode.IMAGE),
        background,
    )

    assert result.size == (4, 4)
    assert result.getpixel((0, 0)) == (0, 0, 255, 255)
