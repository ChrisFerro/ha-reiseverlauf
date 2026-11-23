"""
Which symbols the map of a trip shows: its stops and the refills from the logbook.

Start and end are added by the export itself (docs/features/feat-12-kartensymbole.md 6.6).
"""

from bisect import bisect_left
from collections.abc import Iterable, Sequence
from datetime import datetime

from custom_components.reiseverlauftracker.export import MapMarker, MarkerKind, Stop, TrackPoint

from .logbook import LogbookEntry


def trip_markers(
    stops: Iterable[Stop], entries: Iterable[LogbookEntry], points: Sequence[TrackPoint]
) -> tuple[MapMarker, ...]:
    """
    Return the symbols of the stops and of the fuel and gas refills in `entries`.

    A stop or entry without a stored position takes the recorded position nearest
    to its time; without any, it gets no symbol.
    """
    ordered = sorted(points, key=lambda p: p.time)
    markers = [
        MapMarker(MarkerKind.STOP, *where)
        for stop in stops
        if (where := _position(stop.lat, stop.lon, stop.start, ordered)) is not None
    ]
    for entry in entries:
        kinds = [k for k, refill in ((MarkerKind.FUEL, entry.fuel), (MarkerKind.GAS, entry.gas)) if refill is not None]
        if kinds and (where := _position(entry.lat, entry.lon, entry.time, ordered)) is not None:
            markers += [MapMarker(kind, *where) for kind in kinds]
    return tuple(markers)


def _position(
    lat: float | None, lon: float | None, time: datetime, points: Sequence[TrackPoint]
) -> tuple[float, float] | None:
    if lat is not None and lon is not None:
        return lat, lon
    if not points:
        return None
    index = bisect_left([p.time for p in points], time)
    candidates = [points[i] for i in (index - 1, index) if 0 <= i < len(points)]
    nearest = min(candidates, key=lambda p: abs(p.time - time))
    return nearest.lat, nearest.lon
