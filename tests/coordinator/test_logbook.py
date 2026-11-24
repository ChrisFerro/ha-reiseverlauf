"""Tests for the logbook of odometer readings, tank levels and refills."""

from datetime import UTC, date, datetime, timedelta
import json
from zoneinfo import ZoneInfo

import pytest

from custom_components.reiseverlauftracker.coordinator.logbook import (
    CostCategory,
    Draft,
    FormField,
    Logbook,
    Occasion,
    RecordedStop,
    Refill,
    Suggestion,
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 31, 8, 0, tzinfo=UTC)
BERLIN = ZoneInfo("Europe/Berlin")


def at(hours: float) -> datetime:
    """Return T0 plus `hours`."""
    return T0 + timedelta(hours=hours)


def drive(book: Logbook, km: float) -> None:
    """Measure a closed trip of `km`."""
    book.set_running_trip(km * 1000)
    book.close_trip()


def test_distance_counter_adds_running_trip_to_closed_trips() -> None:
    book = Logbook()
    drive(book, 84.2)
    book.set_running_trip(5000)
    book.set_running_trip(4900)

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
    book.set_running_trip(84_200)

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
    book.set_running_trip(150_000)

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
    book.set_running_trip(40_000)
    book.add(at(1), Occasion.STOP, trip_start=trip, stop_start=at(1), fuel=Refill(55, 95.0), fuel_percent=100)
    book.set_running_trip(84_200)
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
    book.set_running_trip(1000)

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
    book.set_running_trip(2000)
    occasion_counter = book.distance_counter_m
    book.set_running_trip(30_000)

    entry = book.add(at(1), Occasion.TRIP_START, odometer_km=1002, distance_counter_m=occasion_counter)

    assert not entry.odometer_corrected
    assert book.suggest_odometer() == 1030


def test_entries_keep_the_elevation_counters_of_their_occasion() -> None:
    book = Logbook()
    book.set_running_trip(10_000, 120, 80)
    book.close_trip()
    book.set_running_trip(5000, 30, 10)

    assert (book.ascent_counter_m, book.descent_counter_m) == (pytest.approx(150), pytest.approx(90))
    entry = book.add(at(0), Occasion.STOP)
    later = book.add(at(1), Occasion.STOP, ascent_counter_m=140, descent_counter_m=85)
    assert (entry.ascent_counter_m, entry.descent_counter_m) == (150, 90)
    assert (later.ascent_counter_m, later.descent_counter_m) == (140, 85)

    restored = Logbook.from_dict(json.loads(json.dumps(book.as_dict())), 90)
    assert (restored.ascent_counter_m, restored.descent_counter_m) == (pytest.approx(150), pytest.approx(90))
    assert restored.get(entry.id).descent_counter_m == 90


def test_entries_stored_before_the_elevation_counters_load_without_them() -> None:
    book = Logbook()
    book.add(at(0), Occasion.STOP, fuel_percent=50)
    data = book.as_dict()
    for key in ("closed_trips_ascent_m", "running_trip_ascent_m", "closed_trips_descent_m", "running_trip_descent_m"):
        del data[key]
    del data["entries"][0]["ascent_counter_m"]
    del data["entries"][0]["descent_counter_m"]

    restored = Logbook.from_dict(data, 90)

    assert (restored.ascent_counter_m, restored.descent_counter_m) == (0, 0)
    assert restored.entries[0].ascent_counter_m is None
    assert restored.entries[0].descent_counter_m is None


def park(book: Logbook, arrival_h: float, departure_h: float, levels: tuple[float, float], km: float = 50) -> None:
    """Drive `km`, arrive with the first level and start the next trip with the second."""
    drive(book, km)
    book.add(at(arrival_h), Occasion.STOP, fuel_percent=levels[0])
    book.add(at(departure_h), Occasion.TRIP_START, fuel_percent=levels[1])


