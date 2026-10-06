"""Geographic helpers shared by trip detection and export."""

import math
from typing import NamedTuple

EARTH_RADIUS_M = 6371000.0


class Position(NamedTuple):
    """A WGS84 coordinate in decimal degrees."""

    lat: float
    lon: float


def distance_m(a: Position, b: Position) -> float:
    """Return the great-circle distance between two positions in metres."""
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp = p2 - p1
    dl = math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))
