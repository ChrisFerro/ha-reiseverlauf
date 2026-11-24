"""Input data and options of the trip export."""

from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta, tzinfo
from enum import StrEnum
import math
from typing import Any

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
    lat: float | None = None
    lon: float | None = None
    ferry: bool = False
    """The vehicle was on a ferry; the crossing does not count as distance driven."""

    @property
    def duration(self) -> timedelta:
        """Return how long the stop lasted."""
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class LogbookFigures:
    """Logbook figures of one trip; costs in `ExportOptions.currency`."""

    odometer_start_km: float | None = None
    odometer_end_km: float | None = None
    fuel_litres: float = 0.0
    fuel_cost: float = 0.0
    gas_litres: float = 0.0
    gas_cost: float = 0.0
    consumption_l_100km: float | None = None
    """Average consumption over all refills up to the end of the trip, not of this trip alone."""
    travel_costs: dict[str, float] = field(default_factory=dict)
    """Travel costs of the trip (toll, ferry …) by category, usually entered after the trip."""

    @property
    def fuel_and_gas_cost(self) -> float:
        """Return fuel and gas costs together."""
        return self.fuel_cost + self.gas_cost

    @property
    def cost(self) -> float:
        """Return all costs: fuel, gas and travel costs."""
        return self.fuel_and_gas_cost + sum(self.travel_costs.values())

    def as_dict(self) -> dict[str, Any]:
        """Return the figures as stored in `export.json` and sent with the events, keyed in German."""
        return {
            "kilometerstand_start": self.odometer_start_km,
            "kilometerstand_ende": self.odometer_end_km,
            "diesel_liter": self.fuel_litres,
            "diesel_kosten": round(self.fuel_cost, 2),
            "gas_liter": self.gas_litres,
            "gas_kosten": round(self.gas_cost, 2),
            "reisekosten": {category: round(amount, 2) for category, amount in self.travel_costs.items()},
            "kosten": round(self.cost, 2),
            "verbrauch_l_100km": round(self.consumption_l_100km, 1) if self.consumption_l_100km is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LogbookFigures:
        """Rebuild the figures from `as_dict()` output."""
        return cls(
            odometer_start_km=data.get("kilometerstand_start"),
            odometer_end_km=data.get("kilometerstand_ende"),
            fuel_litres=data.get("diesel_liter") or 0.0,
            fuel_cost=data.get("diesel_kosten") or 0.0,
            gas_litres=data.get("gas_liter") or 0.0,
            gas_cost=data.get("gas_kosten") or 0.0,
            consumption_l_100km=data.get("verbrauch_l_100km"),
            travel_costs=dict(data.get("reisekosten") or {}),
        )


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
    logbook: LogbookFigures | None = None
    currency: str = "EUR"
    markers: tuple[MapMarker, ...] = ()
    """Symbols besides start and end, e.g. stops and refills (docs/features/feat-12-kartensymbole.md)."""
    arrival_stay: str | None = None
    """Name of the camp site or pitch at the arrival; the end symbol then shows a pitch."""


class MarkerKind(StrEnum):
    """Kinds of map symbols (docs/features/feat-12-kartensymbole.md 5.1); the value is used in texts and files."""

    START = "start"
    END = "ziel"
    PITCH = "stellplatz"
    STOP = "halt"
    FUEL = "diesel"
    GAS = "gas"
    FERRY = "faehre"


@dataclass(frozen=True, slots=True)
class MapMarker:
    """One symbol on the map."""

    kind: MarkerKind
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class FerryLeg:
    """
    A ferry crossing, drawn dashed with its symbol halfway along.

    `points` are (latitude, longitude) pairs; without positions on board they are
    just the last position before and the first after the crossing.
    """

    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class MapProjection:
    """
    Where a coordinate lies on a rendered map: Web Mercator tile numbers at `zoom`.

    Stored with the base map, so that symbols can be drawn again without tiles
    (docs/features/feat-12-kartensymbole.md 6.5).
    """

    zoom: int
    x_center: float
    y_center: float
    width: int
    height: int
    tile_size: int = 256

    def to_px(self, lat: float, lon: float) -> tuple[float, float]:
        """Return the pixel position of a coordinate, the same way `staticmap` draws its lines."""
        tiles = 2**self.zoom
        x = (lon + 180.0) / 360.0 * tiles
        rad = math.radians(lat)
        y = (1 - math.log(math.tan(rad) + 1 / math.cos(rad)) / math.pi) / 2 * tiles
        return (
            (x - self.x_center) * self.tile_size + self.width / 2,
            (y - self.y_center) * self.tile_size + self.height / 2,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the projection as a JSON-serialisable dict."""
        return {
            "zoom": self.zoom,
            "x_center": self.x_center,
            "y_center": self.y_center,
            "width": self.width,
            "height": self.height,
            "tile_size": self.tile_size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MapProjection:
        """Rebuild a projection from `as_dict()` output."""
        return cls(
            zoom=int(data["zoom"]),
            x_center=float(data["x_center"]),
            y_center=float(data["y_center"]),
            width=int(data["width"]),
            height=int(data["height"]),
            tile_size=int(data.get("tile_size", 256)),
        )
