"""Input data and options of the trip export."""

from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, tzinfo

from custom_components.reiseverlauftracker.utils.geo import Position


@dataclass(frozen=True, slots=True)
class TrackPoint:
    """One recorded vehicle position; speed in km/h, altitude in metres."""

    time: datetime
    lat: float
    lon: float
    accuracy: float | None = None
    speed: float | None = None
    altitude: float | None = None

    @property
    def position(self) -> Position:
        """Return the coordinate of the point."""
        return Position(self.lat, self.lon)

    def with_values(self, speed: float | None, altitude: float | None) -> TrackPoint:
        """Return a copy with speed and altitude filled in where missing."""
        return replace(
            self,
            speed=self.speed if self.speed is not None else speed,
            altitude=self.altitude if self.altitude is not None else altitude,
        )


class StepSeries:
    """A sensor history as a step function: each value holds until the next change."""

    def __init__(self, pairs: Iterable[tuple[datetime, float]]) -> None:
        """Create the series from (time, value) pairs in any order."""
        ordered = sorted(pairs, key=lambda pair: pair[0])
        self.times = [t for t, _ in ordered]
        self.values = [v for _, v in ordered]

    def __len__(self) -> int:
        """Return the number of recorded changes."""
        return len(self.times)

    def value_at(self, time: datetime) -> float | None:
        """Return the value valid at `time`, or None before the first change."""
        index = bisect_right(self.times, time) - 1
        return self.values[index] if index >= 0 else None

    def window(self, start: datetime, end: datetime) -> StepSeries | None:
        """Return the part between `start` and `end`, starting with the value valid at `start`."""
        pairs: list[tuple[datetime, float]] = []
        first = self.value_at(start)
        if first is not None:
            pairs.append((start, first))
        pairs += [(t, v) for t, v in zip(self.times, self.values, strict=True) if start < t <= end]
        return StepSeries(pairs) if pairs else None


@dataclass(frozen=True, slots=True)
class Stop:
    """A stop during the trip; listed in the statistics."""

    start: datetime
    end: datetime
    place: str | None = None

    @property
    def duration(self) -> timedelta:
        """Return how long the stop lasted."""
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class ExportOptions:
    """Settings of one export run."""

    title: str | None = None
    scale: float = 1.0
    margin: timedelta = timedelta(minutes=10)
    language: str = "de"
    timezone: tzinfo = UTC
    standstill_kmh: float = 3.0
    max_accuracy_m: float = 50.0
    min_point_distance_m: float = 15.0
    min_movement_m: float = 100.0
    elevation_hysteresis_m: float = 5.0
    max_gap: timedelta = timedelta(minutes=5)
    map_size: tuple[int, int] = (2400, 1600)
    map_line_width: int = 6
    user_agent: str = "reiseverlauftracker"
    with_map: bool = True
    stops: tuple[Stop, ...] = ()
