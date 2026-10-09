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
from custom_components.reiseverlauftracker.export.track import decode_speed
from custom_components.reiseverlauftracker.utils.geo import Position, distance_m

LOG_VERSION = 2


@dataclass(frozen=True, slots=True)
class RunningStatsSettings:
    """Thresholds of the live statistics; the export recomputes them exactly."""

    max_accuracy_m: float = 50.0
    standstill_kmh: float = 3.0
    max_gap: timedelta = timedelta(minutes=5)


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
        self.start_place: str | None = None
        self.stops: list[TripStop] = []
        self._last_usable: TrackPoint | None = None

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
        """Open a stop at the last known position; an already open stop is kept."""
        if self.open_stop is not None:
            return
        position = self.last_position()
        self.stops.append(
            TripStop(start=at, lat=position.lat if position else None, lon=position.lon if position else None)
        )

    def end_stop(self, at: datetime, min_duration: timedelta) -> TripStop | None:
        """
        Close the open stop; one shorter than `min_duration` is dropped.

        Returns:
            The kept stop, or None if there was none or it was too short.

        """
        stop = self.open_stop
        if stop is None:
            return None
        self.stops.pop()
        if at - stop.start < min_duration:
            return None
        closed = replace(stop, end=at)
        self.stops.append(closed)
        return closed

    def set_stop_place(self, start: datetime, place: str | None) -> None:
        """Store the place name of the stop that began at `start`."""
        self.stops = [replace(s, place=place) if s.start == start else s for s in self.stops]

    def confirmed_stops(self, now: datetime, min_duration: timedelta) -> list[TripStop]:
        """Return closed stops and an open one that already lasts `min_duration`."""
        return [s for s in self.stops if s.end is not None or s.duration(now) >= min_duration]

    def export_stops(self, end: datetime) -> tuple[Stop, ...]:
        """Return the closed stops before `end`; the open one is the arrival, not a stop."""
        return tuple(Stop(start=s.start, end=s.end, place=s.place) for s in self.stops if s.end and s.end <= end)

    def add_position(self, time: datetime, lat: float, lon: float, accuracy: float | None) -> None:
        """Append a position and update distance and driving time."""
        point = TrackPoint(time=time, lat=lat, lon=lon, accuracy=accuracy)
        self.positions.append(point)
        if accuracy is not None and accuracy > self.settings.max_accuracy_m:
            return
        previous, self._last_usable = self._last_usable, point
        if previous is None:
            return
        seconds = (time - previous.time).total_seconds()
        if seconds <= 0:
            return
        metres = distance_m(previous.position, point.position)
        self.distance_m += metres
        if seconds <= self.settings.max_gap.total_seconds() and metres / seconds * 3.6 >= self.settings.standstill_kmh:
            self.driving_time += timedelta(seconds=seconds)
            self.moving_distance_m += metres

    def add_speed(self, time: datetime, value: float) -> None:
        """Append a raw speed reading; old float-bit values are decoded on export."""
        self.speed.append((time, value))

    def add_altitude(self, time: datetime, value: float) -> None:
        """Append an altitude reading in metres."""
        self.altitude.append((time, value))

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
        log.altitude = list(zip(altitude.times, altitude.values, strict=True)) if altitude else []
        return log

    @classmethod
    def from_dict(cls, data: dict[str, Any], settings: RunningStatsSettings) -> TripLog:
        """Rebuild a log, including its running statistics, from `as_dict()` output."""
        log = cls(datetime.fromisoformat(data["start"]), settings)
        for ts, lat, lon, accuracy in data["positions"]:
            log.add_position(_from_ts(ts), lat, lon, accuracy)
        log.speed = [(_from_ts(ts), v) for ts, v in data["speed"]]
        log.altitude = [(_from_ts(ts), v) for ts, v in data["altitude"]]
        log.start_place = data.get("start_place")
        log.stops = [TripStop.from_dict(stop) for stop in data.get("stops", [])]
        return log


def _from_ts(value: float) -> datetime:
    return datetime.fromtimestamp(value, UTC)
