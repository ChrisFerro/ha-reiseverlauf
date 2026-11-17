"""Tests for preparing the track."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.reiseverlauftracker.export import (
    ExportOptions,
    NoMovementError,
    NotEnoughPointsError,
    StepSeries,
    TrackPoint,
    decode_speed,
)
from custom_components.reiseverlauftracker.export.track import coalesce, prepare_track, thin_out

pytestmark = pytest.mark.unit

START = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
DEPARTURE = START + timedelta(minutes=15)
ARRIVAL = START + timedelta(minutes=55)


def minutes(n: float) -> datetime:
    return START + timedelta(minutes=n)


def north(metres: float) -> tuple[float, float]:
    return 47.0 + metres / 111195.0, 11.0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (1118656744, pytest.approx(86.67, abs=0.01)),
        (50.0, 50.0),
        (0.0, 0.0),
        (-1.0, None),
        (250.0, None),
        (float("nan"), None),
        (None, None),
        (4294967295, None),
    ],
)
def test_decode_speed(raw: float | None, expected: object) -> None:
    assert decode_speed(raw) == expected


def test_step_series_holds_last_value() -> None:
    series = StepSeries([(minutes(10), 2.0), (minutes(0), 1.0)])
    assert series.value_at(minutes(-1)) is None
    assert series.value_at(minutes(5)) == 1.0
    assert series.value_at(minutes(10)) == 2.0

    window = series.window(minutes(5), minutes(20))
    assert window is not None
    assert window.times == [minutes(5), minutes(10)]
    assert window.values == [1.0, 2.0]


def test_prepare_trims_to_departure_and_arrival(
    positions: list[TrackPoint], speed: StepSeries, altitude: StepSeries
) -> None:
    track = prepare_track(positions, speed, altitude, ExportOptions())

    assert track.departure == DEPARTURE
    assert track.arrival == ARRIVAL
    assert track.chart_start == DEPARTURE - timedelta(minutes=10)
    assert track.chart_end == ARRIVAL + timedelta(minutes=10)
    assert all(p.accuracy == 10 for p in track.points)
    assert all(p.speed is not None and p.altitude is not None for p in track.points)


def test_prepare_keeps_recorded_values() -> None:
    a = TrackPoint(START, *north(0), speed=12.0, altitude=100.0)
    b = TrackPoint(minutes(1), *north(500))
    track = prepare_track([a, b], StepSeries([(START, 99.0)]), StepSeries([(START, 999.0)]), ExportOptions())

    assert (track.points[0].speed, track.points[0].altitude) == (12.0, 100.0)
    assert (track.points[1].speed, track.points[1].altitude) == (99.0, 999.0)


def test_prepare_without_sensor_series(positions: list[TrackPoint], speed: StepSeries, altitude: StepSeries) -> None:
    track = prepare_track(positions, None, None, ExportOptions())

    assert track.speed is None
    assert track.chart_speed is None
    assert all(p.altitude is None for p in track.points)


def test_prepare_rejects_too_few_points() -> None:
    good = TrackPoint(START, *north(0))
    bad = TrackPoint(minutes(1), *north(500), accuracy=80)
    with pytest.raises(NotEnoughPointsError):
        prepare_track([good, bad], None, None, ExportOptions())


def test_prepare_rejects_standstill() -> None:
    points = [TrackPoint(minutes(i), *north(i * 5)) for i in range(10)]
    with pytest.raises(NoMovementError):
        prepare_track(points, None, None, ExportOptions())


def test_thin_out_keeps_ends_and_spacing() -> None:
    points = [TrackPoint(minutes(i), *north(i * 6)) for i in range(11)]
    kept = thin_out(points, 15.0)

    assert kept[0] is points[0]
    assert kept[-1] is points[-1]
    assert [round(p.lat, 7) for p in kept[1:-1]] == [round(points[i].lat, 7) for i in (3, 6, 9)]


def test_coalesce_keeps_the_complete_update_of_each_fix() -> None:
    first = TrackPoint(START, 47.0, 11.0)
    half = TrackPoint(START + timedelta(seconds=5), 47.01, 11.0)
    full = TrackPoint(START + timedelta(seconds=6), 47.01, 11.01)
    later = TrackPoint(START + timedelta(seconds=10), 47.02, 11.01)

    assert coalesce([first, half, full, later]) == [first, full, later]


def test_prepare_measures_the_coalesced_track() -> None:
    """Separate latitude and longitude updates must not add a staircase to the distance."""
    points = []
    for i in range(1, 60):
        t = START + timedelta(seconds=5 * i)
        points.append(TrackPoint(t, 47.0 + i * 0.001, 11.0 + (i - 1) * 0.001, 10))
        points.append(TrackPoint(t + timedelta(seconds=1), 47.0 + i * 0.001, 11.0 + i * 0.001, 10))

    track = prepare_track(points, None, None, ExportOptions())

    assert all(round((p.lat - 47.0) * 1000) == round((p.lon - 11.0) * 1000) for p in track.points)
