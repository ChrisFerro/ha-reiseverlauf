"""Tests for resolving the time of a late logbook entry and saving it."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from custom_components.reiseverlauftracker.coordinator.late_entry import (
    LatePoint,
    TripSpan,
    entry_for,
    matching_stop,
    resolve_time,
    stop_point,
)
from custom_components.reiseverlauftracker.coordinator.logbook import FormField, Logbook, Occasion, RecordedStop, Refill
from custom_components.reiseverlauftracker.coordinator.logbook_keeper import LogbookKeeper
from custom_components.reiseverlauftracker.coordinator.trip_log import RunningStatsSettings, TrackCounters, TripLog
from homeassistant.core import HomeAssistant

T0 = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)
METRES_PER_DEGREE_LAT = 111195.0


def at(minutes: float) -> datetime:
    """Return T0 plus `minutes`."""
    return T0 + timedelta(minutes=minutes)


def track(counter_start: TrackCounters | None, kilometres: int = 10) -> TripLog:
    """Return a trip that drives one kilometre north per minute from T0, climbing 10 m per minute."""
    log = TripLog(T0, RunningStatsSettings())
    log.counter_start = counter_start
    for minute in range(kilometres + 1):
        log.add_position(at(minute), 50.0 + 1000 * minute / METRES_PER_DEGREE_LAT, 8.0, 10)
        log.add_altitude(at(minute), 100 + 10 * minute)
    return log


@pytest.mark.unit
def test_time_during_a_trip_uses_the_track() -> None:
    book = Logbook()
    spans = [TripSpan(T0, at(10), TrackCounters(50_000, 1000, 1000))]

    point = resolve_time(at(4.5), book, spans, track(spans[0].counter_start))

    assert point.counters.distance_m == pytest.approx(54_000, abs=1)
    assert point.counters.ascent_m == 1040
    assert point.trip_start == T0
    assert not point.estimated
    assert point.lat == pytest.approx(50.0 + 4000 / METRES_PER_DEGREE_LAT)


@pytest.mark.unit
def test_old_trip_without_start_counters_uses_the_trip_start_entry() -> None:
    book = Logbook()
    book.add(T0, Occasion.TRIP_START, odometer_km=34_000, trip_start=T0, distance_counter_m=20_000)
    spans = [TripSpan(T0, at(10))]

    point = resolve_time(at(3), book, spans, track(None))

    assert point.counters.distance_m == pytest.approx(23_000, abs=1)
    assert not point.estimated


@pytest.mark.unit
def test_parked_time_uses_the_counters_of_the_next_trip_or_the_current_ones() -> None:
    book = Logbook(closed_trips_m=90_000)
    spans = [TripSpan(T0, at(10), TrackCounters(50_000)), TripSpan(at(600), at(700), TrackCounters(60_000))]

    assert resolve_time(at(300), book, spans).counters == TrackCounters(60_000)
    assert resolve_time(at(800), book, spans).counters == TrackCounters(90_000)
    assert resolve_time(at(300), book, spans).trip_start is None


@pytest.mark.unit
def test_unknown_counters_are_interpolated_and_marked_as_estimated() -> None:
    book = Logbook()
    book.add(at(0), Occasion.MANUAL, odometer_km=34_000, distance_counter_m=10_000)
    book.add(at(100), Occasion.MANUAL, odometer_km=34_100, distance_counter_m=110_000)
    spans = [TripSpan(at(10), at(90))]

    point = resolve_time(at(25), book, spans)

    assert point.estimated
    assert point.counters.distance_m == pytest.approx(35_000)
    assert point.trip_start == at(10)
    assert resolve_time(at(200), Logbook(), [TripSpan(at(150), None)]).estimated


@pytest.mark.unit
def test_an_entry_being_moved_is_no_neighbour_for_interpolating() -> None:
    book = Logbook()
    book.add(at(0), Occasion.MANUAL, odometer_km=34_000, distance_counter_m=10_000)
    moved = book.add(at(20), Occasion.MANUAL, odometer_km=34_090, distance_counter_m=100_000)
    book.add(at(100), Occasion.MANUAL, odometer_km=34_100, distance_counter_m=110_000)
    spans = [TripSpan(at(10), at(90))]

    assert resolve_time(at(50), book, spans).counters.distance_m == pytest.approx(103_750)
    assert resolve_time(at(50), book, spans, exclude=moved.id).counters.distance_m == pytest.approx(60_000)


@pytest.mark.unit
def test_service_time_is_matched_to_a_stop_close_by() -> None:
    book = Logbook()
    book.record_stop(RecordedStop(T0, at(30), 30_000, end=at(32)))
    book.record_stop(RecordedStop(T0, at(60), 60_000, end=at(90)))

    assert matching_stop(book, at(35), at(200)) == book.stops[0]
    assert matching_stop(book, at(75), at(200)) == book.stops[1]
    assert matching_stop(book, at(45), at(200)) is None


@pytest.mark.unit
def test_entry_for_finds_the_entry_of_a_stop_or_an_earlier_late_entry() -> None:
    book = Logbook()
    stop = RecordedStop(T0, at(30), 30_000)
    halt = book.add(at(36), Occasion.STOP, odometer_km=34_030, stop_start=at(30))
    late = book.add(at(50), Occasion.LATE, odometer_km=34_050)

    assert entry_for(book, stop_point(stop)) == halt
    assert entry_for(book, LatePoint(at(50), TrackCounters(0))) == late
    assert entry_for(book, LatePoint(at(51), TrackCounters(0))) is None


async def test_late_refill_completes_the_stop_entry_and_restores_the_form(hass: HomeAssistant, tmp_path: Path) -> None:
    keeper = LogbookKeeper(hass, "x", 90, tmp_path)
    book = keeper.logbook
    book.add(T0, Occasion.TRIP_START, odometer_km=34_000, fuel_percent=50, trip_start=T0, distance_counter_m=0)
    book.add(at(40), Occasion.STOP, odometer_km=34_040, trip_start=T0, stop_start=at(30), distance_counter_m=40_000)
    book.set_running_trip(60_000)
    keeper.announce(Occasion.STOP, at(60), trip_start=T0, stop_start=at(55))
    keeper.set_field(FormField.FUEL, 33)
    stop = RecordedStop(T0, at(30), 40_000, place="Irschenberg")

    keeper.select_late(stop_point(stop))
    assert keeper.draft.odometer_km == 34_040
    keeper.set_field(FormField.FUEL_LITRES, 40)
    keeper.set_field(FormField.FUEL_AMOUNT, 70)
    entry = await keeper.async_save_late()

    assert len(book.entries) == 2
    assert entry.occasion is Occasion.STOP
    assert (entry.fuel, entry.fuel_percent) == (Refill(40, 70), 100)
    assert keeper.late is None
    assert keeper.pending is not None
    assert keeper.draft.fuel_percent == 33
    assert (tmp_path / "fahrtenbuch.csv").exists()


async def test_late_entry_for_a_short_stop_carries_the_odometer_forward(hass: HomeAssistant, tmp_path: Path) -> None:
    keeper = LogbookKeeper(hass, "x", 90, tmp_path)
    book = keeper.logbook
    book.add(T0, Occasion.TRIP_START, odometer_km=34_000, fuel_percent=50, trip_start=T0, distance_counter_m=0)
    book.add(at(120), Occasion.STOP, odometer_km=34_100, fuel_percent=100, fuel=Refill(50), distance_counter_m=100_000)
    book.set_running_trip(150_000)

    keeper.select_late(stop_point(RecordedStop(T0, at(20), 20_000, place="Tankstelle")))
    assert keeper.draft.odometer_km == 34_020
    keeper.set_field(FormField.FUEL_LITRES, 9)
    entry = await keeper.async_save_late()

    assert entry.occasion is Occasion.LATE
    assert (entry.time, entry.odometer_km, entry.place, entry.distance_counter_m) == (
        at(20),
        34_020,
        "Tankstelle",
        20_000,
    )
    assert not entry.odometer_corrected
    assert [e.time for e in book.entries] == [T0, at(20), at(120)]
    assert book.average_consumption() == pytest.approx(50 / 80 * 100)


async def test_service_late_entry_fills_the_tanks_and_keeps_the_odometer(hass: HomeAssistant, tmp_path: Path) -> None:
    keeper = LogbookKeeper(hass, "x", 90, tmp_path)
    book = keeper.logbook
    book.add(T0, Occasion.TRIP_START, odometer_km=34_000, distance_counter_m=0)
    point = LatePoint(at(30), TrackCounters(30_000), trip_start=T0)

    entry = await keeper.async_add_late(point, gas=Refill(20, 25))
    again = await keeper.async_add_late(point, odometer_km=34_031, fuel=Refill(40))

    assert entry.odometer_km == 34_030
    assert (entry.gas1_percent, entry.gas2_percent) == (100, 100)
    assert again.id == entry.id
    assert (again.odometer_km, again.fuel, again.gas, again.fuel_percent) == (34_031, Refill(40), Refill(20, 25), 100)
    assert again.odometer_corrected


async def test_discard_while_a_late_entry_is_chosen_returns_to_the_current_form(
    hass: HomeAssistant, hass_storage: dict[str, Any], tmp_path: Path
) -> None:
    keeper = LogbookKeeper(hass, "x", 90, tmp_path)
    keeper.set_field(FormField.ODOMETER, 34_500)
    keeper.select_late(LatePoint(at(30), TrackCounters(0)))
    keeper.set_field(FormField.FUEL_LITRES, 40)

    await keeper.async_save_now()
    assert hass_storage["reiseverlauftracker.x.logbook"]["data"]["draft"]["odometer_km"] == 34_500
    keeper.discard()

    assert keeper.late is None
    assert (keeper.draft.odometer_km, keeper.draft.fuel_litres) == (34_500, 0)
