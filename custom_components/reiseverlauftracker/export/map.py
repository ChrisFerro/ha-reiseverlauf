"""Route map on OpenStreetMap tiles, rendered with staticmap."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import io
from itertools import pairwise
import logging
import math
import threading
from typing import Any

from PIL import Image, ImageDraw
import requests
from staticmap import Line, StaticMap

from .model import FerryLeg, MapMarker, MapProjection, MarkerKind, TrackPoint
from .symbols import COLORS, draw_symbol, layout

_LOGGER = logging.getLogger(__name__)

TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TILE_SIZE = 256
TILE_TIMEOUT_S = 15
TILE_ATTEMPTS = 2
HTTP_OK = 200
ROUTE_COLOR = "#d62828"
OUTLINE_COLOR = "#ffffff"
FERRY_COLOR = COLORS[MarkerKind.FERRY]
SYMBOL_PER_LINE_WIDTH = 8
"""Symbol diameter in multiples of the route's line width."""
MAP_PADDING = 60

type TileFetcher = Callable[[str], bytes | None]


def _blank_tile() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def http_tile_fetcher(user_agent: str) -> TileFetcher:
    """Return a fetcher that downloads tiles with an identifying User-Agent, as the OSM tile policy requires."""

    def fetch(url: str) -> bytes | None:
        for _ in range(TILE_ATTEMPTS):
            try:
                response = requests.get(url, headers={"User-Agent": user_agent}, timeout=TILE_TIMEOUT_S)
            except requests.RequestException:
                continue
            if response.status_code == HTTP_OK:
                return response.content
        return None

    return fetch


class _TolerantStaticMap(StaticMap):
    """
    StaticMap that leaves a missing or broken tile blank.

    The base class retries failed tiles three times and then raises without
    shutting down its thread pool, so one bad tile would drop the whole map
    and leak four threads. `get` therefore never reports a failure.
    """

    def __init__(self, width: int, height: int, fetch_tile: TileFetcher, **kwargs: Any) -> None:
        super().__init__(width, height, url_template=TILE_URL, tile_size=TILE_SIZE, **kwargs)
        self._fetch_tile = fetch_tile
        self.missing_tiles = 0
        self._lock = threading.Lock()

    def get(self, url: str, **_kwargs: Any) -> tuple[int, bytes]:
        content = self._fetch_tile(url)
        if content is not None and _is_image(content):
            return HTTP_OK, content
        with self._lock:
            self.missing_tiles += 1
        return HTTP_OK, _blank_tile()


def _is_image(content: bytes) -> bool:
    try:
        with Image.open(io.BytesIO(content)) as tile:
            tile.verify()
    except OSError, SyntaxError, ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class BaseMap:
    """A map with tiles and routes but no symbols, and where its coordinates lie."""

    image: Image.Image
    projection: MapProjection
    missing_tiles: int = 0
    """Tiles that could not be loaded and stay blank."""


def symbol_diameter(line_width: int) -> int:
    """Return the diameter of the map symbols for a route of `line_width` pixels."""
    return max(line_width * SYMBOL_PER_LINE_WIDTH, 8)


def default_markers(
    segments: Sequence[Sequence[TrackPoint]], places: Sequence[tuple[float, float]] = ()
) -> list[MapMarker]:
    """Return start and end of the routes and a camp symbol at each of `places` (latitude, longitude)."""
    routes = [points for points in segments if len(points) >= 2]
    if not routes:
        return []
    first, last = routes[0][0], routes[-1][-1]
    return [
        *(MapMarker(MarkerKind.PITCH, lat, lon) for lat, lon in places),
        MapMarker(MarkerKind.START, first.lat, first.lon),
        MapMarker(MarkerKind.END, last.lat, last.lon),
    ]


def render_map(
    points: Sequence[TrackPoint],
    size: tuple[int, int],
    line_width: int,
    fetch_tile: TileFetcher,
) -> Image.Image | None:
    """Draw the route with start and end symbols; None if the map cannot be rendered at all."""
    return render_route_map([points], size, line_width, fetch_tile)


def render_route_map(
    segments: Sequence[Sequence[TrackPoint]],
    size: tuple[int, int],
    line_width: int,
    fetch_tile: TileFetcher,
    places: Sequence[tuple[float, float]] = (),
    markers: Sequence[MapMarker] | None = None,
    ferries: Sequence[FerryLeg] = (),
) -> Image.Image | None:
    """
    Draw several routes, each as its own line, with their symbols and ferry crossings.

    Without `markers`, the map shows start, end and a camp symbol at each of `places`
    (latitude, longitude), e.g. the night places of a tour.
    Returns None if the map cannot be rendered at all.
    """
    if markers is None:
        markers = default_markers(segments, places)
    base = render_base_map(segments, size, line_width, fetch_tile, markers, ferries)
    if base is None:
        return None
    image = draw_overlay(base.image, base.projection, segments, markers, ferries, line_width)
    base.image.close()
    return image


