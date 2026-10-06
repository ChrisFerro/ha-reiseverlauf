"""Prepare recorded positions for export: filter, enrich, trim to the movement, thin out."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
import math
import struct

from custom_components.reiseverlauftracker.utils.geo import distance_m

from .model import ExportOptions, StepSeries, TrackPoint

RAW_FLOAT_BITS_THRESHOLD = 100000
MAX_PLAUSIBLE_KMH = 200.0


class NotEnoughPointsError(Exception):
    """Fewer than two usable positions in the requested period."""


class NoMovementError(Exception):
    """The vehicle never moved farther than the minimum movement."""


@dataclass(frozen=True, slots=True)
class PreparedTrack:
    """Positions trimmed to departure and arrival, with the matching speed windows."""

    points: list[TrackPoint]
    departure: datetime
    arrival: datetime
    speed: StepSeries | None
    chart_speed: StepSeries | None
    chart_start: datetime
    chart_end: datetime


def decode_speed(value: float | None) -> float | None:
    """
    Return a plausible speed in km/h, or None.

    The Teltonika speed register was once read as an integer, so old history
    holds the raw big-endian float32 bits (1118656744 is 86.67 km/h).
    """
    if value is None or math.isnan(value):
        return None
    kmh: float = value
    if kmh > RAW_FLOAT_BITS_THRESHOLD:
        try:
            kmh = struct.unpack(">f", struct.pack(">I", int(kmh)))[0]
        except struct.error, OverflowError, ValueError:
            return None
    if math.isnan(kmh) or not 0 <= kmh <= MAX_PLAUSIBLE_KMH:
        return None
    return kmh


def find_movement(points: Sequence[TrackPoint], min_movement_m: float) -> tuple[int, int] | None:
    """
    Return the indices of departure and arrival, or None without movement.

    Departure is the last point before the position first leaves the radius
    around the first point; arrival is the mirror image from the end.
    """
    first = points[0].position
    leave = next(
        (i for i, p in enumerate(points) if distance_m(first, p.position) >= min_movement_m),
        None,
    )
    if leave is None:
        return None
    last = points[-1].position
    enter = next(i for i in range(len(points) - 1, -1, -1) if distance_m(last, points[i].position) >= min_movement_m)
    return max(leave - 1, 0), min(enter + 1, len(points) - 1)


def thin_out(points: Sequence[TrackPoint], min_distance_m: float) -> list[TrackPoint]:
    """Drop points closer than `min_distance_m` to the last kept one; keep both ends."""
    if len(points) < 3:
        return list(points)
    kept = [points[0]]
    for point in points[1:-1]:
        if distance_m(kept[-1].position, point.position) >= min_distance_m:
            kept.append(point)
    kept.append(points[-1])
    return kept


def prepare_track(
    positions: Sequence[TrackPoint],
    speed: StepSeries | None,
    altitude: StepSeries | None,
    options: ExportOptions,
) -> PreparedTrack:
    """
    Turn raw positions and sensor histories into the track that is exported.

    Raises:
        NotEnoughPointsError: Fewer than two positions pass the accuracy filter.
        NoMovementError: The vehicle never left the minimum movement radius.

    """
    usable = sorted(
        (p for p in positions if p.accuracy is None or p.accuracy <= options.max_accuracy_m),
        key=lambda p: p.time,
    )
    if len(usable) < 2:
        raise NotEnoughPointsError
    enriched = [
        p.with_values(
            speed.value_at(p.time) if speed else None,
            altitude.value_at(p.time) if altitude else None,
        )
        for p in usable
    ]
    movement = find_movement(enriched, options.min_movement_m)
    if movement is None:
        raise NoMovementError
    trimmed = enriched[movement[0] : movement[1] + 1]
    departure, arrival = trimmed[0].time, trimmed[-1].time
    chart_start, chart_end = departure - options.margin, arrival + options.margin
    return PreparedTrack(
        points=thin_out(trimmed, options.min_point_distance_m),
        departure=departure,
        arrival=arrival,
        speed=speed.window(departure, arrival) if speed else None,
        chart_speed=speed.window(chart_start, chart_end) if speed else None,
        chart_start=chart_start,
        chart_end=chart_end,
    )
