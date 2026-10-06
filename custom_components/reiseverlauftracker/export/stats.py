"""Trip statistics and their text form."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from itertools import pairwise

from custom_components.reiseverlauftracker.utils.geo import distance_m

from .model import ExportOptions, StepSeries, TrackPoint
from .texts import Texts, format_duration, format_number, format_period


@dataclass(frozen=True, slots=True)
class TripStats:
    """Key figures of one trip."""

    departure: datetime
    arrival: datetime
    distance_km: float
    moving_time: timedelta
    max_speed_kmh: float | None
    avg_moving_speed_kmh: float | None
    altitude_min_m: float | None
    altitude_max_m: float | None
    ascent_m: float | None
    descent_m: float | None


def distance_km(points: Sequence[TrackPoint]) -> float:
    """Return the length of the track in kilometres."""
    return sum(distance_m(a.position, b.position) for a, b in pairwise(points)) / 1000


def moving_time(points: Sequence[TrackPoint], standstill_kmh: float, max_gap: timedelta) -> timedelta:
    """Sum the sections driven at least at `standstill_kmh`; gaps longer than `max_gap` do not count."""
    total = timedelta()
    for a, b in pairwise(points):
        seconds = (b.time - a.time).total_seconds()
        if 0 < seconds <= max_gap.total_seconds():
            kmh = distance_m(a.position, b.position) / seconds * 3.6
            if kmh >= standstill_kmh:
                total += timedelta(seconds=seconds)
    return total


def elevation_change(values: Sequence[float], hysteresis_m: float) -> tuple[float, float]:
    """Return (ascent, descent), counting only changes of at least `hysteresis_m` against GPS noise."""
    if not values:
        return 0.0, 0.0
    reference, ascent, descent = values[0], 0.0, 0.0
    for value in values[1:]:
        if value - reference >= hysteresis_m:
            ascent += value - reference
            reference = value
        elif reference - value >= hysteresis_m:
            descent += reference - value
            reference = value
    return ascent, descent


def compute_stats(points: Sequence[TrackPoint], speed: StepSeries | None, options: ExportOptions) -> TripStats:
    """Compute the key figures of a prepared track."""
    max_speed = avg_speed = None
    if speed:
        max_speed = max(speed.values)
        moving = [v for v in speed.values if v >= options.standstill_kmh]
        avg_speed = sum(moving) / len(moving) if moving else None
    altitudes = [p.altitude for p in points if p.altitude is not None]
    ascent = descent = None
    if altitudes:
        ascent, descent = elevation_change(altitudes, options.elevation_hysteresis_m)
    return TripStats(
        departure=points[0].time,
        arrival=points[-1].time,
        distance_km=distance_km(points),
        moving_time=moving_time(points, options.standstill_kmh, options.max_gap),
        max_speed_kmh=max_speed,
        avg_moving_speed_kmh=avg_speed,
        altitude_min_m=min(altitudes) if altitudes else None,
        altitude_max_m=max(altitudes) if altitudes else None,
        ascent_m=ascent,
        descent_m=descent,
    )


def stats_rows(stats: TripStats, texts: Texts, tz: tzinfo) -> list[tuple[str, str]]:
    """Return (label, value) rows for the text file and the composite header; the period comes first."""
    rows = [
        (texts.period, format_period(texts, stats.departure, stats.arrival, tz)),
        (texts.distance, f"{format_number(texts, stats.distance_km, 1)} km"),
        (texts.moving_time, format_duration(stats.moving_time)),
    ]
    if stats.max_speed_kmh is not None:
        rows.append((texts.max_speed, f"{format_number(texts, stats.max_speed_kmh)} km/h"))
    if stats.avg_moving_speed_kmh is not None:
        rows.append((texts.avg_moving_speed, f"{format_number(texts, stats.avg_moving_speed_kmh)} km/h"))
    if stats.altitude_min_m is not None and stats.altitude_max_m is not None:
        rows.append(
            (
                texts.altitude_range,
                f"{format_number(texts, stats.altitude_min_m)} / {format_number(texts, stats.altitude_max_m)} m",
            )
        )
    if stats.ascent_m is not None and stats.descent_m is not None:
        rows.append(
            (
                texts.elevation_gain,
                f"+{format_number(texts, stats.ascent_m)} / -{format_number(texts, stats.descent_m)} m",
            )
        )
    return rows


def stats_text(title: str, rows: Sequence[tuple[str, str]]) -> str:
    """Return the statistics as plain text with an underlined title."""
    lines = [title, "=" * len(title)]
    lines += [f"{label + ':':<17}{value}" for label, value in rows]
    return "\n".join(lines) + "\n"
