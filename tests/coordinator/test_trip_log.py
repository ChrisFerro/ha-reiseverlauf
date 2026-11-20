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


def test_average_counts_only_moving_sections() -> None:
    log = TripLog(T0, SETTINGS)
    log.add_position(at(0), lat(0), 8.0, 10)
    log.add_position(at(60), lat(1000), 8.0, 10)
    log.add_position(at(1200), lat(1001), 8.0, 10)

    assert log.driving_time == timedelta(minutes=1)
    assert log.average_moving_kmh == pytest.approx(60.0, rel=1e-3)
    assert TripLog(T0, SETTINGS).average_moving_kmh is None


def test_stops_shorter_than_minimum_do_not_count() -> None:
    log = TripLog(T0, SETTINGS)
    log.add_position(at(0), lat(0), 8.0, 10)
    log.begin_stop(at(60))
    assert log.end_stop(at(120), timedelta(minutes=5)) is None
    assert log.confirmed_stops(at(120), timedelta(minutes=5)) == []
    assert log.export_stops(at(120), timedelta(minutes=5)) == ()

    log.add_position(at(150), lat(500), 8.0, 10)
    log.begin_stop(at(200))
    stop = log.end_stop(at(900), timedelta(minutes=5))
    assert stop is not None
    assert (stop.start, stop.end, stop.lat) == (at(200), at(900), pytest.approx(lat(500)))


def test_open_stop_counts_once_it_reaches_the_minimum() -> None:
    log = TripLog(T0, SETTINGS)
    log.begin_stop(at(0))
    log.begin_stop(at(30))

    assert len(log.stops) == 1
    assert log.confirmed_stops(at(120), timedelta(minutes=5)) == []
    assert len(log.confirmed_stops(at(400), timedelta(minutes=5))) == 1


def test_export_stops_leave_out_the_arrival() -> None:
    log = TripLog(T0, SETTINGS)
    log.begin_stop(at(0))
    log.end_stop(at(600), timedelta(minutes=5))
    log.set_stop_place(at(0), "Brenner")
    log.begin_stop(at(3600))

    stops = log.export_stops(at(3600), timedelta(minutes=5))

    assert len(stops) == 1
    assert (stops[0].place, stops[0].duration) == ("Brenner", timedelta(minutes=10))


def test_short_engine_runs_without_moving_continue_the_stop() -> None:
    """Refuel, move to a parking space, stop again: one stop (as on 31.10.2026)."""
    log = TripLog(T0, SETTINGS)
    five = timedelta(minutes=5)
    log.add_position(at(0), lat(0), 8.0, 10)
    log.begin_stop(at(60))
    assert log.end_stop(at(300), five) is None
    log.add_position(at(320), lat(40), 8.0, 10)
    log.begin_stop(at(360))
    assert log.end_stop(at(600), five) is not None
    log.begin_stop(at(800))
    log.end_stop(at(1300), five)

    assert [(s.start, s.end) for s in log.export_stops(at(3600), five)] == [(at(60), at(1300))]


def test_a_stop_does_not_continue_after_the_vehicle_drove_off() -> None:
    log = TripLog(T0, SETTINGS)
    five = timedelta(minutes=5)
    log.add_position(at(0), lat(0), 8.0, 10)
    log.begin_stop(at(60))
    log.end_stop(at(600), five)
    log.add_position(at(660), lat(2000), 8.0, 10)
    log.add_position(at(720), lat(50), 8.0, 10)
    log.begin_stop(at(780))
    log.end_stop(at(1200), five)

    assert [(s.start, s.end) for s in log.export_stops(at(3600), five)] == [(at(60), at(600)), (at(780), at(1200))]


def test_lat_and_lon_updates_of_one_fix_are_coalesced() -> None:
    """A tracker fed by two sensors reports the new latitude first, then the longitude."""
    log = TripLog(T0, SETTINGS)
    log.add_position(at(0), 50.0, 8.0, 10)
    log.add_position(at(5), lat(1000), 8.0, 10)
    log.add_position(at(6), lat(1000), 8.014, 10)
    log.add_position(at(10), lat(2000), 8.014, 10)
    log.add_position(at(11), lat(2000), 8.028, 10)

    straight = TripLog(T0, SETTINGS)
    straight.add_position(at(0), 50.0, 8.0, 10)
    straight.add_position(at(6), lat(1000), 8.014, 10)
    straight.add_position(at(11), lat(2000), 8.028, 10)

    assert len(log.positions) == 3
    assert log.distance_m == pytest.approx(straight.distance_m)
    assert log.driving_time == straight.driving_time
    assert log.moving_distance_m == pytest.approx(straight.moving_distance_m)


def test_a_tracker_updating_every_second_is_not_collapsed() -> None:
    log = TripLog(T0, SETTINGS)
    for second in range(10):
        log.add_position(at(second), lat(second * 20), 8.0, 10)

    assert [p.time for p in log.positions] == [at(2), at(5), at(8), at(9)]
    assert log.distance_km == pytest.approx(0.14, rel=1e-3)


def test_start_place_and_stops_survive_a_restart() -> None:
    log = TripLog(T0, SETTINGS)
    log.add_position(at(0), lat(0), 8.0, 10)
    log.start_place = "Kiel"
    log.begin_stop(at(60))
    log.set_stop_place(at(60), "Laboe")

    restored = TripLog.from_dict(json.loads(json.dumps(log.as_dict())), SETTINGS)

    assert restored.start_place == "Kiel"
    assert restored.stops == log.stops


def test_logs_stored_by_older_versions_still_load() -> None:
    old = {"version": 1, "start": T0.isoformat(), "positions": [], "speed": [], "altitude": []}

    log = TripLog.from_dict(old, SETTINGS)

    assert log.start_place is None
    assert log.stops == []


def test_ascent_counts_climbs_beyond_the_hysteresis() -> None:
    log = TripLog(T0, RunningStatsSettings(elevation_hysteresis_m=5))
    for minute, metres in enumerate((100, 103, 98, 110, 108, 104, 120)):
        log.add_altitude(T0 + timedelta(minutes=minute), metres)

    # 100 → 110 (+10), 110 → 104 (down), 104 → 120 (+16); the noise of 3 m adds nothing.
    assert log.ascent_m == pytest.approx(26)
    restored = TripLog.from_dict(json.loads(json.dumps(log.as_dict())), log.settings)
    assert restored.ascent_m == pytest.approx(26)
