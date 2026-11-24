"""
Resolve an earlier point in time for a late logbook entry (docs/features/feat-09-nachtraege.md 6.2).

A late entry needs the distance, ascent and descent counters at its time, so
that the odometer and fuel level are carried forward correctly. The module has
no Home Assistant dependencies: the coordinator lists the known trips and loads
the track of the trip that contains the time.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, tzinfo

from .logbook import Logbook, LogbookEntry, Occasion, RecordedStop
from .trip_log import TrackCounters, TripLog

# A stop this close to the time of a late entry from a service action is taken as its stop.
STOP_MATCH_TOLERANCE = timedelta(minutes=5)
# The selection lists this many of the newest stops, plus all stops of the trip chosen in the export selection.
RECENT_STOPS = 30
SHORT_STOP_WORDS = {"de": "kurz", "en": "short"}
FERRY_WORDS = {"de": "Fähre", "en": "ferry"}


@dataclass(frozen=True, slots=True)
class TripSpan:
    """A recorded trip: its period and the logbook counters when it started, if known."""

    start: datetime
    end: datetime | None = None
    counter_start: TrackCounters | None = None
    folder: str | None = None

    def contains(self, time: datetime) -> bool:
        """Return whether `time` lies within the trip; a running trip has no end yet."""
        return self.start <= time and (self.end is None or time <= self.end)


@dataclass(frozen=True, slots=True)
class LatePoint:
    """
    The point in time a late entry is made for.

    `estimated` means the counters were interpolated between entries, so the
    suggested odometer has to be confirmed.
    """

    time: datetime
    counters: TrackCounters
    estimated: bool = False
    trip_start: datetime | None = None
    stop_start: datetime | None = None
    lat: float | None = None
    lon: float | None = None
    place: str | None = None


def stop_point(stop: RecordedStop) -> LatePoint:
    """Return the point of a remembered stop, with the counters at its beginning."""
    return LatePoint(
        time=stop.start,
        counters=TrackCounters(stop.distance_counter_m, stop.ascent_counter_m or 0.0, stop.descent_counter_m or 0.0),
        trip_start=stop.trip_start,
        stop_start=stop.start,
        lat=stop.lat,
        lon=stop.lon,
        place=stop.place,
    )


def stop_label(stop: RecordedStop, tz: tzinfo, language: str, min_duration: timedelta, now: datetime) -> str:
    """Return how a stop appears in the selection, such as `14.11. 10:42 · Irschenberg · kurz` or `… · Fähre`."""
    parts = [f"{stop.start.astimezone(tz):%d.%m. %H:%M}"]
    if stop.place:
        parts.append(stop.place)
    words = language.split("-", maxsplit=1)[0]
    if stop.ferry:
        parts.append(FERRY_WORDS.get(words, FERRY_WORDS["en"]))
    elif stop.is_short(min_duration, now):
        parts.append(SHORT_STOP_WORDS.get(words, SHORT_STOP_WORDS["en"]))
    return " · ".join(parts)


def selectable_stops(logbook: Logbook, chosen_trip: datetime | None) -> list[RecordedStop]:
    """Return the newest stops and those of the chosen trip, newest first, each once."""
    stops = {s.start: s for s in logbook.recent_stops(RECENT_STOPS)}
    if chosen_trip is not None:
        stops.update({s.start: s for s in logbook.stops_of_trip(chosen_trip)})
    return sorted(stops.values(), key=lambda s: s.start, reverse=True)


def matching_stop(logbook: Logbook, time: datetime, now: datetime) -> RecordedStop | None:
    """Return the remembered stop that lasted until or began close to `time`, the closest one first."""
    candidates = [
        stop
        for stop in logbook.stops
        if stop.start - STOP_MATCH_TOLERANCE <= time <= (stop.end or now) + STOP_MATCH_TOLERANCE
    ]
    return min(candidates, key=lambda s: abs((s.start - time).total_seconds()), default=None)


def containing_trip(spans: list[TripSpan], time: datetime) -> TripSpan | None:
    """Return the trip that contains `time`, the latest one if trips overlap."""
    return max((s for s in spans if s.contains(time)), key=lambda s: s.start, default=None)


def resolve_time(
    time: datetime,
    logbook: Logbook,
    spans: list[TripSpan],
    track: TripLog | None = None,
    *,
    exclude: str | None = None,
) -> LatePoint:
    """
    Return the counters and position at `time`.

    In order:
    1. During a trip with a track: the counters at the trip start plus the track
       up to `time`. Without stored start counters, those of the trip-start entry.
    2. While parked: counters only change while driving, so they equal the start
       counters of the next trip, or the current counters if no trip followed.
    3. Otherwise interpolated by time between the entries before and after,
       marked as estimated.

    `track` is the track of the trip that contains `time`, if any. `exclude` is
    the id of an entry that is being moved; it is no neighbour for interpolating.
    """
    span = containing_trip(spans, time)
    if span is not None:
        start = span.counter_start or _trip_start_counters(logbook, span.start)
        if track is not None and start is not None:
            if track.counter_start is None:
                track = _with_start(track, start)
            counters = track.counters_at(time)
            position = track.position_at(time)
            if counters is not None:
                return LatePoint(
                    time=time,
                    counters=counters,
                    trip_start=span.start,
                    lat=position.lat if position else None,
                    lon=position.lon if position else None,
                )
        return replace(_interpolated(logbook, time, exclude), trip_start=span.start)
    later = sorted((s for s in spans if s.start > time), key=lambda s: s.start)
    if not later:
        return LatePoint(time=time, counters=_current(logbook))
    following = later[0].counter_start or _trip_start_counters(logbook, later[0].start)
    if following is not None:
        return LatePoint(time=time, counters=following)
    return _interpolated(logbook, time, exclude)


def entry_for(logbook: Logbook, point: LatePoint) -> LogbookEntry | None:
    """Return the entry already made for the point: the one of its stop, or a late entry at the same time."""
    for entry in logbook.entries:
        if point.stop_start is not None and entry.stop_start == point.stop_start:
            return entry
        if entry.time == point.time and entry.occasion is Occasion.LATE:
            return entry
    return None


def _with_start(track: TripLog, start: TrackCounters) -> TripLog:
    """Return a copy of the track's log with the given start counters; the original stays unchanged."""
    copy = TripLog(track.start, track.settings)
    copy.positions, copy.altitude = track.positions, track.altitude
    copy.counter_start = start
    return copy


