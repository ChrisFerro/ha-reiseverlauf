"""
Points and stops recorded during one trip, with running distance and driving time.

The log has no Home Assistant dependencies. The coordinator appends sensor
values while a trip runs or may still be merged, persists `as_dict()` in a
`Store`, and hands `export_inputs()` to the export once the trip ends.
"""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from itertools import pairwise
from typing import Any

from custom_components.reiseverlauftracker.export.model import StepSeries, Stop, TrackPoint
from custom_components.reiseverlauftracker.export.track import COALESCE_WINDOW, decode_speed
from custom_components.reiseverlauftracker.utils.geo import Position, distance_m

LOG_VERSION = 2


@dataclass(frozen=True, slots=True)
class RunningStatsSettings:
    """Thresholds of the live statistics; the export recomputes them exactly."""

    max_accuracy_m: float = 50.0
    standstill_kmh: float = 3.0
    max_gap: timedelta = timedelta(minutes=5)
    min_movement_m: float = 100.0
    elevation_hysteresis_m: float = 5.0


@dataclass(frozen=True, slots=True)
class TrackCounters:
    """Distance, ascent and descent counters of the logbook at one point in time."""

    distance_m: float
    ascent_m: float = 0.0
    descent_m: float = 0.0

    def __add__(self, other: TrackCounters) -> TrackCounters:
        """Return both counters added up."""
        return TrackCounters(
            self.distance_m + other.distance_m, self.ascent_m + other.ascent_m, self.descent_m + other.descent_m
        )

    def __sub__(self, other: TrackCounters) -> TrackCounters:
        """Return the difference of both counters."""
        return TrackCounters(
            self.distance_m - other.distance_m, self.ascent_m - other.ascent_m, self.descent_m - other.descent_m
        )

    def as_dict(self) -> dict[str, float]:
        """Return the counters as a JSON-serialisable dict."""
        return {"distance_m": self.distance_m, "ascent_m": self.ascent_m, "descent_m": self.descent_m}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrackCounters:
        """Rebuild the counters from `as_dict()` output."""
        return cls(data["distance_m"], data.get("ascent_m", 0.0), data.get("descent_m", 0.0))


class FerryMark(StrEnum):
    """Whether a stop was a ferry crossing (docs/features/feat-12-kartensymbole.md 6.1); unchecked is None."""

    AUTO = "auto"
    """Detected: the vehicle moved on water during the stop."""
    HAND = "hand"
    """Marked by hand."""
    NONE = "kein"
    """Mark removed by hand; detection does not set it again."""


@dataclass(frozen=True, slots=True)
class TripStop:
    """
    D+ was off during the trip; open while `end` is None.

    Later logbook data (odometer, tank levels) belongs on this record.
    """

    start: datetime
    lat: float | None = None
    lon: float | None = None
    end: datetime | None = None
    place: str | None = None
    ferry: FerryMark | None = None

    @property
    def is_ferry(self) -> bool:
        """Return whether the stop was a ferry crossing, detected or marked by hand."""
        return self.ferry in (FerryMark.AUTO, FerryMark.HAND)

    def duration(self, now: datetime) -> timedelta:
        """Return how long the stop lasted, or lasts so far."""
        return (self.end or now) - self.start

    def as_dict(self) -> dict[str, Any]:
        """Return the stop as a JSON-serialisable dict."""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
            "lat": self.lat,
            "lon": self.lon,
            "place": self.place,
            "ferry": self.ferry.value if self.ferry else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TripStop:
        """Rebuild a stop from `as_dict()` output."""
        return cls(
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]) if data.get("end") else None,
            lat=data.get("lat"),
            lon=data.get("lon"),
            place=data.get("place"),
            ferry=FerryMark(data["ferry"]) if data.get("ferry") in set(FerryMark) else None,
        )


@dataclass(frozen=True, slots=True)
class _Segment:
    """What the step to the last usable position added to the running statistics."""

    metres: float = 0.0
    moving_metres: float = 0.0
    driving: timedelta = timedelta()


