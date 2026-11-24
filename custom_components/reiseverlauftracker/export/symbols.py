"""
Map symbols drawn with Pillow: pictograms in coloured circles, their layout and the legend.

The pictograms are built from shapes, not taken from a font, so that they look the
same with any installed fonts and stay sharp at every scale
(docs/features/feat-12-kartensymbole.md 5.3).
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
import math

from PIL import Image, ImageDraw, ImageFilter

from custom_components.reiseverlauftracker.utils.geo import Position, distance_m

from .fonts import load_font
from .model import MapMarker, MarkerKind

SUPERSAMPLE = 4
RING = 0.08
"""Width of the white ring, as a fraction of the diameter."""
PICTOGRAM = "#ffffff"

COLORS: dict[MarkerKind, str] = {
    MarkerKind.START: "#2a9d8f",
    MarkerKind.END: "#1d3557",
    MarkerKind.PITCH: "#6d597a",
    MarkerKind.STOP: "#6c757d",
    MarkerKind.FUEL: "#212529",
    MarkerKind.GAS: "#e76f51",
    MarkerKind.FERRY: "#1d72b8",
}

DRAW_ORDER: tuple[MarkerKind, ...] = (
    MarkerKind.STOP,
    MarkerKind.PITCH,
    MarkerKind.FUEL,
    MarkerKind.GAS,
    MarkerKind.FERRY,
    MarkerKind.START,
    MarkerKind.END,
)
"""Later kinds are drawn on top (6.4)."""

LEGEND_ORDER: tuple[MarkerKind, ...] = (
    MarkerKind.START,
    MarkerKind.END,
    MarkerKind.PITCH,
    MarkerKind.STOP,
    MarkerKind.FUEL,
    MarkerKind.GAS,
    MarkerKind.FERRY,
)

type Draw = ImageDraw.ImageDraw
type Point = tuple[float, float]


def merge_markers(markers: Iterable[MapMarker], same_place_m: float) -> list[MapMarker]:
    """
    Drop the stop symbol where fuel or gas was bought at the same place (5.4).

    A stop counts as the same place when a fuel or gas symbol lies within `same_place_m`.
    """
    markers = list(markers)
    refills = [m for m in markers if m.kind in (MarkerKind.FUEL, MarkerKind.GAS)]
    return [
        m
        for m in markers
        if m.kind is not MarkerKind.STOP
        or not any(distance_m(Position(m.lat, m.lon), Position(r.lat, r.lon)) <= same_place_m for r in refills)
    ]


def layout(markers: Sequence[tuple[MarkerKind, Point]], diameter: float) -> list[tuple[MarkerKind, Point]]:
    """
    Return the symbols in drawing order, moved aside where they would cover each other (5.4).

    Each symbol keeps its place if it is free; otherwise it moves one diameter to the
    first free side (right, left, up, down, then the diagonals). If no side is free,
    it stays where it is.
    """
    order = {kind: i for i, kind in enumerate(DRAW_ORDER)}
    ordered = sorted(markers, key=lambda m: order[m[0]])
    # Place the symbols on top first, so that start and end keep their exact position.
    placed: list[tuple[MarkerKind, Point]] = []
    minimum = diameter * 0.9
    steps = [(1, 0), (-1, 0), (0, -1), (0, 1), (1, -1), (-1, -1), (1, 1), (-1, 1)]
    for kind, (x, y) in reversed(ordered):
        candidates = [(x, y)] + [(x + dx * diameter, y + dy * diameter) for dx, dy in steps]
        spot = next(
            (c for c in candidates if all(math.dist(c, p) >= minimum for _, p in placed)),
            (x, y),
        )
        placed.append((kind, spot))
    placed.reverse()
    return placed


def symbol_image(kind: MarkerKind, diameter: int) -> Image.Image:
    """Return one symbol as an RGBA image of `diameter` pixels plus room for its shadow."""
    pad = max(diameter // 8, 1)
    size = diameter + 2 * pad
    big = size * SUPERSAMPLE
    d = diameter * SUPERSAMPLE
    p = pad * SUPERSAMPLE

    shadow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse((p, p + p // 2, p + d, p + d + p // 2), fill=(0, 0, 0, 90))
    image = shadow.filter(ImageFilter.GaussianBlur(p / 2))

    draw = ImageDraw.Draw(image)
    draw.ellipse((p, p, p + d, p + d), fill="#ffffff")
    ring = d * RING
    draw.ellipse((p + ring, p + ring, p + d - ring, p + d - ring), fill=COLORS[kind])

    centre = p + d / 2
    radius = d / 2 - ring
    _PICTOGRAMS[kind](draw, _unit(centre, centre, radius * 0.62))
    return image.resize((size, size), Image.Resampling.LANCZOS)


def draw_symbol(image: Image.Image, kind: MarkerKind, centre: Point, diameter: int) -> None:
    """Draw one symbol centred on `centre` into the RGBA `image`."""
    symbol = symbol_image(kind, diameter)
    x = round(centre[0] - symbol.width / 2)
    y = round(centre[1] - symbol.height / 2)
    if x >= 0 and y >= 0 and x + symbol.width <= image.width and y + symbol.height <= image.height:
        image.alpha_composite(symbol, (x, y))
    else:
        # Partly outside the image: paste clips, alpha_composite would refuse.
        image.paste(symbol, (x, y), symbol)


def render_legend(
    kinds: Iterable[MarkerKind],
    labels: Mapping[MarkerKind, str],
    width: int,
    scale: float = 1.0,
) -> Image.Image | None:
    """
    Return a one-line legend of the given kinds, centred on a white strip of `width` (5.5).

    Kinds appear in a fixed order; None if there is nothing to explain.
    """
    present = set(kinds)
    shown = [k for k in LEGEND_ORDER if k in present]
    if not shown:
        return None

    def s(v: float) -> int:
        return max(round(v * scale), 1)

    diameter, gap, spacing = s(40), s(14), s(48)
    font = load_font(s(30))
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    widths = [probe.textlength(labels.get(k, k.value), font=font) for k in shown]
    total = sum(diameter + gap + w for w in widths) + spacing * (len(shown) - 1)
    height = s(80)
    image = Image.new("RGBA", (width, height), "white")
    draw = ImageDraw.Draw(image)
    x = max((width - total) / 2, s(40))
    for kind, text_width in zip(shown, widths, strict=True):
        draw_symbol(image, kind, (x + diameter / 2, height / 2), diameter)
        x += diameter + gap
        draw.text((x, height / 2), labels.get(kind, kind.value), fill="#333333", font=font, anchor="lm")
        x += text_width + spacing
    return image.convert("RGB")


# Pictograms. Each one draws into a square of side 2 around the centre, given as a
# function that maps unit coordinates (-1 … 1, y downwards) to pixels.

type Unit = Callable[[float, float], Point]


def _unit(cx: float, cy: float, r: float) -> Unit:
    return lambda x, y: (cx + x * r, cy + y * r)


def _box(u: Unit, x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
    (a, b), (c, d) = u(x0, y0), u(x1, y1)
    return a, b, c, d


def _width(u: Unit, w: float) -> int:
    return max(round(u(w, 0)[0] - u(0, 0)[0]), 1)


def _pause(draw: Draw, u: Unit) -> None:
    draw.rectangle(_box(u, -0.6, -0.75, -0.15, 0.75), fill=PICTOGRAM)
    draw.rectangle(_box(u, 0.15, -0.75, 0.6, 0.75), fill=PICTOGRAM)


def _fuel_pump(draw: Draw, u: Unit) -> None:
    color = COLORS[MarkerKind.FUEL]
    draw.rounded_rectangle(_box(u, -0.8, -0.85, 0.25, 0.85), radius=_width(u, 0.12), fill=PICTOGRAM)
    draw.rectangle(_box(u, -0.62, -0.65, 0.07, -0.2), fill=color)
    draw.rectangle(_box(u, -0.95, 0.75, 0.4, 0.95), fill=PICTOGRAM)
    hose = [u(0.25, -0.45), u(0.6, -0.45), u(0.75, -0.25), u(0.75, 0.4), u(0.55, 0.55), u(0.45, 0.35)]
    draw.line(hose, fill=PICTOGRAM, width=_width(u, 0.16), joint="curve")
    draw.line([u(0.62, -0.45), u(0.62, -0.8)], fill=PICTOGRAM, width=_width(u, 0.16))


def _gas_bottle(draw: Draw, u: Unit) -> None:
    color = COLORS[MarkerKind.GAS]
    draw.rounded_rectangle(_box(u, -0.55, -0.45, 0.55, 0.95), radius=_width(u, 0.4), fill=PICTOGRAM)
    draw.rectangle(_box(u, -0.18, -0.8, 0.18, -0.4), fill=PICTOGRAM)
    draw.rounded_rectangle(_box(u, -0.42, -0.98, 0.42, -0.74), radius=_width(u, 0.1), fill=PICTOGRAM)
    draw.rectangle(_box(u, -0.25, -0.86, 0.25, -0.82), fill=color)
    draw.line([u(-0.55, 0.2), u(0.55, 0.2)], fill=color, width=_width(u, 0.08))


def _motorhome(draw: Draw, u: Unit) -> None:
    color = COLORS[MarkerKind.PITCH]
    body = [u(-0.95, 0.55), u(-0.95, -0.55), u(0.35, -0.55), u(0.35, -0.75), u(0.6, -0.75), u(0.6, -0.1)]
    body += [u(0.95, 0.2), u(0.95, 0.55)]
    draw.polygon(body, fill=PICTOGRAM)
    draw.rectangle(_box(u, -0.75, -0.35, -0.35, -0.05), fill=color)
    draw.rectangle(_box(u, -0.2, -0.35, 0.2, -0.05), fill=color)
    draw.polygon([u(0.62, -0.05), u(0.62, 0.15), u(0.85, 0.2)], fill=color)
    for x in (-0.55, 0.55):
        draw.ellipse(_box(u, x - 0.27, 0.35, x + 0.27, 0.89), fill=PICTOGRAM)
        draw.ellipse(_box(u, x - 0.11, 0.51, x + 0.11, 0.73), fill=color)


def _ship(draw: Draw, u: Unit) -> None:
    color = COLORS[MarkerKind.FERRY]
    draw.polygon([u(-1.0, 0.15), u(1.0, 0.15), u(0.65, 0.7), u(-0.75, 0.7)], fill=PICTOGRAM)
    draw.rectangle(_box(u, -0.55, -0.35, 0.45, 0.15), fill=PICTOGRAM)
    draw.rectangle(_box(u, -0.15, -0.8, 0.15, -0.35), fill=PICTOGRAM)
    for x in (-0.4, -0.05, 0.3):
        draw.rectangle(_box(u, x, -0.22, x + 0.18, -0.04), fill=color)
    waves = [u(-0.9 + 0.3 * i, 0.9 + (0.08 if i % 2 else -0.04)) for i in range(7)]
    draw.line(waves, fill=PICTOGRAM, width=_width(u, 0.12), joint="curve")


def _flag(draw: Draw, u: Unit) -> None:
    draw.line([u(-0.55, -0.9), u(-0.55, 0.95)], fill=PICTOGRAM, width=_width(u, 0.18))
    draw.polygon([u(-0.5, -0.9), u(0.8, -0.5), u(-0.5, -0.1)], fill=PICTOGRAM)


def _chequered_flag(draw: Draw, u: Unit) -> None:
    color = COLORS[MarkerKind.END]
    draw.line([u(-0.7, -0.9), u(-0.7, 0.95)], fill=PICTOGRAM, width=_width(u, 0.18))
    left, top, cell = -0.62, -0.9, 0.36
    draw.rectangle(_box(u, left, top, left + 4 * cell, top + 3 * cell), fill=PICTOGRAM)
    for row in range(3):
        for col in range(4):
            if (row + col) % 2:
                x, y = left + col * cell, top + row * cell
                draw.rectangle(_box(u, x, y, x + cell, y + cell), fill=color)


_PICTOGRAMS: dict[MarkerKind, Callable[[Draw, Unit], None]] = {
    MarkerKind.START: _flag,
    MarkerKind.END: _chequered_flag,
    MarkerKind.PITCH: _motorhome,
    MarkerKind.STOP: _pause,
    MarkerKind.FUEL: _fuel_pump,
    MarkerKind.GAS: _gas_bottle,
    MarkerKind.FERRY: _ship,
}
