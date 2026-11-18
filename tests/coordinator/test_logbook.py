"""Tests for the logbook of odometer readings, tank levels and refills."""

from datetime import UTC, datetime, timedelta
import json

import pytest

from custom_components.reiseverlauftracker.coordinator.logbook import (
    Draft,
    FormField,
    Logbook,
    Occasion,
    Refill,
    Suggestion,
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 31, 8, 0, tzinfo=UTC)


def at(hours: float) -> datetime:
    """Return T0 plus `hours`."""
    return T0 + timedelta(hours=hours)


def drive(book: Logbook, km: float) -> None:
    """Measure a closed trip of `km`."""
    book.set_running_trip_distance(km * 1000)
    book.close_trip()


def test_distance_counter_adds_running_trip_to_closed_trips() -> None:
    book = Logbook()
    drive(book, 84.2)
    book.set_running_trip_distance(5000)
    book.set_running_trip_distance(4900)

    assert book.distance_counter_m == pytest.approx(89100)

    book.close_trip()
    assert book.closed_trips_m == pytest.approx(89100)
    assert book.running_trip_m == 0


def test_no_odometer_suggestion_before_the_first_reading() -> None:
    book = Logbook()
    drive(book, 10)

    assert book.suggest_odometer() is None
    assert book.suggestion().odometer_km is None


def test_odometer_is_carried_forward_by_the_measured_distance() -> None:
    book = Logbook()
    book.add(at(0), Occasion.TRIP_START, odometer_km=34299)
    book.set_running_trip_distance(84_200)

    assert book.suggest_odometer() == 34383


def test_odometer_counts_as_corrected_only_when_it_differs_from_the_suggestion() -> None:
    book = Logbook()
    first = book.add(at(0), Occasion.MANUAL, odometer_km=34299)
    drive(book, 84.2)
    confirmed = book.add(at(2), Occasion.STOP, odometer_km=34383)
    drive(book, 10)
    corrected = book.add(at(3), Occasion.STOP, odometer_km=34395)

    assert not first.odometer_corrected
    assert not confirmed.odometer_corrected
    assert corrected.odometer_corrected
    assert book.suggest_odometer() == 34395


def test_suggestion_keeps_the_last_gas_levels_and_fuel_without_consumption() -> None:
    book = Logbook()
    book.add(at(0), Occasion.STOP, odometer_km=1000, fuel_percent=80, gas1_percent=60, gas2_percent=90)
    book.add(at(1), Occasion.STOP, odometer_km=1050)
    drive(book, 100)

    suggestion = book.suggestion()

    assert suggestion.fuel_percent == 80
    assert suggestion.gas1_percent == 60
    assert suggestion.gas2_percent == 90


def full_tank(book: Logbook, hours: float, odometer: float, litres: float) -> None:
    book.add(at(hours), Occasion.STOP, odometer_km=odometer, fuel_percent=100, fuel=Refill(litres, litres * 1.7))


def test_average_consumption_needs_two_full_refills() -> None:
    book = Logbook()
    full_tank(book, 0, 1000, 50)

    assert book.average_consumption() is None

    full_tank(book, 10, 1500, 60)
    assert book.average_consumption() == pytest.approx(12.0)


def test_average_consumption_adds_partial_refills_to_the_next_full_one() -> None:
    book = Logbook()
    full_tank(book, 0, 1000, 50)
    book.add(at(5), Occasion.STOP, odometer_km=1300, fuel_percent=70, fuel=Refill(20, 34))
    full_tank(book, 10, 1500, 40)
    full_tank(book, 20, 2000, 50)

    assert book.average_consumption() == pytest.approx((60 + 50) / 1000 * 100)


def test_fuel_suggestion_subtracts_consumption_over_the_distance() -> None:
    book = Logbook(tank_litres=90)
    full_tank(book, 0, 1000, 50)
    full_tank(book, 10, 1500, 60)
    book.set_running_trip_distance(150_000)

    # 150 km at 12 l/100 km = 18 l = 20 % of 90 l
    assert book.suggest_fuel_percent() == 80


def test_fuel_suggestion_stays_within_the_tank() -> None:
    book = Logbook(tank_litres=90)
    full_tank(book, 0, 1000, 50)
    full_tank(book, 10, 1500, 60)
    drive(book, 2000)

    assert book.suggest_fuel_percent() == 0


def test_update_marks_a_changed_odometer_and_keeps_entries_sorted() -> None:
    book = Logbook()
    first = book.add(at(0), Occasion.STOP, odometer_km=1000)
    second = book.add(at(1), Occasion.STOP, odometer_km=1010)

    changed = book.update(first.id, odometer_km=1001, time=at(2))

    assert changed.odometer_corrected
    assert [e.id for e in book.entries] == [second.id, first.id]