def _trip_start_counters(logbook: Logbook, trip_start: datetime) -> TrackCounters | None:
    """Return the counters of the trip-start entry of a trip, for trips recorded before start counters existed."""
    for entry in logbook.entries:
        if entry.occasion is Occasion.TRIP_START and entry.trip_start == trip_start:
            return _counters(entry)
    return None


def _interpolated(logbook: Logbook, time: datetime, exclude: str | None = None) -> LatePoint:
    """Return counters interpolated by time between the entries before and after `time`, except `exclude`."""
    entries = [e for e in logbook.entries if e.id != exclude]
    before = next((e for e in reversed(entries) if e.time <= time), None)
    after = next((e for e in entries if e.time > time), None)
    if before is None or after is None:
        known = before or after
        counters = _counters(known) if known is not None else _current(logbook)
        return LatePoint(time=time, counters=counters, estimated=True)
    share = (time - before.time) / (after.time - before.time)
    low, high = _counters(before), _counters(after)
    return LatePoint(
        time=time,
        counters=TrackCounters(
            low.distance_m + (high.distance_m - low.distance_m) * share,
            low.ascent_m + (high.ascent_m - low.ascent_m) * share,
            low.descent_m + (high.descent_m - low.descent_m) * share,
        ),
        estimated=True,
    )


def _counters(entry: LogbookEntry) -> TrackCounters:
    return TrackCounters(entry.distance_counter_m, entry.ascent_counter_m or 0.0, entry.descent_counter_m or 0.0)


def _current(logbook: Logbook) -> TrackCounters:
    return TrackCounters(logbook.distance_counter_m, logbook.ascent_counter_m, logbook.descent_counter_m)
