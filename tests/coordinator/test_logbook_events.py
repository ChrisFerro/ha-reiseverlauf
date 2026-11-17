"""Tests for logbook occasions, measured distance and storage in the coordinator."""

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events, async_fire_time_changed

from custom_components.reiseverlauftracker.const import EVENT_LOGBOOK
from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
from custom_components.reiseverlauftracker.coordinator.logbook import Occasion
from custom_components.reiseverlauftracker.coordinator.logbook_keeper import LogbookKeeper
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

DPLUS = "sensor.camper_dplus"
TRACKER = "device_tracker.camper_gps"
SPEED = "sensor.camper_speed"
METRES_PER_DEGREE_LAT = 111195.0
STORE_KEY = "reiseverlauftracker.{}.logbook"


def coordinator_of(entry: MockConfigEntry) -> ReiseverlaufDataUpdateCoordinator:
    """Return the coordinator of a loaded entry."""
    return entry.runtime_data.coordinator


def set_position(hass: HomeAssistant, metres_north: float) -> None:
    """Move the tracker `metres_north` of the start point."""
    hass.states.async_set(
        TRACKER,
        "not_home",
        {"latitude": 50.0 + metres_north / METRES_PER_DEGREE_LAT, "longitude": 8.0, "gps_accuracy": 10},
    )


async def advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    """Move the clock forward and run the timers that became due."""
    freezer.tick(delta)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def drive(hass: HomeAssistant, freezer: FrozenDateTimeFactory, metres: float) -> None:
    """Switch D+ on, drive `metres` north in four steps and switch D+ off again."""
    hass.states.async_set(DPLUS, "ON")
    for step in range(1, 5):
        await advance(hass, freezer, timedelta(minutes=1))
        set_position(hass, metres * step / 4)
    await advance(hass, freezer, timedelta(minutes=1))
    hass.states.async_set(DPLUS, "OFF")
    await hass.async_block_till_done()


@pytest.fixture
async def ready(hass: HomeAssistant, config_entry: MockConfigEntry) -> MockConfigEntry:
    """Set up the integration with D+ off and the vehicle parked."""
    hass.states.async_set(DPLUS, "OFF")
    set_position(hass, 0)
    hass.states.async_set(SPEED, "0")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def test_trip_start_announces_a_pending_entry(
    hass: HomeAssistant, ready: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    keeper = coordinator_of(ready).logbook
    keeper.logbook.add(dt_util.utcnow(), Occasion.MANUAL, odometer_km=34299, fuel_percent=60, gas1_percent=80)
    events = async_capture_events(hass, EVENT_LOGBOOK)

    hass.states.async_set(DPLUS, "ON")
    await hass.async_block_till_done()

    assert len(events) == 1
    data = events[0].data
    assert data["entry_id"] == ready.entry_id
    assert data["anlass"] == "reisestart"
    assert data["ort"] == "Startort"
    assert data["reise_start"] == coordinator_of(ready).data.trip_start.isoformat()
    assert data["halt_start"] is None
    assert data["vorschlag"] == {"kilometerstand": 34299, "kraftstoff": 60, "gas_1": 80, "gas_2": None}
    assert keeper.pending is not None
    assert keeper.pending.occasion is Occasion.TRIP_START


async def test_stop_is_announced_once_after_the_minimum_duration(
    hass: HomeAssistant, ready: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    keeper = coordinator_of(ready).logbook
    keeper.logbook.add(dt_util.utcnow(), Occasion.MANUAL, odometer_km=1000)
    events = async_capture_events(hass, EVENT_LOGBOOK)

    await drive(hass, freezer, 4000)
    await advance(hass, freezer, timedelta(minutes=4))
    assert [e.data["anlass"] for e in events] == ["reisestart"]

    await advance(hass, freezer, timedelta(minutes=2))
    assert [e.data["anlass"] for e in events] == ["reisestart", "halt"]
    stop = events[-1].data
    assert stop["ort"] == "Zielort"
    assert stop["halt_start"] is not None
    assert stop["vorschlag"]["kilometerstand"] == 1004

    # D+ briefly on without moving: the stop continues and is not announced again.
    hass.states.async_set(DPLUS, "ON")
    await advance(hass, freezer, timedelta(minutes=1))
    hass.states.async_set(DPLUS, "OFF")
    await advance(hass, freezer, timedelta(minutes=10))
    assert [e.data["anlass"] for e in events] == ["reisestart", "halt"]


async def test_short_stop_is_not_announced(
    hass: HomeAssistant, ready: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    events = async_capture_events(hass, EVENT_LOGBOOK)
    await drive(hass, freezer, 4000)
    await advance(hass, freezer, timedelta(minutes=2))

    hass.states.async_set(DPLUS, "ON")
    await advance(hass, freezer, timedelta(minutes=5))

    assert [e.data["anlass"] for e in events] == ["reisestart"]


async def test_measured_distance_is_kept_after_the_trip_closes(
    hass: HomeAssistant, ready: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    keeper = coordinator_of(ready).logbook
    await drive(hass, freezer, 4000)
    assert keeper.logbook.running_trip_m == pytest.approx(4000, rel=1e-3)

    await advance(hass, freezer, timedelta(hours=7))

    assert coordinator_of(ready).log is None
    assert keeper.logbook.running_trip_m == 0
    assert keeper.logbook.closed_trips_m == pytest.approx(4000, rel=1e-3)


async def test_logbook_survives_restart(
    hass: HomeAssistant, ready: MockConfigEntry, freezer: FrozenDateTimeFactory, hass_storage: dict[str, Any]
) -> None:
    keeper = coordinator_of(ready).logbook
    keeper.logbook.add(dt_util.utcnow(), Occasion.MANUAL, odometer_km=34299)
    hass.states.async_set(DPLUS, "ON")
    await advance(hass, freezer, timedelta(minutes=1))
    set_position(hass, 2000)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(ready.entry_id)
    assert STORE_KEY.format(ready.entry_id) in hass_storage

    await hass.config_entries.async_setup(ready.entry_id)
    await hass.async_block_till_done()

    keeper = coordinator_of(ready).logbook
    assert len(keeper.logbook.entries) == 1
    assert keeper.logbook.running_trip_m == pytest.approx(2000, rel=1e-3)
    assert keeper.pending is not None
    assert keeper.pending.occasion is Occasion.TRIP_START
    assert keeper.logbook.suggest_odometer() == 34301


async def test_unreadable_store_starts_empty(hass: HomeAssistant, hass_storage: dict[str, Any]) -> None:
    hass_storage[STORE_KEY.format("x")] = {"version": 1, "key": STORE_KEY.format("x"), "data": {"entries": [{}]}}
    keeper = LogbookKeeper(hass, "x", 90)

    await keeper.async_load()

    assert keeper.logbook.entries == []
    assert keeper.pending is None