def test_no_parked_consumption_without_a_parked_period() -> None:
    book = Logbook()
    book.add(at(0), Occasion.TRIP_START, fuel_percent=80)
    drive(book, 50)
    book.add(at(2), Occasion.STOP, fuel_percent=70)

    assert book.parked_consumption() is None


def test_parked_consumption_sums_all_parked_periods() -> None:
    book = Logbook(tank_litres=90)
    park(book, 0, 48, (80, 75))
    park(book, 50, 98, (70, 70))
    park(book, 100, 148, (65, 70))  # read too high once, which the other readings balance

    parked = book.parked_consumption()

    assert parked is not None
    assert parked.periods == 3
    assert parked.days == pytest.approx(6)
    assert parked.litres == pytest.approx(0)
    assert parked.litres_per_day == pytest.approx(0)
    park(book, 150, 198, (70, 60))
    assert book.parked_consumption().litres_per_day == pytest.approx(9 / 8)


def test_parked_consumption_is_never_negative() -> None:
    book = Logbook()
    park(book, 0, 24, (60, 65))

    assert book.parked_consumption().litres_per_day == 0


def test_parked_periods_with_refills_or_driving_are_left_out() -> None:
    book = Logbook()
    drive(book, 50)
    book.add(at(0), Occasion.STOP, fuel_percent=40)
    book.add(at(10), Occasion.MANUAL, fuel=Refill(50))  # a refill without a level read
    book.add(at(24), Occasion.TRIP_START, fuel_percent=100)  # refill in between: not counted
    drive(book, 5)
    book.add(at(48), Occasion.TRIP_START, fuel_percent=90)  # a trip without entries in between
    book.add(at(72), Occasion.TRIP_START, fuel=Refill(10), fuel_percent=100)  # refill at the start

    assert book.parked_consumption() is None


def test_a_refill_at_the_last_stop_starts_the_parked_period() -> None:
    book = Logbook(tank_litres=90)
    drive(book, 50)
    book.add(at(0), Occasion.STOP, fuel=Refill(60), fuel_percent=100)
    book.add(at(24), Occasion.TRIP_START, fuel_percent=95)

    parked = book.parked_consumption()

    assert parked.periods == 1
    assert parked.litres_per_day == pytest.approx(4.5)


# --- Late entries (docs/features/feat-09-nachtraege.md 6.2) ---


def test_late_entry_builds_on_the_readings_before_its_time() -> None:
    book = Logbook()
    book.add(at(0), Occasion.TRIP_START, odometer_km=34299, fuel_percent=60, gas1_percent=80, gas2_percent=70)
    drive(book, 40)
    stop_counter = book.distance_counter_m
    drive(book, 60)
    book.add(at(5), Occasion.STOP, odometer_km=34399, fuel_percent=30, gas1_percent=50, gas2_percent=40)

    suggestion = book.suggestion(stop_counter, until=at(2))
    assert suggestion.odometer_km == 34339
    assert suggestion.fuel_percent == 60
    assert (suggestion.gas1_percent, suggestion.gas2_percent) == (80, 70)
    # Without a time the latest reading counts, as before.
    assert book.suggest_odometer() == 34399


def test_late_entry_counts_as_corrected_only_against_the_reading_before_it() -> None:
    book = Logbook()
    book.add(at(0), Occasion.TRIP_START, odometer_km=34299)
    drive(book, 40)
    stop_counter = book.distance_counter_m
    drive(book, 60)
    book.add(at(5), Occasion.STOP, odometer_km=34399)

    late = book.add(at(2), Occasion.LATE, odometer_km=34339, distance_counter_m=stop_counter, fuel=Refill(50, 90))

    assert not late.odometer_corrected
    assert [e.occasion for e in book.entries] == [Occasion.TRIP_START, Occasion.LATE, Occasion.STOP]


def test_late_refill_closes_a_consumption_interval() -> None:
    book = Logbook()
    book.add(at(0), Occasion.STOP, odometer_km=34000, fuel_percent=100, fuel=Refill(40, 70))
    book.add(at(10), Occasion.STOP, odometer_km=34500, fuel_percent=60)
    assert book.average_consumption() is None

    book.add(at(5), Occasion.LATE, odometer_km=34400, fuel_percent=100, fuel=Refill(44, 80))

    assert book.average_consumption() == pytest.approx(11.0)


