"""
Positions of a trip at which its countries are looked up (docs/features/feat-09-nachtraege.md 6.3).

The track is sampled at its start, every `SAMPLE_DISTANCE_M` and at its end;
the stops are added, so a short detour across a border with a halt counts too.
Points close to the one before are left out.
"""

from collections.abc import Iterable

from custom_components.reiseverlauftracker.utils.geo import Position, distance_m

from .trip_log import TripLog

SAMPLE_DISTANCE_M = 20_000.0
# A point this close to the one before adds no country, e.g. the arrival stop at the end of the track.
MIN_SPACING_M = 1_000.0


def country_sample_points(log: TripLog, every_m: float = SAMPLE_DISTANCE_M) -> list[Position]:
    """Return the positions to look up, in time order, from usable track points and the stops."""
    usable = [p for p in log.positions if p.accuracy is None or p.accuracy <= log.settings.max_accuracy_m]
    timed: list[tuple[float, Position]] = []
    since = 0.0
    previous: Position | None = None
    for index, point in enumerate(usable):
        position = Position(point.lat, point.lon)
        if previous is not None:
            since += distance_m(previous, position)
        if previous is None or since >= every_m or index == len(usable) - 1:
            timed.append((point.time.timestamp(), position))
            since = 0.0
        previous = position
    timed.extend(
        (stop.start.timestamp(), Position(stop.lat, stop.lon))
        for stop in log.stops
        if stop.lat is not None and stop.lon is not None
    )
    timed.sort(key=lambda item: item[0])
    points: list[Position] = []
    for _, position in timed:
        if not points or distance_m(points[-1], position) >= MIN_SPACING_M:
            points.append(position)
    return points


def ordered_countries(codes: Iterable[str | None]) -> tuple[str, ...]:
    """Return the known codes once each, in the order they first appear."""
    return tuple(dict.fromkeys(code for code in codes if code))
