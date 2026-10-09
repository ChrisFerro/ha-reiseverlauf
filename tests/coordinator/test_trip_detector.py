"""Tests for the trip detection state machine."""

from datetime import UTC, datetime, timedelta
import json

import pytest

from custom_components.reiseverlauftracker.coordinator.trip_detector import (
    DetectorSettings,
    TripClosed,
    TripDetector,
    TripDiscarded,
    TripEnded,
    TripPhase,
    TripResumed,
    TripStarted,
)
from custom_components.reiseverlauftracker.utils.geo import Position

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
HOME = Position(50.0, 8.0)
METRES_PER_DEGREE_LAT = 111195.0
SETTINGS = DetectorSettings(
    end_delay=timedelta(minutes=60),
    merge_window=timedelta(hours=6),
    min_movement_m=100.0,
)


def north(metres: float) -> Position:
    """Return a position `metres` north of HOME."""
    return Position(HOME.lat + metres / METRES_PER_DEGREE_LAT, HOME.lon)


def minutes(n: float) -> datetime:
    """Return T0 plus `n` minutes."""
    return T0 + timedelta(minutes=n)


def drive(detector: TripDetector, start_min: float, end_min: float, metres: float) -> None:
    """Start a trip at HOME and drive `metres` north, then switch D+ off."""
    detector.update_position(HOME, minutes(start_min - 1))
    assert detector.update_dplus(True, minutes(start_min)) == [TripStarted(minutes(start_min))]
    detector.update_position(north(metres / 2), minutes((start_min + end_min) / 2))
    detector.update_position(north(metres), minutes(end_min - 1))
    assert detector.update_dplus(False, minutes(end_min)) == []


def test_normal_trip_ends_after_delay_at_dplus_off_time() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 120, 50_000)

    assert detector.next_deadline() == minutes(180)
    assert detector.tick(minutes(179)) == []
    assert detector.tick(minutes(180)) == [
        TripEnded(start=T0, end=minutes(120), max_distance_m=pytest.approx(50_000), resumed=False)
    ]
    assert detector.phase is TripPhase.ENDED
    assert detector.next_deadline() == minutes(120 + 360)

    assert detector.tick(minutes(120 + 360)) == [TripClosed(start=T0, end=minutes(120))]
    assert detector.phase is TripPhase.IDLE
    assert detector.next_deadline() is None


def test_short_stop_belongs_to_same_trip() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 60, 20_000)

    assert detector.update_dplus(True, minutes(90)) == []
    assert detector.next_deadline() is None
    detector.update_position(north(40_000), minutes(150))
    assert detector.update_dplus(False, minutes(160)) == []

    assert detector.tick(minutes(220)) == [
        TripEnded(start=T0, end=minutes(160), max_distance_m=pytest.approx(40_000), resumed=False)
    ]


def test_trip_without_movement_is_discarded() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 30, 80)

    assert detector.tick(minutes(90)) == [TripDiscarded(start=T0, end=minutes(30), max_distance_m=pytest.approx(80))]
    assert detector.phase is TripPhase.IDLE
    assert detector.next_deadline() is None


def test_start_position_falls_back_to_first_position() -> None:
    detector = TripDetector(SETTINGS)
    detector.update_dplus(True, T0)
    detector.update_position(HOME, minutes(1))
    detector.update_position(north(500), minutes(5))
    detector.update_dplus(False, minutes(10))

    events = detector.tick(minutes(70))
    assert isinstance(events[0], TripEnded)
    assert events[0].max_distance_m == pytest.approx(500)


def test_ferry_movement_without_dplus_extends_trip() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 60, 10_000)

    # On the ferry: engine off, but the position keeps changing for 90 minutes.
    for step in range(1, 10):
        assert detector.update_position(north(10_000 + step * 2_000), minutes(60 + step * 10)) == []
    assert detector.tick(minutes(130)) == []
    assert detector.next_deadline() == minutes(150 + 60)

    # Drive off the ferry with the engine on: the same trip continues.
    assert detector.update_dplus(True, minutes(155)) == []
    assert detector.phase is TripPhase.ACTIVE
    detector.update_position(north(40_000), minutes(200))
    detector.update_dplus(False, minutes(210))

    assert detector.tick(minutes(270)) == [
        TripEnded(start=T0, end=minutes(210), max_distance_m=pytest.approx(40_000), resumed=False)
    ]


def test_trip_ending_on_the_move_ends_at_last_motion() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 60, 10_000)
    detector.update_position(north(12_000), minutes(80))

    assert detector.tick(minutes(139)) == []
    events = detector.tick(minutes(140))
    assert isinstance(events[0], TripEnded)
    assert events[0].end == minutes(80)


