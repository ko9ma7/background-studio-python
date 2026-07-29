from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageColor, ImageFilter

from .models import BackgroundMode


@dataclass(frozen=True)
class EditOptions:
    mode: BackgroundMode = BackgroundMode.TRANSPARENT
    color: str = "#ffffff"
    blur_radius: float = 18.0
    shadow_blur: float = 0.0
    shadow_opacity: int = 80
    shadow_offset_x: int = 0
    shadow_offset_y: int = 12

    def validate(self) -> None:
        try:
            ImageColor.getrgb(self.color)
        except ValueError as exc:
            raise ValueError("color must be a valid CSS color") from exc
        if not 0 <= self.blur_radius <= 100:
            raise ValueError("blur_radius must be between 0 and 100")
        if not 0 <= self.shadow_blur <= 100:
            raise ValueError("shadow_blur must be between 0 and 100")
        if not 0 <= self.shadow_opacity <= 255:
            raise ValueError("shadow_opacity must be between 0 and 255")


def open_rgba(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image.convert("RGBA")


def _cover(background: Image.Image, size: tuple[int, int]) -> Image.Image:
    source = background.convert("RGBA")
    scale = max(size[0] / source.width, size[1] / source.height)
    resized = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = (resized.width - size[0]) // 2
    top = (resized.height - size[1]) // 2
    return resized.crop((left, top, left + size[0], top + size[1]))


def _shadow_layer(cutout: Image.Image, options: EditOptions) -> Image.Image:
    alpha = cutout.getchannel("A")
    if options.shadow_blur:
        alpha = alpha.filter(ImageFilter.GaussianBlur(options.shadow_blur))
    opacity = alpha.point(lambda value: value * options.shadow_opacity // 255)
    shadow = Image.new("RGBA", cutout.size, (0, 0, 0, 0))
    black = Image.new("RGBA", cutout.size, (0, 0, 0, 255))
    shadow.alpha_composite(black, (options.shadow_offset_x, options.shadow_offset_y))
    shadow.putalpha(opacity)
    return shadow


def compose(
    original: Image.Image,
    cutout: Image.Image,
    options: EditOptions,
    background: Image.Image | None = None,
) -> Image.Image:
    options.validate()
    size = cutout.size
    if options.mode == BackgroundMode.TRANSPARENT:
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    elif options.mode == BackgroundMode.COLOR:
        canvas = Image.new("RGBA", size, ImageColor.getrgb(options.color) + (255,))
    elif options.mode == BackgroundMode.IMAGE:
        if background is None:
            raise ValueError("background image is required for image mode")
        canvas = _cover(background, size)
    elif options.mode == BackgroundMode.BLUR:
        canvas = _cover(original, size).filter(ImageFilter.GaussianBlur(options.blur_radius))
    else:
        raise ValueError(f"unsupported background mode: {options.mode}")

    if options.shadow_blur or options.shadow_offset_x or options.shadow_offset_y:
        canvas.alpha_composite(_shadow_layer(cutout, options))
    canvas.alpha_composite(cutout)
    return canvas


def to_png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