class TripLog:
    """Positions, speed, altitude and stops of one trip."""

    def __init__(self, start: datetime, settings: RunningStatsSettings) -> None:
        """Create an empty log for the trip that started at `start`."""
        self.start = start
        self.settings = settings
        self.positions: list[TrackPoint] = []
        self.speed: list[tuple[datetime, float]] = []
        self.altitude: list[tuple[datetime, float]] = []
        self.distance_m = 0.0
        self.moving_distance_m = 0.0
        self.driving_time = timedelta()
        self.ascent_m = 0.0
        self.descent_m = 0.0
        self._ascent_reference: float | None = None
        self.start_place: str | None = None
        self.stops: list[TripStop] = []
        self.counter_start: TrackCounters | None = None
        self._last_usable: TrackPoint | None = None
        self._previous_usable: TrackPoint | None = None
        self._last_segment = _Segment()
        self._group_start: datetime | None = None

    @property
    def distance_km(self) -> float:
        """Return the distance driven so far in kilometres."""
        return self.distance_m / 1000

    @property
    def average_moving_kmh(self) -> float | None:
        """Return the average speed while moving, or None before the vehicle moved."""
        seconds = self.driving_time.total_seconds()
        return self.moving_distance_m / seconds * 3.6 if seconds > 0 else None

    @property
    def open_stop(self) -> TripStop | None:
        """Return the stop that has not ended yet."""
        return self.stops[-1] if self.stops and self.stops[-1].end is None else None

    def begin_stop(self, at: datetime) -> None:
        """
        Open a stop at the last known position; an already open stop is kept.

        If the vehicle stayed within `min_movement_m` of the previous stop since it
        ended, that stop continues instead: refuelling and then moving to a parking
        space is one stop, not several short ones.
        """
        if self.open_stop is not None:
            return
        if self.stops and self._stayed_at(self.stops[-1]):
            self.stops[-1] = replace(self.stops[-1], end=None)
            return
        position = self.last_position()
        self.stops.append(
            TripStop(start=at, lat=position.lat if position else None, lon=position.lon if position else None)
        )

    def end_stop(self, at: datetime, min_duration: timedelta) -> TripStop | None:
        """
        Close the open stop.

        A stop shorter than `min_duration` stays in the log, so that it can still
        continue, but it does not count until it reaches the minimum.

        Returns:
            The closed stop if it lasted `min_duration`, otherwise None.

        """
        stop = self.open_stop
        if stop is None:
            return None
        closed = replace(stop, end=at)
        self.stops[-1] = closed
        return closed if closed.duration(at) >= min_duration else None

    def _stayed_at(self, stop: TripStop) -> bool:
        """Return whether every position since `stop` ended lies within the minimum movement of it."""
        if stop.end is None or stop.lat is None or stop.lon is None:
            return False
        where = Position(stop.lat, stop.lon)
        return all(
            distance_m(where, p.position) <= self.settings.min_movement_m
            for p in self.positions
            if p.time >= stop.end and (p.accuracy is None or p.accuracy <= self.settings.max_accuracy_m)
        )

    def set_stop_place(self, start: datetime, place: str | None) -> None:
        """Store the place name of the stop that began at `start`."""
        self.stops = [replace(s, place=place) if s.start == start else s for s in self.stops]

    def set_ferry(self, start: datetime, mark: FerryMark | None) -> TripStop | None:
        """
        Mark the stop that began at `start` as ferry crossing, or not, and count distance and climb anew.

        Returns:
            The changed stop, or None if the log has no such stop.

        """
        stop = next((s for s in self.stops if s.start == start), None)
        if stop is None:
            return None
        changed = replace(stop, ferry=mark)
        self.stops = [changed if s.start == start else s for s in self.stops]
        self._recount()
        return changed

    def ferry_probe(self, stop: TripStop) -> Position | None:
        """
        Return the position halfway along the way the vehicle moved during `stop`, or None if it stayed.

        Only there is it worth asking whether the vehicle was on water (6.2).
        """
        if stop.end is None:
            return None
        points = [
            p
            for p in self.positions
            if stop.start <= p.time <= stop.end and (p.accuracy is None or p.accuracy <= self.settings.max_accuracy_m)
        ]
        if len(points) < 2 or max(distance_m(points[0].position, p.position) for p in points) < (
            self.settings.min_movement_m
        ):
            return None
        steps = [distance_m(a.position, b.position) for a, b in pairwise(points)]
        half, walked = sum(steps) / 2, 0.0
        for point, step in zip(points[1:], steps, strict=True):
            walked += step
            if walked >= half:
                return point.position
        return points[-1].position

    def _ferry_spans(self) -> list[tuple[datetime, datetime]]:
        return [(s.start, s.end) for s in self.stops if s.is_ferry and s.end is not None]

    def _recount(self) -> None:
        """Count distance, driving time and climb again from the recorded data, e.g. after a ferry was marked."""
        positions = self.positions
        self.positions, self.distance_m, self.moving_distance_m, self.driving_time = [], 0.0, 0.0, timedelta()
        self._last_usable = self._previous_usable = self._group_start = None
        self._last_segment = _Segment()
        for point in positions:
            self.add_position(point.time, point.lat, point.lon, point.accuracy)
        self._set_altitude(self.altitude)

    def confirmed_stops(self, now: datetime, min_duration: timedelta) -> list[TripStop]:
        """Return the stops, open or closed, that last `min_duration`."""
        return [s for s in self.stops if s.duration(now) >= min_duration]

    def export_stops(self, end: datetime, min_duration: timedelta) -> tuple[Stop, ...]:
        """Return the closed stops before `end` that lasted `min_duration`; the open one is the arrival."""
        return tuple(
            Stop(start=s.start, end=s.end, place=s.place, lat=s.lat, lon=s.lon, ferry=s.is_ferry)
            for s in self.stops
            if s.end and s.end <= end and s.duration(end) >= min_duration
        )

    def add_position(self, time: datetime, lat: float, lon: float, accuracy: float | None) -> None:
        """
        Append a position and update distance and driving time.

        A position within `COALESCE_WINDOW` of the first one of its group replaces
        the last position: a tracker fed by separate latitude and longitude sensors
        reports every fix twice, and the half-updated position zigzags the track.
        """
        if self.positions and self._group_start is not None and time - self._group_start < COALESCE_WINDOW:
            if self.positions.pop() is self._last_usable:
                self._undo_last_segment()
        else:
            self._group_start = time
        point = TrackPoint(time=time, lat=lat, lon=lon, accuracy=accuracy)
        self.positions.append(point)
        if accuracy is not None and accuracy > self.settings.max_accuracy_m:
            return
        previous, self._previous_usable, self._last_usable = self._last_usable, self._last_usable, point
        self._last_segment = _Segment()
        if previous is None:
            return
        seconds = (time - previous.time).total_seconds()
        if seconds <= 0:
            return
        if any(previous.time < end and time > start for start, end in self._ferry_spans()):
            return  # On board: the crossing is not driven (5.10).
        metres = distance_m(previous.position, point.position)
        segment = _Segment(metres=metres)
        if seconds <= self.settings.max_gap.total_seconds() and metres / seconds * 3.6 >= self.settings.standstill_kmh:
            segment = _Segment(metres=metres, moving_metres=metres, driving=timedelta(seconds=seconds))
        self.distance_m += segment.metres
        self.moving_distance_m += segment.moving_metres
        self.driving_time += segment.driving
        self._last_segment = segment

    def _undo_last_segment(self) -> None:
        self.distance_m -= self._last_segment.metres
        self.moving_distance_m -= self._last_segment.moving_metres
        self.driving_time -= self._last_segment.driving
        self._last_usable = self._previous_usable
        self._last_segment = _Segment()

    def add_speed(self, time: datetime, value: float) -> None:
        """Append a raw speed reading; old float-bit values are decoded on export."""
        self.speed.append((time, value))

    def add_altitude(self, time: datetime, value: float) -> None:
        """Append an altitude reading in metres and count ascent and descent like the export does."""
        self.altitude.append((time, value))
        if not any(start <= time <= end for start, end in self._ferry_spans()):
            self._count_elevation(value)

    def _count_elevation(self, value: float) -> None:
        """Count changes of at least the hysteresis, like `elevation_change()`, so GPS noise adds nothing."""
        reference = self._ascent_reference
        if reference is None or abs(value - reference) >= self.settings.elevation_hysteresis_m:
            if reference is not None and value > reference:
                self.ascent_m += value - reference
            elif reference is not None:
                self.descent_m += reference - value
            self._ascent_reference = value

    def _set_altitude(self, altitude: list[tuple[datetime, float]]) -> None:
        self.altitude = []
        self.ascent_m, self.descent_m, self._ascent_reference = 0.0, 0.0, None
        for time, value in altitude:
            self.add_altitude(time, value)

    @property
    def counters(self) -> TrackCounters:
        """Return distance, ascent and descent of the trip so far."""
        return TrackCounters(self.distance_m, self.ascent_m, self.descent_m)

    def counters_at(self, time: datetime) -> TrackCounters | None:
        """
        Return the logbook counters at `time`: the counters at the trip start plus the track up to then.

        The track is replayed with the same filters as the running statistics.

        Returns:
            The counters, or None for a log that does not know its start counters.

        """
        if self.counter_start is None:
            return None
        replay = TripLog(self.start, self.settings)
        replay.stops = list(self.stops)
        for point in self.positions:
            if point.time > time:
                break
            replay.add_position(point.time, point.lat, point.lon, point.accuracy)
        replay._set_altitude([(t, v) for t, v in self.altitude if t <= time])
        return self.counter_start + replay.counters

    def position_at(self, time: datetime) -> Position | None:
        """Return the last usable position at or before `time`, else the first usable one."""
        usable = [p for p in self.positions if p.accuracy is None or p.accuracy <= self.settings.max_accuracy_m]
        before = [p for p in usable if p.time <= time]
        point = before[-1] if before else (usable[0] if usable else None)
        return point.position if point else None

    def last_position(self) -> Position | None:
        """Return the most recent position, usable or not."""
        return self.positions[-1].position if self.positions else None

    def export_inputs(self) -> tuple[list[TrackPoint], StepSeries | None, StepSeries | None]:
        """Return positions, speed and altitude in the shape `export_trip()` takes."""
        speed = [(t, kmh) for t, v in self.speed if (kmh := decode_speed(v)) is not None]
        return (
            list(self.positions),
            StepSeries(speed) if speed else None,
            StepSeries(self.altitude) if self.altitude else None,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the log as a compact JSON-serialisable dict; times are Unix seconds."""
        return {
            "version": LOG_VERSION,
            "start": self.start.isoformat(),
            "positions": [[p.time.timestamp(), p.lat, p.lon, p.accuracy] for p in self.positions],
            "speed": [[t.timestamp(), v] for t, v in self.speed],
            "altitude": [[t.timestamp(), v] for t, v in self.altitude],
            "start_place": self.start_place,
            "stops": [stop.as_dict() for stop in self.stops],
            "counter_start": self.counter_start.as_dict() if self.counter_start else None,
        }

    @classmethod
    def from_export_inputs(
        cls,
        start: datetime,
        data: tuple[list[TrackPoint], StepSeries | None, StepSeries | None],
        settings: RunningStatsSettings,
    ) -> TripLog:
        """Build a log from history data, so a manual export stores its points like a trip does."""
        positions, speed, altitude = data
        log = cls(start, settings)
        for point in sorted(positions, key=lambda p: p.time):
            log.add_position(point.time, point.lat, point.lon, point.accuracy)
        log.speed = list(zip(speed.times, speed.values, strict=True)) if speed else []
        log._set_altitude(list(zip(altitude.times, altitude.values, strict=True)) if altitude else [])
        return log

    @classmethod
    def from_dict(cls, data: dict[str, Any], settings: RunningStatsSettings) -> TripLog:
        """Rebuild a log, including its running statistics, from `as_dict()` output."""
        log = cls(datetime.fromisoformat(data["start"]), settings)
        # Stops first: a ferry crossing among them is not counted as driven.
        log.stops = [TripStop.from_dict(stop) for stop in data.get("stops", [])]
        for ts, lat, lon, accuracy in data["positions"]:
            log.add_position(_from_ts(ts), lat, lon, accuracy)
        log.speed = [(_from_ts(ts), v) for ts, v in data["speed"]]
        log._set_altitude([(_from_ts(ts), v) for ts, v in data["altitude"]])
        log.start_place = data.get("start_place")
        counter_start = data.get("counter_start")
        log.counter_start = TrackCounters.from_dict(counter_start) if counter_start else None
        return log


def _from_ts(value: float) -> datetime:
    return datetime.fromtimestamp(value, UTC)
