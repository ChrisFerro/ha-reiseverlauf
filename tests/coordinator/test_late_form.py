"""Tests for choosing an earlier time in the logbook form and its counters from the track."""

from datetime import datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.reiseverlauftracker.const import DOMAIN, LATE_CHOICE_CURRENT, LATE_CHOICE_OTHER
from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
from custom_components.reiseverlauftracker.coordinator.late_entry import LatePoint
from custom_components.reiseverlauftracker.coordinator.logbook import FormField, Occasion, Refill
from custom_components.reiseverlauftracker.coordinator.trip_log import TrackCounters
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

DPLUS = "sensor.camper_dplus"
TRACKER = "device_tracker.camper_gps"
SPEED = "sensor.camper_speed"
ALTITUDE = "sensor.camper_altitude"
METRES_PER_DEGREE_LAT = 111195.0


def set_position(hass: HomeAssistant, metres_north: float) -> None:
    """Move the tracker `metres_north` of the start point."""
    hass.states.async_set(
        TRACKER,
        "not_home",
        {"latitude": 50.0 + metres_north / METRES_PER_DEGREE_LAT, "longitude": 8.0, "gps_accuracy": 10},
    )


async def advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    """Move the clock forward and run the timers and tasks that became due."""
    freezer.tick(delta)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> ReiseverlaufDataUpdateCoordinator:
    """Set up the integration with the vehicle parked and D+ off."""
    hass.states.async_set(DPLUS, "OFF")
    set_position(hass, 0)
    hass.states.async_set(SPEED, "0")
    hass.states.async_set(ALTITUDE, "100.0")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data.coordinator


async def drive(hass: HomeAssistant, freezer: FrozenDateTimeFactory, start_m: float, metres: float) -> None:
    """Drive `metres` north from `start_m` in ten one-minute steps with D+ on, then switch D+ off."""
    hass.states.async_set(DPLUS, "ON")
    for step in range(1, 11):
        await advance(hass, freezer, timedelta(minutes=1))
        hass.states.async_set(SPEED, str(50 + step))
        set_position(hass, start_m + metres * step / 10)
    await advance(hass, freezer, timedelta(minutes=1))
    hass.states.async_set(SPEED, "0")
    hass.states.async_set(DPLUS, "OFF")
    await hass.async_block_till_done()


async def test_short_stop_of_a_past_trip_can_be_chosen_and_saved(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    hass.config.language = "de"
    coordinator = await setup(hass, config_entry)
    keeper, form = coordinator.logbook, coordinator.late_form
    keeper.logbook.add(dt_util.utcnow(), Occasion.MANUAL, odometer_km=34_000, fuel_percent=60)
    await drive(hass, freezer, 0, 5000)
    await advance(hass, freezer, timedelta(minutes=2))
    await drive(hass, freezer, 5000, 5000)
    await advance(hass, freezer, timedelta(hours=8))
    await advance(hass, freezer, timedelta(seconds=5))
    assert coordinator.log is None

    options = form.options()
    assert options[0] == LATE_CHOICE_CURRENT
    assert options[-1] == LATE_CHOICE_OTHER
    short = next(o for o in options if o.endswith("· kurz"))
    assert "Zielort" in short
    select_id = er.async_get(hass).async_get_entity_id("select", DOMAIN, f"{config_entry.entry_id}_logbook_time")
    assert select_id is not None
    select = hass.states.get(select_id)
    assert select is not None
    assert short in select.attributes["options"]
    await form.async_select(short)
    assert form.current_option() == short
    assert keeper.draft.odometer_km == 34_005
    keeper.set_field(FormField.FUEL_LITRES, 40)
    keeper.set_field(FormField.FUEL_AMOUNT, 70)
    entry = await coordinator.async_save_logbook_form()

    assert entry.occasion is Occasion.LATE
    assert (entry.odometer_km, entry.fuel, entry.place) == (34_005, Refill(40, 70), "Zielort")
    assert form.current_option() == LATE_CHOICE_CURRENT
    assert keeper.logbook.suggest_odometer() == 34_010


async def test_free_time_of_a_past_trip_takes_the_counters_from_the_raw_data(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    coordinator = await setup(hass, config_entry)
    keeper, form = coordinator.logbook, coordinator.late_form
    keeper.logbook.add(dt_util.utcnow(), Occasion.MANUAL, odometer_km=34_000)
    await drive(hass, freezer, 0, 10_000)
    assert coordinator.log is not None
    trip_start = coordinator.log.start
    await advance(hass, freezer, timedelta(hours=8))
    assert coordinator.log is None

    point = await form.async_point_at(trip_start + timedelta(minutes=5, seconds=30))

    assert not point.estimated
    assert point.trip_start == trip_start
    assert point.counters.distance_m == pytest.approx(5000, abs=1)
    assert point.place == "Zielort"
    await form.async_set_time(trip_start + timedelta(minutes=5, seconds=30))
    await form.async_select(LATE_CHOICE_OTHER)
    assert form.current_option() == LATE_CHOICE_OTHER
    assert keeper.draft.odometer_km == 34_005


async def test_service_refill_while_parked_keeps_the_counters_and_needs_an_odometer_if_estimated(
    hass: HomeAssistant, config_entry: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinator = await setup(hass, config_entry)
    form = coordinator.late_form
    before = dt_util.utcnow() - timedelta(days=3)
    coordinator.logbook.logbook.add(before, Occasion.MANUAL, odometer_km=34_000, distance_counter_m=0)

    entry = await form.async_add(before + timedelta(days=1), fuel=Refill(40))
    assert (entry.odometer_km, entry.fuel_percent, entry.occasion) == (34_000, 100, Occasion.LATE)

    async def estimated(time: datetime) -> LatePoint:
        return LatePoint(time, TrackCounters(0), estimated=True)

    monkeypatch.setattr(form, "async_point_at", estimated)
    with pytest.raises(ValueError, match="odometer"):
        await form.async_add(before + timedelta(days=2), fuel=Refill(40))
    entry = await form.async_add(before + timedelta(days=2), odometer_km=34_050, fuel=Refill(40))
    assert entry.odometer_km == 34_050
