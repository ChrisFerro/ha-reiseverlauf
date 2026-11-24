"""Trip statistics and their text form."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from itertools import pairwise

from custom_components.reiseverlauftracker.utils.geo import distance_m

from .ferry import SplitTrack, ferry_spans, on_ferry, split_track
from .model import ExportOptions, LogbookFigures, StepSeries, Stop, TrackPoint
from .texts import Texts, format_duration, format_money, format_number, format_period


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
    ferry_km: float = 0.0
    """Distance on ferries; not part of `distance_km` (docs/features/feat-12-kartensymbole.md 5.10)."""
    ferry_time: timedelta = timedelta()


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


def compute_stats(
    points: Sequence[TrackPoint], speed: StepSeries | None, options: ExportOptions, split: SplitTrack | None = None
) -> TripStats:
    """
    Compute the key figures of a prepared track.

    Ferry crossings among `options.stops` count neither as distance nor as driving
    time, climb or speed; they are summed up on their own. `split` is the track
    already split at them.
    """
    split = split or split_track(points, options.stops)
    spans = ferry_spans(options.stops)
    max_speed = avg_speed = None
    if speed:
        values = [v for t, v in zip(speed.times, speed.values, strict=True) if not on_ferry(t, spans)]
        max_speed = max(values) if values else None
        moving = [v for v in values if v >= options.standstill_kmh]
        avg_speed = sum(moving) / len(moving) if moving else None
    altitudes = [p.altitude for p in points if p.altitude is not None]
    ascent = descent = None
    if altitudes:
        changes = [
            elevation_change([p.altitude for p in part if p.altitude is not None], options.elevation_hysteresis_m)
            for part in split.land
        ]
        ascent, descent = sum(a for a, _ in changes), sum(d for _, d in changes)
    return TripStats(
        departure=points[0].time,
        arrival=points[-1].time,
        distance_km=sum(distance_km(part) for part in split.land),
        moving_time=sum(
            (moving_time(part, options.standstill_kmh, options.max_gap) for part in split.land), timedelta()
        ),
        max_speed_kmh=max_speed,
        avg_moving_speed_kmh=avg_speed,
        altitude_min_m=min(altitudes) if altitudes else None,
        altitude_max_m=max(altitudes) if altitudes else None,
        ascent_m=ascent,
        descent_m=descent,
        ferry_km=sum(distance_km(leg) for leg in split.ferries),
        ferry_time=split.ferry_time if split.ferries else timedelta(),
    )


def stats_rows(stats: TripStats, texts: Texts, tz: tzinfo) -> list[tuple[str, str]]:
    """Return (label, value) rows for the text file and the composite header; the period comes first."""
    rows = [
        (texts.period, format_period(texts, stats.departure, stats.arrival, tz)),
        (texts.distance, f"{format_number(texts, stats.distance_km, 1)} km"),
        (texts.moving_time, format_duration(stats.moving_time)),
    ]
    if stats.ferry_km > 0 or stats.ferry_time:
        rows.append((texts.ferry, f"{format_number(texts, stats.ferry_km, 1)} km, {format_duration(stats.ferry_time)}"))
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


def logbook_rows(
    figures: LogbookFigures | None, texts: Texts, currency: str, *, travel_details: bool = False
) -> list[tuple[str, str]]:
    """
    Return (label, value) rows of the logbook figures; empty rows are left out.

    "Costs" holds all costs; with `travel_details`, a row lists the travel costs by category
    (the statistics text has room for it, the composite header does not).
    """
    if figures is None:
        return []
    rows: list[tuple[str, str]] = []
    start, end = figures.odometer_start_km, figures.odometer_end_km
    if start is not None and end is not None:
        rows.append((texts.odometer, f"{format_number(texts, start)} – {format_number(texts, end)} km"))
    elif end is not None:
        rows.append((texts.odometer, f"{format_number(texts, end)} km"))
    refuelled = [
        f"{format_number(texts, litres, 1)} l {name}"
        for litres, name in ((figures.fuel_litres, texts.diesel), (figures.gas_litres, texts.gas))
        if litres > 0
    ]
    if refuelled:
        rows.append((texts.refuelled, " · ".join(refuelled)))
    if figures.cost > 0:
        rows.append((texts.costs, format_money(texts, figures.cost, currency)))
    travel = [
        f"{texts.cost_categories.get(category, category)} {format_money(texts, amount, currency)}"
        for category, amount in figures.travel_costs.items()
        if amount > 0
    ]
    if travel_details and travel:
        rows.append((texts.travel_costs, " · ".join(travel)))
    if figures.consumption_l_100km is not None:
        rows.append((texts.consumption, f"{format_number(texts, figures.consumption_l_100km, 1)} l/100 km"))
    return rows


def stats_text(title: str, rows: Sequence[tuple[str, str]], stop_lines: Sequence[str] = ()) -> str:
    """Return the statistics as plain text with an underlined title, followed by the stops if there are any."""
    lines = [title, "=" * len(title)]
    lines += [f"{label + ':':<17}{value}" for label, value in rows]
    lines += stop_lines
    return "\n".join(lines) + "\n"


def stop_lines(stops: Sequence[Stop], texts: Texts, tz: tzinfo) -> list[str]:
    """Return one line per stop with place, local time span and duration, under a heading."""
    if not stops:
        return []
    lines = ["", f"{texts.stops}:"]
    for stop in stops:
        a, b = stop.start.astimezone(tz), stop.end.astimezone(tz)
        span = f"{a:%H:%M}–{b:%H:%M}" if a.date() == b.date() else f"{a:%d.%m. %H:%M}–{b:%d.%m. %H:%M}"
        place = stop.place or texts.unknown_place
        if stop.ferry:
            place = f"{texts.ferry}: {place}"
        lines.append(f"  {place}  {span} ({format_duration(stop.duration)})")
    return lines
