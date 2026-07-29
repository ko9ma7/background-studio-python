from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageColor, ImageEnhance, ImageFilter, ImageOps

from .models import BackgroundMode, CanvasAspect, ForegroundFilter, RenderMode


@dataclass(frozen=True)
class EditOptions:
    mode: BackgroundMode = BackgroundMode.TRANSPARENT
    color: str = "#ffffff"
    blur_radius: float = 18.0
    shadow_blur: float = 0.0
    shadow_opacity: int = 80
    shadow_offset_x: int = 0
    shadow_offset_y: int = 12
    foreground_filter: ForegroundFilter = ForegroundFilter.ORIGINAL
    render_mode: RenderMode = RenderMode.COMPOSITE
    subject_scale: float = 1.0
    subject_offset_x: float = 0.0
    subject_offset_y: float = 0.0
    auto_center: bool = False
    outline_width: int = 3
    outline_color: str = "#111111"
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    temperature: float = 0.0
    hue: float = 0.0
    foreground_opacity: float = 1.0
    rotation: float = 0.0
    flip_horizontal: bool = False
    flip_vertical: bool = False
    mask_threshold: float = 0.0
    mask_feather: float = 0.0
    mask_expansion: int = 0
    canvas_aspect: CanvasAspect = CanvasAspect.ORIGINAL

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
        if not 0.1 <= self.subject_scale <= 3:
            raise ValueError("subject_scale must be between 0.1 and 3")
        if not -1 <= self.subject_offset_x <= 1 or not -1 <= self.subject_offset_y <= 1:
            raise ValueError("subject offsets must be between -1 and 1")
        if not 1 <= self.outline_width <= 50:
            raise ValueError("outline_width must be between 1 and 50")
        for name, value in (
            ("brightness", self.brightness),
            ("contrast", self.contrast),
            ("saturation", self.saturation),
        ):
            if not 0 <= value <= 3:
                raise ValueError(f"{name} must be between 0 and 3")
        if not -1 <= self.temperature <= 1:
            raise ValueError("temperature must be between -1 and 1")
        if not -180 <= self.hue <= 180 or not -180 <= self.rotation <= 180:
            raise ValueError("hue and rotation must be between -180 and 180")
        if not 0 <= self.foreground_opacity <= 1:
            raise ValueError("foreground_opacity must be between 0 and 1")
        if not 0 <= self.mask_threshold <= 1 or not 0 <= self.mask_feather <= 0.5:
            raise ValueError("mask threshold and feather are outside their allowed range")
        if not -12 <= self.mask_expansion <= 12:
            raise ValueError("mask_expansion must be between -12 and 12")
        try:
            ImageColor.getrgb(self.outline_color)
        except ValueError as exc:
            raise ValueError("outline_color must be a valid CSS color") from exc


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


def _apply_filter(cutout: Image.Image, preset: ForegroundFilter) -> Image.Image:
    if preset == ForegroundFilter.ORIGINAL:
        return cutout
    alpha = cutout.getchannel("A")
    rgb = cutout.convert("RGB")
    if preset == ForegroundFilter.BRIGHT:
        rgb = ImageEnhance.Brightness(rgb).enhance(1.15)
    elif preset == ForegroundFilter.VIVID:
        rgb = ImageEnhance.Contrast(ImageEnhance.Color(rgb).enhance(1.4)).enhance(1.12)
    elif preset == ForegroundFilter.WARM:
        red, green, blue = rgb.split()
        rgb = Image.merge(
            "RGB",
            (
                red.point(lambda value: min(255, round(value * 1.08 + 5))),
                green.point(lambda value: min(255, round(value * 1.02))),
                blue.point(lambda value: round(value * 0.9)),
            ),
        )
    elif preset == ForegroundFilter.COOL:
        red, green, blue = rgb.split()
        rgb = Image.merge(
            "RGB",
            (
                red.point(lambda value: round(value * 0.9)),
                green.point(lambda value: min(255, round(value * 1.02))),
                blue.point(lambda value: min(255, round(value * 1.1 + 4))),
            ),
        )
    elif preset == ForegroundFilter.GRAYSCALE:
        rgb = ImageOps.grayscale(rgb).convert("RGB")
    elif preset == ForegroundFilter.COMIC:
        smooth = rgb.filter(ImageFilter.MedianFilter(3))
        colors = ImageOps.posterize(ImageEnhance.Color(smooth).enhance(1.35), 4)
        edges = ImageOps.invert(
            ImageOps.grayscale(smooth).filter(ImageFilter.FIND_EDGES)
        ).point(lambda value: 255 if value > 150 else 35)
        rgb = ImageChops.multiply(colors, Image.merge("RGB", (edges, edges, edges)))
    elif preset == ForegroundFilter.HIGH_CONTRAST:
        rgb = ImageEnhance.Contrast(rgb).enhance(1.55)
    elif preset == ForegroundFilter.POSTERIZE:
        rgb = ImageOps.posterize(rgb, 3)
    elif preset == ForegroundFilter.SEPIA:
        grayscale = ImageOps.grayscale(rgb)
        rgb = ImageOps.colorize(grayscale, "#3a2415", "#f2d6a2")
    elif preset == ForegroundFilter.INVERT:
        rgb = ImageOps.invert(rgb)
    elif preset == ForegroundFilter.PENCIL:
        edges = ImageOps.grayscale(rgb).filter(ImageFilter.FIND_EDGES)
        rgb = ImageOps.invert(edges).point(lambda value: 255 if value > 205 else 25).convert("RGB")
    return Image.merge("RGBA", (*rgb.split(), alpha))


