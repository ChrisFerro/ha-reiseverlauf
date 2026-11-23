"""Tests for the symbols of a trip map taken from its stops and logbook entries."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.reiseverlauftracker.coordinator.logbook import LogbookEntry, Occasion, Refill
from custom_components.reiseverlauftracker.coordinator.map_symbols import trip_markers
from custom_components.reiseverlauftracker.export import MapMarker, MarkerKind, Stop, TrackPoint

pytestmark = pytest.mark.unit

START = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)


def at(minutes: float) -> datetime:
    return START + timedelta(minutes=minutes)


POINTS = [TrackPoint(at(m), 47.0 + m / 1000, 11.0) for m in range(0, 61, 10)]


def entry(minutes: float, *, fuel: bool = False, gas: bool = False, lat: float | None = None) -> LogbookEntry:
    return LogbookEntry(
        id=f"e{minutes}",
        time=at(minutes),
        occasion=Occasion.STOP,
        distance_counter_m=0,
        fuel=Refill(40, 70) if fuel else None,
        gas=Refill(20, 25) if gas else None,
        lat=lat,
        lon=11.5 if lat is not None else None,
    )


def test_stops_and_refills_become_symbols() -> None:
    stops = [Stop(at(20), at(30), "Kiel", 47.5, 11.5)]
    entries = [entry(20, fuel=True, gas=True, lat=47.5), entry(40)]

    markers = trip_markers(stops, entries, POINTS)

    assert markers == (
        MapMarker(MarkerKind.STOP, 47.5, 11.5),
        MapMarker(MarkerKind.FUEL, 47.5, 11.5),
        MapMarker(MarkerKind.GAS, 47.5, 11.5),
    )


def test_without_a_stored_position_the_nearest_recorded_one_is_taken() -> None:
    stops = [Stop(at(31), at(45), "Kiel")]
    entries = [entry(52, gas=True)]

    markers = trip_markers(stops, entries, POINTS)

    assert markers == (MapMarker(MarkerKind.STOP, 47.03, 11.0), MapMarker(MarkerKind.GAS, 47.05, 11.0))


def test_without_any_position_there_is_no_symbol() -> None:
    assert trip_markers([Stop(at(1), at(9))], [entry(5, fuel=True)], []) == ()