def test_long_wait_before_ferry_resumes_ended_trip() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 60, 10_000)

    ended = detector.tick(minutes(120))
    assert ended == [TripEnded(start=T0, end=minutes(60), max_distance_m=pytest.approx(10_000), resumed=False)]

    # The ferry leaves two hours after the engine went off.
    assert detector.update_position(north(10_500), minutes(180)) == [TripResumed(start=T0, resumed_at=minutes(180))]
    assert detector.phase is TripPhase.ACTIVE
    detector.update_position(north(30_000), minutes(240))
    assert detector.update_dplus(True, minutes(250)) == []
    detector.update_position(north(60_000), minutes(300))
    detector.update_dplus(False, minutes(310))

    assert detector.tick(minutes(370)) == [
        TripEnded(start=T0, end=minutes(310), max_distance_m=pytest.approx(60_000), resumed=True)
    ]


def test_dplus_within_merge_window_resumes_ended_trip() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 60, 10_000)
    detector.tick(minutes(120))

    assert detector.update_dplus(True, minutes(300)) == [TripResumed(start=T0, resumed_at=minutes(300))]
    assert detector.start == T0
    assert detector.end is None


def test_gps_jitter_does_not_resume_ended_trip() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 60, 10_000)
    detector.tick(minutes(120))

    assert detector.update_position(north(10_050), minutes(150)) == []
    assert detector.update_position(north(9_960), minutes(200)) == []
    assert detector.phase is TripPhase.ENDED


def test_dplus_after_merge_window_starts_new_trip() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 60, 10_000)
    detector.tick(minutes(120))

    assert detector.update_dplus(True, minutes(500)) == [
        TripClosed(start=T0, end=minutes(60)),
        TripStarted(start=minutes(500)),
    ]


def test_late_input_processes_missed_deadline_first() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 60, 10_000)

    assert detector.update_dplus(True, minutes(200)) == [
        TripEnded(start=T0, end=minutes(60), max_distance_m=pytest.approx(10_000), resumed=False),
        TripResumed(start=T0, resumed_at=minutes(200)),
    ]


def test_merge_window_shorter_than_delay_closes_immediately() -> None:
    detector = TripDetector(DetectorSettings(merge_window=timedelta(0)))
    drive(detector, 0, 60, 10_000)

    events = detector.tick(minutes(120))
    assert [type(e) for e in events] == [TripEnded, TripClosed]
    assert detector.phase is TripPhase.IDLE


def test_duplicate_dplus_updates_are_ignored() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 60, 10_000)

    assert detector.update_dplus(False, minutes(90)) == []
    assert detector.next_deadline() == minutes(120)


def test_state_round_trip_through_json() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 60, 10_000)
    detector.update_position(north(10_500), minutes(70))

    stored = json.loads(json.dumps(detector.as_dict()))
    restored = TripDetector(SETTINGS, stored)

    assert restored.as_dict() == detector.as_dict()
    assert restored.next_deadline() == minutes(130)
    assert restored.tick(minutes(130)) == detector.tick(minutes(130))


def test_restore_without_state_and_dplus_on_starts_at_last_changed() -> None:
    detector = TripDetector(SETTINGS)

    assert detector.restore(True, minutes(-30), T0) == [TripStarted(start=minutes(-30))]
    assert detector.phase is TripPhase.ACTIVE


def test_restore_without_state_and_dplus_off_stays_idle() -> None:
    detector = TripDetector(SETTINGS)

    assert detector.restore(False, minutes(-30), T0) == []
    assert detector.phase is TripPhase.IDLE


def test_restore_ends_trip_whose_countdown_expired_during_downtime() -> None:
    before = TripDetector(SETTINGS)
    drive(before, 0, 60, 10_000)

    detector = TripDetector(SETTINGS, before.as_dict())
    assert detector.restore(False, minutes(60), minutes(200)) == [
        TripEnded(start=T0, end=minutes(60), max_distance_m=pytest.approx(10_000), resumed=False)
    ]


def test_restore_resumes_countdown_still_running() -> None:
    before = TripDetector(SETTINGS)
    drive(before, 0, 60, 10_000)

    detector = TripDetector(SETTINGS, before.as_dict())
    assert detector.restore(False, minutes(60), minutes(90)) == []
    assert detector.next_deadline() == minutes(120)


def test_restore_replays_dplus_off_missed_during_downtime() -> None:
    before = TripDetector(SETTINGS)
    before.update_position(HOME, minutes(-1))
    before.update_dplus(True, T0)
    before.update_position(north(10_000), minutes(50))

    detector = TripDetector(SETTINGS, before.as_dict())
    assert detector.restore(False, minutes(60), minutes(200)) == [
        TripEnded(start=T0, end=minutes(60), max_distance_m=pytest.approx(10_000), resumed=False)
    ]