# --- Travel costs (docs/features/feat-09-nachtraege.md 6.3, feat-10-tour.md 5.4) ---


def test_travel_costs_count_on_their_day_by_category() -> None:
    book = Logbook()
    book.add(datetime(2026, 10, 15, 9, 0, tzinfo=UTC), Occasion.STOP, fuel=Refill(50, 90), gas=Refill(20, 25))
    trip = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)
    book.add_travel_cost(date(2026, 10, 14), CostCategory.TOLL, 23.4, trip_start=trip, country="at")
    book.add_travel_cost(date(2026, 10, 31), CostCategory.TOLL, 61.1, trip_start=trip, country="IT")
    book.add_travel_cost(date(2026, 11, 1), CostCategory.PITCH, 30.0, note="Camping Seeblick")

    october = book.costs_between(datetime(2026, 10, 1, tzinfo=BERLIN), datetime(2026, 11, 1, tzinfo=BERLIN))

    assert (october.fuel, october.gas) == (90, 25)
    assert october.travel == {CostCategory.TOLL: pytest.approx(84.5)}
    assert october.total == pytest.approx(199.5)
    assert book.costs_between(datetime(2026, 11, 1, tzinfo=BERLIN), datetime(2026, 12, 1, tzinfo=BERLIN)).travel == {
        CostCategory.PITCH: 30.0
    }


def test_travel_cost_country_is_normalised_and_checked() -> None:
    book = Logbook()

    cost = book.add_travel_cost(date(2026, 10, 14), CostCategory.TOLL, 10, country=" at ", note="")

    assert (cost.country, cost.note) == ("AT", None)
    with pytest.raises(ValueError, match="country"):
        book.add_travel_cost(date(2026, 10, 14), CostCategory.TOLL, 10, country="AUT")
    with pytest.raises(ValueError, match="amount"):
        book.add_travel_cost(date(2026, 10, 14), CostCategory.TOLL, 0)


def test_travel_costs_can_be_changed_and_removed() -> None:
    book = Logbook()
    cost = book.add_travel_cost(date(2026, 10, 14), CostCategory.TOLL, 10, country="AT")

    changed = book.update_travel_cost(cost.id, amount=12.5, day=date(2026, 10, 15))

    assert (changed.id, changed.amount, changed.day) == (cost.id, 12.5, date(2026, 10, 15))
    assert book.travel_costs == [changed]
    with pytest.raises(ValueError, match="amount"):
        book.update_travel_cost(cost.id, amount=-1)
    book.remove_travel_cost(cost.id)
    assert book.travel_costs == []
    with pytest.raises(KeyError):
        book.remove_travel_cost(cost.id)
    with pytest.raises(KeyError):
        book.update_travel_cost(cost.id, amount=1)


def test_toll_is_settled_by_a_toll_cost_or_the_no_toll_mark() -> None:
    book = Logbook()
    trip, other = at(0), at(48)
    book.add_travel_cost(date(2026, 10, 31), CostCategory.FERRY, 85, trip_start=trip)
    assert not book.toll_settled(trip)

    book.add_travel_cost(date(2026, 10, 31), CostCategory.TOLL, 20, trip_start=trip, country="FR")
    book.set_no_toll(other, True)

    assert book.toll_settled(trip)
    assert book.toll_settled(other)
    book.set_no_toll(other, False)
    assert not book.toll_settled(other)
    assert [c.category for c in book.travel_costs_of_trip(trip)] == [CostCategory.FERRY, CostCategory.TOLL]


