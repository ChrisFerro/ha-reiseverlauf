"""Tests for the per-trip point log."""

from datetime import UTC, datetime, timedelta
import json

import pytest

from custom_components.reiseverlauftracker.coordinator.trip_log import RunningStatsSettings, TripLog

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
METRES_PER_DEGREE_LAT = 111195.0
SETTINGS = RunningStatsSettings()


def at(seconds: float) -> datetime:
    """Return T0 plus `seconds`."""
    return T0 + timedelta(seconds=seconds)


def lat(metres: float) -> float:
    """Return the latitude `metres` north of 50°."""
    return 50.0 + metres / METRES_PER_DEGREE_LAT


def test_distance_and_driving_time_accumulate() -> None:
    log = TripLog(T0, SETTINGS)
    log.add_position(at(0), lat(0), 8.0, 10)
    log.add_position(at(60), lat(1000), 8.0, 10)
    log.add_position(at(120), lat(2000), 8.0, 10)

    assert log.distance_km == pytest.approx(2.0, rel=1e-3)
    assert log.driving_time == timedelta(minutes=2)


def test_standstill_and_long_gaps_do_not_count_as_driving() -> None:
    log = TripLog(T0, SETTINGS)
    log.add_position(at(0), lat(0), 8.0, 10)
    log.add_position(at(600), lat(1), 8.0, 10)
    log.add_position(at(1200), lat(5000), 8.0, 10)

    assert log.distance_km == pytest.approx(5.0, rel=1e-3)
    assert log.driving_time == timedelta(0)


def test_inaccurate_positions_are_kept_but_skipped_for_statistics() -> None:
    log = TripLog(T0, SETTINGS)
    log.add_position(at(0), lat(0), 8.0, 10)
    log.add_position(at(30), lat(3000), 8.0, 500)
    log.add_position(at(60), lat(1000), 8.0, 10)

    assert len(log.positions) == 3
    assert log.distance_km == pytest.approx(1.0, rel=1e-3)


def test_export_inputs_decode_old_speed_bits() -> None:
    log = TripLog(T0, SETTINGS)
    log.add_position(at(0), lat(0), 8.0, 10)
    log.add_speed(at(0), 1118656744)
    log.add_speed(at(10), 50)
    log.add_speed(at(20), 999)
    log.add_altitude(at(0), 120.5)

    positions, speed, altitude = log.export_inputs()

    assert len(positions) == 1
    assert speed is not None
    assert speed.values == [pytest.approx(86.67, abs=0.01), 50]
    assert altitude is not None
    assert altitude.values == [120.5]


def test_export_inputs_without_sensor_values() -> None:
    _, speed, altitude = TripLog(T0, SETTINGS).export_inputs()

    assert speed is None
    assert altitude is None


def test_round_trip_through_json_rebuilds_statistics() -> None:
    log = TripLog(T0, SETTINGS)
    log.add_position(at(0), lat(0), 8.0, 10)
    log.add_position(at(60), lat(1000), 8.0, None)
    log.add_speed(at(0), 60)
    log.add_altitude(at(30), 100)

    restored = TripLog.from_dict(json.loads(json.dumps(log.as_dict())), SETTINGS)

    assert restored.as_dict() == log.as_dict()
    assert restored.distance_km == pytest.approx(log.distance_km)
    assert restored.driving_time == log.driving_time


def test_from_export_inputs_matches_a_recorded_log() -> None:
    log = TripLog(T0, SETTINGS)
    log.add_position(at(0), lat(0), 8.0, 10)
    log.add_position(at(60), lat(1000), 8.0, 10)
    log.add_speed(at(0), 60)
    log.add_altitude(at(30), 100)

    rebuilt = TripLog.from_export_inputs(T0, log.export_inputs(), SETTINGS)

    assert rebuilt.as_dict() == log.as_dict()
    assert rebuilt.distance_km == pytest.approx(log.distance_km)