def test_restore_replays_dplus_on_missed_during_downtime() -> None:
    before = TripDetector(SETTINGS)
    drive(before, 0, 60, 10_000)

    detector = TripDetector(SETTINGS, before.as_dict())
    assert detector.restore(True, minutes(90), minutes(100)) == []
    assert detector.phase is TripPhase.ACTIVE
    assert detector.next_deadline() is None


def test_manual_end_while_driving_ends_at_call_time() -> None:
    detector = TripDetector(SETTINGS)
    detector.update_position(HOME, minutes(-1))
    detector.update_dplus(True, T0)
    detector.update_position(north(10_000), minutes(50))

    assert detector.end_manually(minutes(55)) == [
        TripEnded(start=T0, end=minutes(55), max_distance_m=pytest.approx(10_000), resumed=False)
    ]
    assert detector.phase is TripPhase.ENDED
    assert detector.next_deadline() == minutes(55 + 360)


def test_manual_end_during_countdown_skips_delay() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 60, 10_000)

    assert detector.end_manually(minutes(70)) == [
        TripEnded(start=T0, end=minutes(70), max_distance_m=pytest.approx(10_000), resumed=False)
    ]


def test_manual_end_without_movement_is_discarded() -> None:
    detector = TripDetector(SETTINGS)
    detector.update_position(HOME, minutes(-1))
    detector.update_dplus(True, T0)
    detector.update_position(north(50), minutes(10))

    assert detector.end_manually(minutes(20)) == [
        TripDiscarded(start=T0, end=minutes(20), max_distance_m=pytest.approx(50))
    ]
    assert detector.phase is TripPhase.IDLE


def test_manual_end_without_trip_does_nothing() -> None:
    detector = TripDetector(SETTINGS)

    assert detector.end_manually(T0) == []
    assert detector.phase is TripPhase.IDLE


def test_dplus_still_on_after_manual_end_resumes_only_on_new_switch_on() -> None:
    detector = TripDetector(SETTINGS)
    detector.update_position(HOME, minutes(-1))
    detector.update_dplus(True, T0)
    detector.update_position(north(10_000), minutes(50))
    detector.end_manually(minutes(55))

    assert detector.update_dplus(True, minutes(56)) == []
    assert detector.update_position(north(12_000), minutes(58)) == []
    assert detector.update_dplus(False, minutes(60)) == []
    assert detector.phase is TripPhase.ENDED
    assert detector.update_dplus(True, minutes(120)) == [TripResumed(start=T0, resumed_at=minutes(120))]


def test_movement_after_manual_end_with_dplus_off_resumes() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 60, 10_000)
    detector.end_manually(minutes(70))

    assert detector.update_position(north(11_000), minutes(100)) == [TripResumed(start=T0, resumed_at=minutes(100))]


def test_manual_end_after_expired_countdown_keeps_automatic_end() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 60, 10_000)

    assert detector.end_manually(minutes(200)) == [
        TripEnded(start=T0, end=minutes(60), max_distance_m=pytest.approx(10_000), resumed=False)
    ]


def test_manual_start_without_dplus_runs_end_delay_from_start() -> None:
    detector = TripDetector(SETTINGS)
    detector.update_position(HOME, minutes(-1))

    assert detector.start_manually(T0) == [TripStarted(start=T0)]
    assert detector.phase is TripPhase.ACTIVE
    assert detector.next_deadline() == minutes(60)

    detector.update_position(north(5_000), minutes(40))
    assert detector.next_deadline() == minutes(100)
    assert detector.tick(minutes(100)) == [
        TripEnded(start=T0, end=minutes(40), max_distance_m=pytest.approx(5_000), resumed=False)
    ]


def test_manual_start_with_dplus_on_has_no_countdown() -> None:
    detector = TripDetector(SETTINGS)
    detector.update_dplus(True, T0)
    detector.end_manually(minutes(10))
    detector.tick(minutes(10))

    assert detector.phase is TripPhase.IDLE
    assert detector.start_manually(minutes(20)) == [TripStarted(start=minutes(20))]
    assert detector.next_deadline() is None


def test_manual_start_resumes_ended_trip() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 60, 10_000)
    detector.tick(minutes(120))

    assert detector.start_manually(minutes(150)) == [TripResumed(start=T0, resumed_at=minutes(150))]
    assert detector.next_deadline() == minutes(210)


def test_manual_start_during_running_trip_does_nothing() -> None:
    detector = TripDetector(SETTINGS)
    drive(detector, 0, 60, 10_000)

    assert detector.start_manually(minutes(70)) == []
    assert detector.next_deadline() == minutes(120)