def test_travel_costs_and_no_toll_marks_survive_a_round_trip() -> None:
    book = Logbook()
    book.add_travel_cost(date(2026, 10, 14), CostCategory.TOLL, 23.4, trip_start=at(0), country="AT", recorded=at(1))
    book.set_no_toll(at(48), True)

    restored = Logbook.from_dict(json.loads(json.dumps(book.as_dict())), tank_litres=90)

    assert restored.travel_costs == book.travel_costs
    assert restored.no_toll_trips == {at(48)}


def test_logbooks_without_travel_costs_still_load() -> None:
    restored = Logbook.from_dict({"version": 1, "entries": []}, tank_litres=90)

    assert (restored.travel_costs, restored.no_toll_trips) == ([], set())


def stop(trip: datetime, start: datetime, counter_m: float, **kwargs: object) -> RecordedStop:
    """Return a stop of `trip` that began at `start`."""
    return RecordedStop(trip_start=trip, start=start, distance_counter_m=counter_m, **kwargs)  # type: ignore[arg-type]


def test_recorded_stop_update_keeps_counters_and_position_of_its_beginning() -> None:
    book = Logbook()
    book.record_stop(stop(T0, at(1), 5000, ascent_counter_m=10, lat=50.0, lon=8.0))
    book.record_stop(stop(T0, at(1), 5200, end=at(1.05), lat=50.1, lon=8.1))

    assert book.stops == [stop(T0, at(1), 5000, ascent_counter_m=10, end=at(1.05), lat=50.0, lon=8.0)]
    book.set_stop_place(at(1), "Irschenberg")
    book.record_stop(stop(T0, at(1), 5200, end=at(1.5)))
    assert (book.stops[0].place, book.stops[0].end) == ("Irschenberg", at(1.5))


def test_stops_are_short_until_they_reach_the_minimum_duration() -> None:
    open_stop = stop(T0, at(1), 0)
    minimum = timedelta(minutes=5)

    assert open_stop.is_short(minimum, at(1) + timedelta(minutes=4))
    assert not open_stop.is_short(minimum, at(1) + timedelta(minutes=5))
    assert stop(T0, at(1), 0, end=at(1) + timedelta(minutes=2)).is_short(minimum, at(5))


def test_recent_stops_and_stops_of_a_trip() -> None:
    book = Logbook()
    other = at(48)
    for hour in (3, 1, 2):
        book.record_stop(stop(T0, at(hour), hour * 1000))
    book.record_stop(stop(other, at(49), 9000))

    assert [s.start for s in book.recent_stops(2)] == [at(49), at(3)]
    assert [s.start for s in book.stops_of_trip(T0)] == [at(1), at(2), at(3)]


def test_old_stops_are_pruned_but_entries_stay() -> None:
    book = Logbook()
    book.add(at(0), Occasion.TRIP_START, odometer_km=34299)
    book.record_stop(stop(T0, at(1), 0))
    book.record_stop(stop(T0, at(24 * 100), 0))

    assert not book.prune_stops(at(24 * 120))
    assert book.prune_stops(at(24 * 121 + 2))
    assert [s.start for s in book.stops] == [at(24 * 100)]
    assert len(book.entries) == 1


def test_stops_survive_a_round_trip_and_old_data_has_none() -> None:
    book = Logbook()
    book.record_stop(stop(T0, at(1), 5000, ascent_counter_m=1, descent_counter_m=2, end=at(2), place="Rasthof"))

    restored = Logbook.from_dict(json.loads(json.dumps(book.as_dict())), 90)

    assert restored.stops == book.stops
    old = book.as_dict()
    del old["stops"]
    assert Logbook.from_dict(old, 90).stops == []


def test_summary_of_an_earlier_trip_ends_at_its_own_counter() -> None:
    book = Logbook()
    trip = at(0)
    book.add(trip, Occasion.TRIP_START, odometer_km=34_000, trip_start=trip, distance_counter_m=0)
    drive(book, 84)
    next_trip = at(24)
    book.add(next_trip, Occasion.TRIP_START, odometer_km=34_090, trip_start=next_trip, distance_counter_m=84_000)
    drive(book, 100)

    summary = book.trip_summary(trip, end_counter_m=84_000, until=next_trip - timedelta(seconds=1))

    assert (summary.odometer_start_km, summary.odometer_end_km) == (34_000, 34_084)
    assert book.trip_summary(trip).odometer_end_km == 34_190