def render_base_map(
    segments: Sequence[Sequence[TrackPoint]],
    size: tuple[int, int],
    line_width: int,
    fetch_tile: TileFetcher,
    markers: Sequence[MapMarker] = (),
    ferries: Sequence[FerryLeg] = (),
) -> BaseMap | None:
    """
    Draw the tiles that frame routes, symbols and ferry crossings, without drawing any of them.

    Routes, crossings and symbols follow with `draw_overlay`, so a crossing marked
    later changes the route without new tiles (docs/features/feat-12-kartensymbole.md 6.5).
    Returns None if there is no route or the map cannot be rendered at all.
    """
    lines = [[(p.lon, p.lat) for p in points] for points in segments if len(points) >= 2]
    if not lines:
        return None
    padding = max(MAP_PADDING, symbol_diameter(line_width))
    static_map = _TolerantStaticMap(size[0], size[1], fetch_tile, padding_x=padding, padding_y=padding)
    extra = [(m.lon, m.lat) for m in markers] + [(lon, lat) for leg in ferries for lat, lon in leg.points]
    frame = [coord for coords in lines for coord in coords] + extra
    # Invisible: it only sets the frame.
    static_map.add_line(Line(frame, "#00000000", 1, simplify=False))
    try:
        image = static_map.render()
    except (OSError, ValueError, RuntimeError) as err:
        _LOGGER.warning("Map could not be rendered: %s", err)
        return None
    if static_map.missing_tiles:
        _LOGGER.warning("Map rendered with %d missing tiles", static_map.missing_tiles)
    projection = MapProjection(
        zoom=static_map.zoom,
        x_center=static_map.x_center,
        y_center=static_map.y_center,
        width=size[0],
        height=size[1],
        tile_size=TILE_SIZE,
    )
    return BaseMap(image, projection, static_map.missing_tiles)


def draw_overlay(
    base: Image.Image,
    projection: MapProjection,
    segments: Sequence[Sequence[TrackPoint]],
    markers: Sequence[MapMarker],
    ferries: Sequence[FerryLeg],
    line_width: int,
) -> Image.Image:
    """
    Return a copy of `base` with the routes, the ferry crossings dashed and the symbols on top (5.3, 5.4).

    Needs no tiles, so a stored base map can get new routes and symbols at any time (6.5).
    """
    image = base.convert("RGBA")
    if base.size != (projection.width, projection.height):
        _LOGGER.warning("Base map size %s does not match its projection; symbols may be misplaced", base.size)
    diameter = symbol_diameter(line_width)
    routes = [[projection.to_px(p.lat, p.lon) for p in points] for points in segments if len(points) >= 2]
    if routes:
        _draw_routes(image, routes, line_width)
    legs = [[projection.to_px(lat, lon) for lat, lon in leg.points] for leg in ferries if len(leg.points) >= 2]
    if legs:
        _draw_ferries(image, legs, line_width)
    placed = [(m.kind, projection.to_px(m.lat, m.lon)) for m in markers]
    placed += [(MarkerKind.FERRY, _halfway(leg)) for leg in legs]
    for kind, centre in layout(placed, diameter):
        draw_symbol(image, kind, centre, diameter)
    return image.convert("RGB")


def _draw_routes(image: Image.Image, routes: Sequence[Sequence[tuple[float, float]]], line_width: int) -> None:
    """Draw the routes in red with a white outline, anti-aliased by drawing at twice the size."""
    layer = Image.new("RGBA", (image.width * 2, image.height * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for color, width in ((OUTLINE_COLOR, line_width + 4), (ROUTE_COLOR, line_width)):
        for route in routes:
            points = [(x * 2, y * 2) for x, y in route]
            draw.line(points, fill=color, width=width * 2, joint="curve")
            for x, y in (points[0], points[-1]):
                draw.ellipse((x - width, y - width, x + width, y + width), fill=color)
    image.alpha_composite(layer.resize(image.size, Image.Resampling.LANCZOS))


def _draw_ferries(image: Image.Image, legs: Sequence[Sequence[tuple[float, float]]], line_width: int) -> None:
    """Draw each crossing dashed, with a white outline, anti-aliased by drawing at twice the size."""
    layer = Image.new("RGBA", (image.width * 2, image.height * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    dash, gap = line_width * 3, line_width * 2
    for color, width in ((OUTLINE_COLOR, line_width + 4), (FERRY_COLOR, line_width)):
        for leg in legs:
            for a, b in dashes(leg, dash, gap):
                start, end = (a[0] * 2, a[1] * 2), (b[0] * 2, b[1] * 2)
                draw.line([start, end], fill=color, width=width * 2)
                for x, y in (start, end):
                    draw.ellipse((x - width, y - width, x + width, y + width), fill=color)
    image.alpha_composite(layer.resize(image.size, Image.Resampling.LANCZOS))


type Px = tuple[float, float]


def dashes(points: Sequence[Px], dash: float, gap: float) -> list[tuple[Px, Px]]:
    """Split a polyline into dashes of length `dash` with `gap` between them."""
    pieces: list[tuple[Px, Px]] = []
    drawing, left = True, dash
    for a, b in pairwise(points):
        length = math.dist(a, b)
        done = 0.0
        while length - done > 1e-9:
            step = min(left, length - done)
            t0, t1 = done / length, (done + step) / length
            if drawing:
                pieces.append(
                    (
                        (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0),
                        (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1),
                    )
                )
            done += step
            left -= step
            if left <= 1e-9:
                drawing = not drawing
                left = dash if drawing else gap
    return pieces


def _halfway(points: Sequence[Px]) -> Px:
    """Return the point halfway along a polyline."""
    total = sum(math.dist(a, b) for a, b in pairwise(points))
    remaining = total / 2
    for a, b in pairwise(points):
        length = math.dist(a, b)
        if length >= remaining and length > 0:
            t = remaining / length
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        remaining -= length
    return points[-1]
