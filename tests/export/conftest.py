"""Synthetic trip data for the export tests."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import io

from PIL import Image
import pytest

from custom_components.reiseverlauftracker.export import StepSeries, TrackPoint

START = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
ORIGIN_LAT, ORIGIN_LON = 47.0, 11.0
METRES_PER_DEGREE_LAT = 111195.0
STANDSTILL = 15
DRIVE = 40
STEP_S = 10
DRIVE_KM = 30.0


@dataclass
class SyntheticTrip:
    """Positions, speed and altitude of a fake 30 km drive between two 15-minute stops."""

    positions: list[TrackPoint]
    speed: StepSeries
    altitude: StepSeries
    departure: datetime
    arrival: datetime


def minutes(n: float) -> datetime:
    return START + timedelta(minutes=n)


def north(metres: float) -> tuple[float, float]:
    return ORIGIN_LAT + metres / METRES_PER_DEGREE_LAT, ORIGIN_LON


def make_trip() -> SyntheticTrip:
    positions: list[TrackPoint] = []
    speed: list[tuple[datetime, float]] = [(minutes(-30), 0.0)]
    altitude: list[tuple[datetime, float]] = [(minutes(-30), 600.0)]
    for s in range(0, STANDSTILL * 60, 60):
        lat, lon = north(s % 7)
        positions.append(TrackPoint(START + timedelta(seconds=s), lat, lon, accuracy=10))
    departure = minutes(STANDSTILL)
    steps = DRIVE * 60 // STEP_S
    for i in range(steps + 1):
        t = departure + timedelta(seconds=i * STEP_S)
        fraction = i / steps
        lat, lon = north(DRIVE_KM * 1000 * fraction)
        positions.append(TrackPoint(t, lat, lon, accuracy=10))
        speed.append((t, 45.0 if 0 < i < steps else 0.0))
        # Climb 300 m to the middle, then descend 200 m.
        altitude.append((t, 600 + 600 * fraction if fraction <= 0.5 else 900 - 400 * (fraction - 0.5)))
    arrival = departure + timedelta(minutes=DRIVE)
    for s in range(60, STANDSTILL * 60, 60):
        lat, lon = north(DRIVE_KM * 1000 + s % 5)
        positions.append(TrackPoint(arrival + timedelta(seconds=s), lat, lon, accuracy=10))
    # A wild fix with bad accuracy that must be filtered out.
    positions.append(TrackPoint(minutes(5.5), 48.0, 12.0, accuracy=500))
    return SyntheticTrip(positions, StepSeries(speed), StepSeries(altitude), departure, arrival)


@pytest.fixture
def positions() -> list[TrackPoint]:
    """Return the positions of a fake 30 km drive from 08:15 to 08:55 UTC between two 15-minute stops."""
    return make_trip().positions


@pytest.fixture
def speed() -> StepSeries:
    """Return the speed history of the fake drive: 45 km/h while moving."""
    return make_trip().speed


@pytest.fixture
def altitude() -> StepSeries:
    """Return the altitude history of the fake drive: 600 m up to 900 m, down to 700 m."""
    return make_trip().altitude


def tile_png(color: str = "#cfe8cf") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def fake_tiles() -> list[str]:
    """Collect requested tile URLs; used with `offline_fetcher`."""
    return []


@pytest.fixture
def offline_fetcher(fake_tiles: list[str]):
    """Return a tile fetcher that serves a plain tile without network access."""
    tile = tile_png()

    def fetch(url: str) -> bytes:
        fake_tiles.append(url)
        return tile

    return fetch