def test_average_consumption_until_a_time_leaves_out_later_refills() -> None:
    book = Logbook()
    full_tank(book, 0, 1000, 50)
    full_tank(book, 10, 1500, 60)
    full_tank(book, 20, 2000, 100)

    assert book.average_consumption(until=at(15)) == pytest.approx(12.0)
    assert book.average_consumption() == pytest.approx(16.0)


def test_travel_costs_by_category_in_category_order() -> None:
    book = Logbook()
    book.add_travel_cost(date(2026, 10, 31), CostCategory.FERRY, 85, trip_start=T0)
    book.add_travel_cost(date(2026, 10, 31), CostCategory.TOLL, 23.4, trip_start=T0, country="AT")
    book.add_travel_cost(date(2026, 10, 31), CostCategory.TOLL, 59.9, trip_start=T0, country="IT")
    book.add_travel_cost(date(2026, 11, 2), CostCategory.PITCH, 18)

    assert book.travel_costs_by_category(T0) == {CostCategory.TOLL: pytest.approx(83.3), CostCategory.FERRY: 85}


def test_gas_level_litres_per_percent_and_last_price() -> None:
    book = Logbook()
    book.add(at(0), Occasion.MANUAL, gas1_percent=60, gas2_percent=40)
    book.add(at(1), Occasion.STOP, fuel=Refill(50, 90.0), fuel_percent=100)
    book.add(at(2), Occasion.STOP, gas=Refill(25, 24.0), gas1_percent=100, gas2_percent=100)
    book.add(at(3), Occasion.STOP, fuel=Refill(10))
    # No reading before this gas stop counts any more than the full tanks: it filled nothing new.
    book.add(at(4), Occasion.STOP, gas=Refill(5, 5.0), gas1_percent=100, gas2_percent=100)

    assert book.gas_level_at(at(-1)) is None
    assert book.gas_level_at(at(1.5)) == 100
    assert book.gas_level_at(at(2)) == 200
    assert book.gas_litres_per_percent() == pytest.approx(0.25)
    assert book.last_price("fuel", at(5)) == pytest.approx(1.8)
    assert book.last_price("gas", at(3)) == pytest.approx(0.96)
    assert book.last_price("fuel", at(0.5)) is None


def test_counters_after_a_ferry_move_with_its_distance() -> None:
    book = Logbook()
    before = book.add(at(0), Occasion.TRIP_START, odometer_km=1000)
    drive(book, 30)
    book.record_stop(RecordedStop(trip_start=at(0), start=at(1), distance_counter_m=10_000))
    after = book.add(at(2), Occasion.MANUAL, odometer_km=1030)

    book.shift_counters(10_000, -18_000, -5, 0, closed_trip=True)

    assert book.get(before.id) == before
    moved = book.get(after.id)
    assert moved is not None
    assert moved.distance_counter_m == 12_000
    assert moved.odometer_km == 1030
    assert book.stops[0].distance_counter_m == 10_000
    assert book.distance_counter_m == 12_000


def test_counters_never_fall_below_the_ferry() -> None:
    book = Logbook()
    entry = book.add(at(0), Occasion.STOP, distance_counter_m=10_500)

    book.shift_counters(10_000, -2000, 0, 0, closed_trip=False)

    moved = book.get(entry.id)
    assert moved is not None
    assert moved.distance_counter_m == 10_000


def test_ferry_mark_of_a_stop_is_stored() -> None:
    book = Logbook()
    book.record_stop(RecordedStop(trip_start=at(0), start=at(1), distance_counter_m=0))

    book.set_stop_ferry(at(1), True)

    restored = Logbook.from_dict(json.loads(json.dumps(book.as_dict())), 90)
    assert restored.stops[0].ferry
