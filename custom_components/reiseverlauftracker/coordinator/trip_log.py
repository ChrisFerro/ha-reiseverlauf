"""
Points recorded during one trip, with running distance and driving time.

The log has no Home Assistant dependencies. The coordinator appends sensor
values while a trip runs or may still be merged, persists `as_dict()` in a
`Store`, and hands `export_inputs()` to the export once the trip ends.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from custom_components.reiseverlauftracker.export.model import StepSeries, TrackPoint
from custom_components.reiseverlauftracker.export.track import decode_speed
from custom_components.reiseverlauftracker.utils.geo import Position, distance_m

LOG_VERSION = 1


@dataclass(frozen=True, slots=True)
class RunningStatsSettings:
    """Thresholds of the live statistics; the export recomputes them exactly."""

    max_accuracy_m: float = 50.0
    standstill_kmh: float = 3.0
    max_gap: timedelta = timedelta(minutes=5)


class TripLog:
    """Positions, speed and altitude of one trip."""

    def __init__(self, start: datetime, settings: RunningStatsSettings) -> None:
        """Create an empty log for the trip that started at `start`."""
        self.start = start
        self.settings = settings
        self.positions: list[TrackPoint] = []
        self.speed: list[tuple[datetime, float]] = []
        self.altitude: list[tuple[datetime, float]] = []
        self.distance_m = 0.0
        self.driving_time = timedelta()
        self._last_usable: TrackPoint | None = None

    @property
    def distance_km(self) -> float:
        """Return the distance driven so far in kilometres."""
        return self.distance_m / 1000

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
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], settings: RunningStatsSettings) -> TripLog:
        """Rebuild a log, including its running statistics, from `as_dict()` output."""
        log = cls(datetime.fromisoformat(data["start"]), settings)
        for ts, lat, lon, accuracy in data["positions"]:
            log.add_position(_from_ts(ts), lat, lon, accuracy)
        log.speed = [(_from_ts(ts), v) for ts, v in data["speed"]]
        log.altitude = [(_from_ts(ts), v) for ts, v in data["altitude"]]
        return log


def _from_ts(value: float) -> datetime:
    return datetime.fromtimestamp(value, UTC)
