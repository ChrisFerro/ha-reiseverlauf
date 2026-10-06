"""Composite image: header with title and key figures above map and profile."""

from collections.abc import Sequence

from PIL import Image, ImageDraw

from .chart import BASE_WIDTH
from .fonts import load_font

HEADER_HEIGHT = 380
GAP = 40
VALUE_FONT_SIZES = (56, 48, 42, 36, 30, 26)


def render_composite(
    parts: Sequence[Image.Image | None],
    title: str,
    period: str,
    figures: Sequence[tuple[str, str]],
    scale: float = 1.0,
) -> Image.Image | None:
    """Stack the available parts under a header; None if no part is available."""
    images = [p for p in parts if p is not None]
    if not images:
        return None

    def s(v: float) -> int:
        return round(v * scale)

    width = s(BASE_WIDTH)
    scaled = [
        (
            img
            if img.width == width
            else img.resize((width, round(img.height * width / img.width)), Image.Resampling.LANCZOS)
        ).convert("RGB")
        for img in images
    ]
    height = s(HEADER_HEIGHT) + sum(img.height + s(GAP) for img in scaled)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    draw.text((s(80), s(50)), title, fill="#111111", font=load_font(s(72)))
    draw.text((s(80), s(150)), period, fill="#666666", font=load_font(s(36)))
    draw.line([(s(80), s(225)), (width - s(80), s(225))], fill="#cccccc", width=s(3))

    if figures:
        column = (width - s(160)) / len(figures)
        value_font = load_font(s(VALUE_FONT_SIZES[-1]))
        for size in VALUE_FONT_SIZES:
            candidate = load_font(s(size))
            if all(draw.textlength(value, font=candidate) <= column - s(30) for _, value in figures):
                value_font = candidate
                break
        label_font = load_font(s(30))
        for index, (label, value) in enumerate(figures):
            x = s(80) + index * column
            draw.text((x, s(255)), value, fill="#111111", font=value_font)
            draw.text((x, s(335)), label, fill="#777777", font=label_font)

    y = s(HEADER_HEIGHT)
    for part in scaled:
        image.paste(part, (0, y))
        y += part.height + s(GAP)
    return image