def test_update_and_remove_reject_unknown_ids() -> None:
    book = Logbook()

    with pytest.raises(KeyError):
        book.update("missing", odometer_km=1)
    with pytest.raises(KeyError):
        book.remove("missing")


def test_remove_deletes_the_entry() -> None:
    book = Logbook()
    entry = book.add(at(0), Occasion.MANUAL, gas1_percent=50)

    book.remove(entry.id)

    assert book.entries == []


def test_cost_between_sums_fuel_and_gas() -> None:
    book = Logbook()
    book.add(at(0), Occasion.STOP, fuel=Refill(50, 85.5), gas=Refill(30, 30.0))
    book.add(at(24), Occasion.STOP, gas=Refill(10))
    book.add(at(48), Occasion.STOP, fuel=Refill(40, 70.0))

    assert book.cost_between(at(0), at(48)) == pytest.approx(115.5)


def test_trip_summary_collects_the_trip_including_its_arrival() -> None:
    book = Logbook()
    trip = at(0)
    book.add(at(-24), Occasion.STOP, odometer_km=34000, fuel=Refill(10, 17))
    book.add(trip, Occasion.TRIP_START, odometer_km=34299, trip_start=trip)
    book.set_running_trip_distance(40_000)
    book.add(at(1), Occasion.STOP, trip_start=trip, stop_start=at(1), fuel=Refill(55, 95.0), fuel_percent=100)
    book.set_running_trip_distance(84_200)
    book.add(at(3), Occasion.STOP, trip_start=trip, stop_start=at(3), gas=Refill(20, 19.8))

    summary = book.trip_summary(trip)

    assert summary.odometer_start_km == 34299
    assert summary.odometer_end_km == 34383
    assert summary.fuel_litres == 55
    assert summary.fuel_cost == pytest.approx(95.0)
    assert summary.gas_litres == 20
    assert summary.cost == pytest.approx(114.8)


def test_trip_summary_without_entries_has_no_start_odometer() -> None:
    summary = Logbook().trip_summary(T0)

    assert summary.odometer_start_km is None
    assert summary.odometer_end_km is None
    assert summary.cost == 0


def test_round_trip_through_json() -> None:
    book = Logbook(tank_litres=90)
    book.add(
        at(0),
        Occasion.STOP,
        odometer_km=34299,
        fuel_percent=100,
        gas1_percent=100,
        gas2_percent=100,
        fuel=Refill(55.3, 96.2),
        gas=Refill(28.4),
        trip_start=at(-1),
        stop_start=at(0),
        lat=50.1,
        lon=8.2,
        place="Tankstelle",
    )
    drive(book, 84.2)
    book.set_running_trip_distance(1000)

    restored = Logbook.from_dict(json.loads(json.dumps(book.as_dict())), tank_litres=80)

    assert restored.entries == book.entries
    assert restored.distance_counter_m == book.distance_counter_m
    assert restored.running_trip_m == 1000
    assert restored.tank_litres == 80


def test_draft_starts_from_the_suggestion_without_refills() -> None:
    draft = Draft.from_suggestion(Suggestion(odometer_km=1000, fuel_percent=40, gas1_percent=50, gas2_percent=60))

    assert draft.value(FormField.ODOMETER) == 1000
    assert draft.fuel is None
    assert draft.gas is None


def test_draft_fills_the_tanks_on_a_new_refill_only() -> None:
    draft = Draft(fuel_percent=20, gas1_percent=10, gas2_percent=30)

    draft = draft.with_value(FormField.FUEL_LITRES, 60).with_value(FormField.GAS_LITRES, 25)
    assert (draft.fuel_percent, draft.gas1_percent, draft.gas2_percent) == (100, 100, 100)

    draft = draft.with_value(FormField.FUEL, 90).with_value(FormField.FUEL_LITRES, 61)
    assert draft.fuel_percent == 90
    assert draft.fuel == Refill(61, None)


def test_draft_round_trip_through_json() -> None:
    draft = Draft(odometer_km=5, fuel_litres=1.5, gas_amount=2)

    assert Draft.from_dict(json.loads(json.dumps(draft.as_dict()))) == draft


def test_entry_saved_later_keeps_the_counter_of_its_occasion() -> None:
    book = Logbook()
    book.add(at(0), Occasion.MANUAL, odometer_km=1000)
    book.set_running_trip_distance(2000)
    occasion_counter = book.distance_counter_m
    book.set_running_trip_distance(30_000)

    entry = book.add(at(1), Occasion.TRIP_START, odometer_km=1002, distance_counter_m=occasion_counter)

    assert not entry.odometer_corrected
    assert book.suggest_odometer() == 1030