def _adjust_foreground(source: Image.Image, options: EditOptions) -> Image.Image:
    alpha = source.getchannel("A")
    rgb = source.convert("RGB")
    rgb = ImageEnhance.Brightness(rgb).enhance(options.brightness)
    rgb = ImageEnhance.Contrast(rgb).enhance(options.contrast)
    rgb = ImageEnhance.Color(rgb).enhance(options.saturation)
    if options.temperature:
        red, green, blue = rgb.split()
        offset = round(options.temperature * 30)
        red = red.point(lambda value: max(0, min(255, value + offset)))
        blue = blue.point(lambda value: max(0, min(255, value - offset)))
        rgb = Image.merge("RGB", (red, green, blue))
    if options.hue:
        hsv = rgb.convert("HSV")
        hue, saturation, value = hsv.split()
        shift = round(options.hue / 360 * 255)
        hue = hue.point(lambda channel: (channel + shift) % 256)
        rgb = Image.merge("HSV", (hue, saturation, value)).convert("RGB")
    if options.mask_threshold or options.mask_feather:
        threshold = options.mask_threshold * 255
        feather = options.mask_feather * 255
        if feather:
            alpha = alpha.point(
                lambda value: max(
                    0,
                    min(255, round((value - threshold + feather) / (2 * feather) * 255)),
                )
            )
        else:
            alpha = alpha.point(lambda value: 255 if value >= threshold else 0)
    if options.mask_expansion:
        kernel = abs(options.mask_expansion) * 2 + 1
        alpha = alpha.filter(
            ImageFilter.MaxFilter(kernel)
            if options.mask_expansion > 0
            else ImageFilter.MinFilter(kernel)
        )
    if options.foreground_opacity != 1:
        alpha = alpha.point(lambda value: round(value * options.foreground_opacity))
    return Image.merge("RGBA", (*rgb.split(), alpha))


def prepare_foreground(cutout: Image.Image, options: EditOptions) -> Image.Image:
    source = _adjust_foreground(
        _apply_filter(cutout.convert("RGBA"), options.foreground_filter),
        options,
    )
    alpha_box = source.getchannel("A").getbbox()
    if alpha_box is None:
        return Image.new("RGBA", source.size, (0, 0, 0, 0))
    crop = source.crop(alpha_box)
    width = max(1, round(crop.width * options.subject_scale))
    height = max(1, round(crop.height * options.subject_scale))
    if (width, height) != crop.size:
        crop = crop.resize((width, height), Image.Resampling.LANCZOS)
    if options.flip_horizontal:
        crop = ImageOps.mirror(crop)
    if options.flip_vertical:
        crop = ImageOps.flip(crop)
    if options.rotation:
        crop = crop.rotate(
            -options.rotation,
            resample=Image.Resampling.BICUBIC,
            expand=True,
        )
        width, height = crop.size
    if options.auto_center:
        center_x = source.width / 2
        center_y = source.height / 2
    else:
        center_x = (alpha_box[0] + alpha_box[2]) / 2
        center_y = (alpha_box[1] + alpha_box[3]) / 2
    center_x += options.subject_offset_x * source.width
    center_y += options.subject_offset_y * source.height
    positioned = Image.new("RGBA", source.size, (0, 0, 0, 0))
    positioned.alpha_composite(crop, (round(center_x - width / 2), round(center_y - height / 2)))
    return positioned


def _canvas_size(size: tuple[int, int], aspect: CanvasAspect) -> tuple[int, int]:
    width, height = size
    if aspect == CanvasAspect.ORIGINAL:
        return size
    ratio = {
        CanvasAspect.SQUARE: 1.0,
        CanvasAspect.PORTRAIT_45: 4 / 5,
        CanvasAspect.LANDSCAPE_169: 16 / 9,
    }[aspect]
    if width / height > ratio:
        return max(1, round(height * ratio)), height
    return width, max(1, round(width / ratio))


