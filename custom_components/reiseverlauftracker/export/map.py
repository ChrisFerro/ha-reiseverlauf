"""Route map on OpenStreetMap tiles, rendered with staticmap."""

from collections.abc import Callable, Sequence
import io
import logging
import threading
from typing import Any

from PIL import Image
import requests
from staticmap import CircleMarker, Line, StaticMap

from .model import TrackPoint

_LOGGER = logging.getLogger(__name__)

TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TILE_SIZE = 256
TILE_TIMEOUT_S = 15
TILE_ATTEMPTS = 2
HTTP_OK = 200

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


def render_map(
    points: Sequence[TrackPoint],
    size: tuple[int, int],
    line_width: int,
    fetch_tile: TileFetcher,
) -> Image.Image | None:
    """Draw the route with start and end markers; None if the map cannot be rendered at all."""
    return render_route_map([points], size, line_width, fetch_tile)


def render_route_map(
    segments: Sequence[Sequence[TrackPoint]],
    size: tuple[int, int],
    line_width: int,
    fetch_tile: TileFetcher,
    places: Sequence[tuple[float, float]] = (),
) -> Image.Image | None:
    """
    Draw several routes, each as its own line, with markers at the very start and end.

    `places` (latitude, longitude) get small markers, e.g. the night places of a tour.
    Returns None if the map cannot be rendered at all.
    """
    lines = [[(p.lon, p.lat) for p in points] for points in segments if len(points) >= 2]
    if not lines:
        return None
    static_map = _TolerantStaticMap(size[0], size[1], fetch_tile, padding_x=60, padding_y=60)
    for coords in lines:
        static_map.add_line(Line(coords, "#ffffff", line_width + 4))
    for coords in lines:
        static_map.add_line(Line(coords, "#d62828", line_width))
    marker = round(line_width * 22 / 6)
    for lat, lon in places:
        static_map.add_marker(CircleMarker((lon, lat), "#ffffff", round(marker * 0.8)))
        static_map.add_marker(CircleMarker((lon, lat), "#e9a23b", round(marker * 0.55)))
    static_map.add_marker(CircleMarker(lines[0][0], "#2a9d8f", marker))
    static_map.add_marker(CircleMarker(lines[-1][-1], "#1d3557", marker))
    try:
        image = static_map.render()
    except (OSError, ValueError, RuntimeError) as err:
        _LOGGER.warning("Map could not be rendered: %s", err)
        return None
    if static_map.missing_tiles:
        _LOGGER.warning("Map rendered with %d missing tiles", static_map.missing_tiles)
    return image
