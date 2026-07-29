from PIL import Image

from background_studio.editing import (
    EditOptions,
    compose,
    prepare_foreground,
    to_image_bytes,
    to_svg_outline,
)
from background_studio.models import BackgroundMode, ForegroundFilter, RenderMode


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


def test_auto_center_moves_subject_and_outline_is_transparent() -> None:
    cutout = Image.new("RGBA", (20, 10), (0, 0, 0, 0))
    for x in range(2, 6):
        for y in range(2, 8):
            cutout.putpixel((x, y), (255, 20, 10, 255))
    options = EditOptions(
        auto_center=True,
        subject_scale=0.5,
        foreground_filter=ForegroundFilter.VIVID,
        render_mode=RenderMode.OUTLINE,
        outline_width=1,
    )

    foreground = prepare_foreground(cutout, options)
    result = compose(cutout, cutout, options)

    assert foreground.getchannel("A").getbbox() == (9, 4, 11, 7)
    assert result.getchannel("A").getbbox() is not None


def test_image_export_formats_and_svg_outline() -> None:
    image = Image.new("RGBA", (8, 8), (255, 0, 0, 128))
    for output_format in ("png", "jpg", "webp", "bmp", "tiff"):
        assert to_image_bytes(image, output_format)
    svg = to_svg_outline(image)
    assert svg.startswith("<svg")
    assert "<path" in svg
