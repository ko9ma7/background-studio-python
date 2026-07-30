from PIL import Image

from background_studio.editing import (
    EditOptions,
    MaskStroke,
    apply_mask_strokes,
    compose,
    prepare_foreground,
    to_image_bytes,
    to_svg_outline,
)
from background_studio.models import BackgroundMode, CanvasAspect, ForegroundFilter, RenderMode


def test_manual_mask_strokes_erase_and_restore_ai_alpha() -> None:
    cutout = Image.new("RGBA", (12, 6), (30, 60, 90, 180))
    result = apply_mask_strokes(
        cutout,
        [
            MaskStroke("erase", 0.3, ((0.5, 0.5),)),
            MaskStroke("restore", 0.08, ((0.5, 0.5),)),
        ],
    )

    assert result.getpixel((6, 3))[3] == 180
    assert result.getpixel((4, 3))[3] == 0


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


def test_advanced_color_mask_transform_and_canvas_controls() -> None:
    source = Image.new("RGBA", (20, 10), (0, 0, 0, 0))
    for x in range(3, 9):
        for y in range(2, 8):
            source.putpixel((x, y), (120, 80, 40, 180))
    options = EditOptions(
        foreground_filter=ForegroundFilter.POSTERIZE,
        brightness=1.2,
        contrast=1.3,
        saturation=0.7,
        temperature=0.25,
        hue=30,
        foreground_opacity=0.8,
        rotation=25,
        flip_horizontal=True,
        mask_threshold=0.2,
        mask_feather=0.1,
        mask_expansion=-1,
        auto_center=True,
        canvas_aspect=CanvasAspect.SQUARE,
    )

    result = compose(source, source, options)

    assert result.size == (10, 10)
    assert result.getchannel("A").getbbox() is not None
    assert max(result.getchannel("A").getextrema()) < 255
