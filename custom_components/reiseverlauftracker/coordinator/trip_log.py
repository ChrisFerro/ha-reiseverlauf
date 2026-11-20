"""
Points and stops recorded during one trip, with running distance and driving time.

The log has no Home Assistant dependencies. The coordinator appends sensor
values while a trip runs or may still be merged, persists `as_dict()` in a
`Store`, and hands `export_inputs()` to the export once the trip ends.
"""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
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
        self._ascent_reference: float | None = None
        self.start_place: str | None = None
        self.stops: list[TripStop] = []
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

    def confirmed_stops(self, now: datetime, min_duration: timedelta) -> list[TripStop]:
        """Return the stops, open or closed, that last `min_duration`."""
        return [s for s in self.stops if s.duration(now) >= min_duration]

    def export_stops(self, end: datetime, min_duration: timedelta) -> tuple[Stop, ...]:
        """Return the closed stops before `end` that lasted `min_duration`; the open one is the arrival."""
        return tuple(
            Stop(start=s.start, end=s.end, place=s.place)
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
        """Append an altitude reading in metres and count the ascent like the export does."""
        self.altitude.append((time, value))
        self._count_ascent(value)

    def _count_ascent(self, value: float) -> None:
        """Count climbs of at least the hysteresis, like `elevation_change()`, so GPS noise adds nothing."""
        reference = self._ascent_reference
        if reference is None or abs(value - reference) >= self.settings.elevation_hysteresis_m:
            if reference is not None and value > reference:
                self.ascent_m += value - reference
            self._ascent_reference = value

    def _set_altitude(self, altitude: list[tuple[datetime, float]]) -> None:
        self.altitude = []
        self.ascent_m, self._ascent_reference = 0.0, None
        for time, value in altitude:
            self.add_altitude(time, value)

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
        for ts, lat, lon, accuracy in data["positions"]:
            log.add_position(_from_ts(ts), lat, lon, accuracy)
        log.speed = [(_from_ts(ts), v) for ts, v in data["speed"]]
        log._set_altitude([(_from_ts(ts), v) for ts, v in data["altitude"]])
        log.start_place = data.get("start_place")
        log.stops = [TripStop.from_dict(stop) for stop in data.get("stops", [])]
        return log


def _from_ts(value: float) -> datetime:
    return datetime.fromtimestamp(value, UTC)