def _center_crop(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    left = (source.width - size[0]) // 2
    top = (source.height - size[1]) // 2
    return source.crop((left, top, left + size[0], top + size[1]))


def _mask_layer(cutout: Image.Image) -> Image.Image:
    alpha = cutout.getchannel("A")
    result = Image.new("RGBA", cutout.size, "black")
    result.paste(Image.new("RGBA", cutout.size, "white"), mask=alpha)
    return result


def _outline_layer(cutout: Image.Image, width: int, color: str) -> Image.Image:
    alpha = cutout.getchannel("A")
    kernel = width * 2 + 1
    outer = alpha.filter(ImageFilter.MaxFilter(kernel))
    inner = alpha.filter(ImageFilter.MinFilter(kernel))
    edge = ImageChops.subtract(outer, inner)
    result = Image.new("RGBA", cutout.size, ImageColor.getrgb(color) + (0,))
    result.putalpha(edge)
    return result


def compose(
    original: Image.Image,
    cutout: Image.Image,
    options: EditOptions,
    background: Image.Image | None = None,
) -> Image.Image:
    options.validate()
    size = _canvas_size(cutout.size, options.canvas_aspect)
    foreground = _center_crop(prepare_foreground(cutout, options), size)
    if options.render_mode == RenderMode.MASK:
        return _mask_layer(foreground)
    if options.render_mode == RenderMode.OUTLINE:
        return _outline_layer(
            foreground,
            options.outline_width,
            options.outline_color,
        )
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
        canvas.alpha_composite(_shadow_layer(foreground, options))
    canvas.alpha_composite(foreground)
    return canvas


def to_image_bytes(image: Image.Image, output_format: str = "png", quality: int = 92) -> bytes:
    normalized = output_format.lower()
    formats = {
        "png": ("PNG", "image/png"),
        "jpg": ("JPEG", "image/jpeg"),
        "jpeg": ("JPEG", "image/jpeg"),
        "webp": ("WEBP", "image/webp"),
        "bmp": ("BMP", "image/bmp"),
        "tiff": ("TIFF", "image/tiff"),
    }
    if normalized not in formats:
        raise ValueError("output_format must be png, jpg, webp, bmp, or tiff")
    pillow_format, _ = formats[normalized]
    save_image = image
    if pillow_format in {"JPEG", "BMP"}:
        matte = Image.new("RGB", image.size, "white")
        if image.mode == "RGBA":
            matte.paste(image, mask=image.getchannel("A"))
        else:
            matte.paste(image.convert("RGB"))
        save_image = matte
    output = io.BytesIO()
    kwargs = {"quality": quality} if pillow_format in {"JPEG", "WEBP"} else {}
    if pillow_format == "PNG":
        kwargs["optimize"] = True
    save_image.save(output, format=pillow_format, **kwargs)
    return output.getvalue()


def media_type_for(output_format: str) -> str:
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "bmp": "image/bmp",
        "tiff": "image/tiff",
    }[output_format.lower()]


def to_svg_outline(
    cutout: Image.Image,
    threshold: int = 128,
    max_side: int = 512,
    stroke_color: str = "#111111",
    stroke_width: int = 2,
) -> str:
    red, green, blue = ImageColor.getrgb(stroke_color)
    normalized_color = f"#{red:02x}{green:02x}{blue:02x}"
    alpha = cutout.getchannel("A")
    scale = min(1.0, max_side / max(alpha.size))
    if scale < 1:
        alpha = alpha.resize(
            (max(1, round(alpha.width * scale)), max(1, round(alpha.height * scale))),
            Image.Resampling.LANCZOS,
        )
    pixels = alpha.load()
    segments: dict[tuple[int, int], list[tuple[int, int]]] = {}

    def add(start: tuple[int, int], end: tuple[int, int]) -> None:
        segments.setdefault(start, []).append(end)

    for y in range(alpha.height):
        for x in range(alpha.width):
            if pixels[x, y] < threshold:
                continue
            if y == 0 or pixels[x, y - 1] < threshold:
                add((x + 1, y), (x, y))
            if x == alpha.width - 1 or pixels[x + 1, y] < threshold:
                add((x + 1, y + 1), (x + 1, y))
            if y == alpha.height - 1 or pixels[x, y + 1] < threshold:
                add((x, y + 1), (x + 1, y + 1))
            if x == 0 or pixels[x - 1, y] < threshold:
                add((x, y), (x, y + 1))

    paths: list[str] = []
    while segments:
        start = next(iter(segments))
        points = [start]
        current = start
        while current in segments:
            next_point = segments[current].pop()
            if not segments[current]:
                del segments[current]
            points.append(next_point)
            current = next_point
            if current == start:
                break
        if len(points) > 3:
            simplified = [points[0]]
            for index in range(1, len(points) - 1):
                previous = simplified[-1]
                current_point = points[index]
                following = points[index + 1]
                if (
                    (previous[0] == current_point[0] == following[0])
                    or (previous[1] == current_point[1] == following[1])
                ):
                    continue
                simplified.append(current_point)
            simplified.append(points[-1])
            factor = 1 / scale
            commands = " ".join(
                f"{'M' if index == 0 else 'L'}{point[0] * factor:.2f},{point[1] * factor:.2f}"
                for index, point in enumerate(simplified)
            )
            paths.append(f"{commands} Z")
    path_data = " ".join(paths)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {cutout.width} {cutout.height}">'
        f'<path d="{path_data}" fill="none" stroke="{normalized_color}" '
        f'stroke-width="{stroke_width}" '
        'stroke-linejoin="round"/></svg>'
    )
