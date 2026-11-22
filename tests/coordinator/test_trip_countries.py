"""Tests for the positions at which the countries of a trip are looked up."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.reiseverlauftracker.coordinator.trip_countries import country_sample_points, ordered_countries
from custom_components.reiseverlauftracker.coordinator.trip_log import RunningStatsSettings, TripLog, TripStop

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
# Slightly below the true 111194.93 m, so a step of "1000 m" is a little longer and 20 steps reach 20 km.
METRES_PER_DEGREE_LAT = 111194.0


def lat(metres: float) -> float:
    """Return the latitude `metres` north of 50°."""
    return 50.0 + metres / METRES_PER_DEGREE_LAT


def drive(km: int, *, step_m: float = 1000, accuracy: float = 10) -> TripLog:
    """Return a log of a straight drive north with one position per `step_m`, one minute apart."""
    log = TripLog(T0, RunningStatsSettings())
    for index in range(int(km * 1000 / step_m) + 1):
        log.add_position(T0 + timedelta(minutes=index), lat(index * step_m), 8.0, accuracy)
    return log


def test_start_every_20_km_and_end() -> None:
    points = country_sample_points(drive(50))

    assert [round((p.lat - 50.0) * METRES_PER_DEGREE_LAT / 1000) for p in points] == [0, 20, 40, 50]


def test_stops_are_added_in_time_order() -> None:
    log = drive(30)
    log.stops.append(TripStop(T0 + timedelta(minutes=5, seconds=30), lat(5500), 8.0, T0 + timedelta(minutes=20)))
    log.stops.append(TripStop(T0 + timedelta(minutes=25), None, None))

    points = country_sample_points(log)

    assert [round((p.lat - 50.0) * METRES_PER_DEGREE_LAT / 100) for p in points] == [0, 55, 200, 300]


def test_points_close_to_the_one_before_are_left_out() -> None:
    log = drive(30)
    log.stops.append(TripStop(T0 + timedelta(minutes=30, seconds=10), lat(30_200), 8.0))

    assert len(country_sample_points(log)) == 3


def test_inaccurate_positions_are_skipped() -> None:
    assert country_sample_points(drive(5, accuracy=500)) == []


def test_a_short_trip_has_start_and_end() -> None:
    assert len(country_sample_points(drive(3))) == 2


def test_ordered_countries_keep_the_first_appearance() -> None:
    assert ordered_countries(["DE", None, "AT", "DE", "IT", "AT"]) == ("DE", "AT", "IT")
