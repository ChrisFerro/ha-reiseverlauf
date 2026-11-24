"""Tests for the per-trip point log."""

from datetime import UTC, datetime, timedelta
import json

import pytest

from custom_components.reiseverlauftracker.coordinator.trip_log import (
    FerryMark,
    RunningStatsSettings,
    TrackCounters,
    TripLog,
)

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


def test_ascent_and_descent_count_changes_beyond_the_hysteresis() -> None:
    log = TripLog(T0, RunningStatsSettings(elevation_hysteresis_m=5))
    for minute, metres in enumerate((100, 103, 98, 110, 108, 104, 120)):
        log.add_altitude(T0 + timedelta(minutes=minute), metres)

    # 100 → 110 (+10), 110 → 104 (-6), 104 → 120 (+16); the noise of 3 to 5 m adds nothing.
    assert (log.ascent_m, log.descent_m) == (pytest.approx(26), pytest.approx(6))
    restored = TripLog.from_dict(json.loads(json.dumps(log.as_dict())), log.settings)
    assert (restored.ascent_m, restored.descent_m) == (pytest.approx(26), pytest.approx(6))


def test_counters_at_add_the_track_up_to_a_time_to_the_start_counters() -> None:
    log = TripLog(T0, SETTINGS)
    log.counter_start = TrackCounters(100_000, 500, 400)
    for minute in range(4):
        log.add_position(at(60 * minute), lat(1000 * minute), 8.0, 10)
        log.add_altitude(at(60 * minute), 100 + 10 * minute)

    halfway = log.counters_at(at(90))

    assert halfway is not None
    assert halfway.distance_m == pytest.approx(101_000, abs=1)
    assert (halfway.ascent_m, halfway.descent_m) == (510, 400)
    end = log.counters_at(at(600))
    assert end is not None
    assert end.distance_m == pytest.approx(100_000 + log.distance_m)
    assert end.ascent_m == 500 + log.ascent_m


def test_counters_at_use_the_same_filters_as_the_trip_distance() -> None:
    log = TripLog(T0, SETTINGS)
    log.counter_start = TrackCounters(0)
    log.add_position(at(0), lat(0), 8.0, 10)
    log.add_position(at(60), lat(5000), 8.0, 500)
    log.add_position(at(120), lat(2000), 8.0, 10)

    counters = log.counters_at(at(120))

    assert counters is not None
    assert counters.distance_m == pytest.approx(log.distance_m)
    assert counters.distance_m == pytest.approx(2000, rel=1e-3)


def test_counters_at_are_unknown_without_start_counters() -> None:
    log = TripLog(T0, SETTINGS)
    log.add_position(at(0), lat(0), 8.0, 10)

    assert log.counters_at(at(0)) is None


def test_position_at_returns_the_last_usable_position_before() -> None:
    log = TripLog(T0, SETTINGS)
    assert log.position_at(at(0)) is None
    log.add_position(at(0), lat(0), 8.0, 10)
    log.add_position(at(60), lat(1000), 8.0, 10)
    log.add_position(at(120), lat(2000), 8.0, 500)

    position = log.position_at(at(150))
    assert position is not None
    assert position.lat == pytest.approx(lat(1000))
    earliest = log.position_at(T0 - timedelta(minutes=1))
    assert earliest is not None
    assert earliest.lat == pytest.approx(lat(0))


def test_start_counters_survive_a_round_trip() -> None:
    log = TripLog(T0, SETTINGS)
    log.counter_start = TrackCounters(12_345.5, 10, 20)

    restored = TripLog.from_dict(json.loads(json.dumps(log.as_dict())), SETTINGS)

    assert restored.counter_start == log.counter_start
    old = log.as_dict()
    del old["counter_start"]
    assert TripLog.from_dict(old, SETTINGS).counter_start is None


def ferry_log() -> TripLog:
    """Drive 1 km, stop and cross 3 km with D+ off, then drive 1 km more."""
    log = TripLog(T0, SETTINGS)
    log.counter_start = TrackCounters(100_000)
    log.add_position(at(0), lat(0), 8.0, 10)
    log.add_position(at(60), lat(1000), 8.0, 10)
    log.begin_stop(at(90))
    for minute in range(1, 4):
        log.add_position(at(90 + 600 * minute), lat(1000 + 1000 * minute), 8.0, 10)
    log.end_stop(at(2000), timedelta(minutes=5))
    log.add_position(at(2060), lat(5000), 8.0, 10)
    return log


def test_marked_ferry_is_not_driven_and_counted_again_when_unmarked() -> None:
    log = ferry_log()
    assert log.distance_m == pytest.approx(5000, abs=1)

    changed = log.set_ferry(log.stops[0].start, FerryMark.HAND)

    assert changed is not None
    assert changed.is_ferry
    # 1 km before and the step off the ship (4 km → 5 km) after it belong to the crossing.
    assert log.distance_m == pytest.approx(1000, abs=1)
    assert log.export_stops(at(3000), timedelta(minutes=5))[0].ferry
    counters = log.counters_at(at(1500))
    assert counters is not None
    assert counters.distance_m == pytest.approx(101_000, abs=1)

    log.set_ferry(log.stops[0].start, FerryMark.NONE)

    assert log.distance_m == pytest.approx(5000, abs=1)
    assert not log.stops[0].is_ferry


def test_ferry_survives_storage_and_is_not_counted_after_a_restart() -> None:
    log = ferry_log()
    log.set_ferry(log.stops[0].start, FerryMark.AUTO)

    restored = TripLog.from_dict(json.loads(json.dumps(log.as_dict())), SETTINGS)

    assert restored.stops[0].ferry is FerryMark.AUTO
    assert restored.distance_m == pytest.approx(1000, abs=1)


def test_unknown_stop_cannot_be_marked() -> None:
    assert ferry_log().set_ferry(at(5), FerryMark.HAND) is None


def test_ferry_probe_is_halfway_along_the_movement_during_the_stop() -> None:
    log = ferry_log()

    probe = log.ferry_probe(log.stops[0])

    assert probe is not None
    assert probe.lat == pytest.approx(lat(3000))


def test_no_ferry_probe_for_a_stop_without_movement() -> None:
    log = TripLog(T0, SETTINGS)
    log.add_position(at(0), lat(0), 8.0, 10)
    log.begin_stop(at(10))
    log.add_position(at(300), lat(20), 8.0, 10)
    log.add_position(at(600), lat(40), 8.0, 10)
    stop = log.end_stop(at(900), timedelta(minutes=5))

    assert stop is not None
    assert log.ferry_probe(stop) is None
