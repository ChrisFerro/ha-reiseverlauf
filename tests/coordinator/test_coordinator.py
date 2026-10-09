"""Tests for the coordinator that drives trip detection from Home Assistant states."""

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events, async_fire_time_changed

from custom_components.reiseverlauftracker.const import EVENT_TRIP_STARTED
from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
from custom_components.reiseverlauftracker.coordinator.models import TripStatus
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

DPLUS = "sensor.camper_dplus"
TRACKER = "device_tracker.camper_gps"
SPEED = "sensor.camper_speed"
ALTITUDE = "sensor.camper_altitude"
METRES_PER_DEGREE_LAT = 111195.0


def coordinator_of(entry: MockConfigEntry) -> ReiseverlaufDataUpdateCoordinator:
    """Return the coordinator of a loaded entry."""
    return entry.runtime_data.coordinator


def set_position(hass: HomeAssistant, metres_north: float, accuracy: float = 10) -> None:
    """Move the tracker `metres_north` of the start point."""
    hass.states.async_set(
        TRACKER,
        "not_home",
        {"latitude": 50.0 + metres_north / METRES_PER_DEGREE_LAT, "longitude": 8.0, "gps_accuracy": accuracy},
    )


async def advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    """Move the clock forward and run the timers that became due."""
    freezer.tick(delta)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


@pytest.fixture
async def ready(hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory) -> MockConfigEntry:
    """Set up the integration with D+ off and the vehicle parked."""
    hass.states.async_set(DPLUS, "OFF")
    set_position(hass, 0)
    hass.states.async_set(SPEED, "0")
    hass.states.async_set(ALTITUDE, "100.0")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def drive(hass: HomeAssistant, freezer: FrozenDateTimeFactory, metres: float) -> None:
    """Switch D+ on, drive `metres` north in four steps and switch D+ off again."""
    hass.states.async_set(DPLUS, "ON")
    for step in range(1, 5):
        await advance(hass, freezer, timedelta(minutes=1))
        hass.states.async_set(SPEED, str(60 + step))
        set_position(hass, metres * step / 4)
    await advance(hass, freezer, timedelta(minutes=1))
    hass.states.async_set(DPLUS, "OFF")
    await hass.async_block_till_done()


async def test_idle_after_setup(hass: HomeAssistant, ready: MockConfigEntry) -> None:
    assert coordinator_of(ready).data.status is TripStatus.READY


async def test_dplus_on_starts_trip_and_fires_event(
    hass: HomeAssistant, ready: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    events = async_capture_events(hass, EVENT_TRIP_STARTED)

    hass.states.async_set(DPLUS, "ON")
    await hass.async_block_till_done()

    data = coordinator_of(ready).data
    assert data.status is TripStatus.DRIVING
    assert data.trip_start is not None
    assert len(events) == 1
    assert events[0].data == {
        "entry_id": ready.entry_id,
        "start": data.trip_start.isoformat(),
        "resumed": False,
        "startort": "Startort",
    }
    assert data.start_place == "Startort"


async def test_full_trip_runs_through_pause_and_merge_window(
    hass: HomeAssistant, ready: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    coordinator = coordinator_of(ready)
    await drive(hass, freezer, 4000)

    data = coordinator.data
    assert data.status is TripStatus.PAUSED
    assert data.distance_km == pytest.approx(4.0, rel=1e-3)
    assert data.driving_time == timedelta(minutes=4)
    assert data.expected_end == dt_util.utcnow() + timedelta(minutes=60)
    assert coordinator.log is not None
    assert [v for _, v in coordinator.log.speed] == [0, 61, 62, 63, 64]
    assert [v for _, v in coordinator.log.altitude] == [100.0]

    await advance(hass, freezer, timedelta(minutes=60))
    assert coordinator.data.status is TripStatus.MERGEABLE
    assert coordinator.data.merge_until is not None

    await advance(hass, freezer, timedelta(hours=6))
    assert coordinator.data.status is TripStatus.READY
    assert coordinator.log is None


async def test_unavailable_dplus_is_not_off(
    hass: HomeAssistant, ready: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set(DPLUS, "ON")
    await hass.async_block_till_done()
    hass.states.async_set(DPLUS, "unavailable")
    await hass.async_block_till_done()

    assert coordinator_of(ready).data.status is TripStatus.DRIVING


async def test_inaccurate_position_does_not_resume_ended_trip(
    hass: HomeAssistant, ready: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    await drive(hass, freezer, 4000)
    await advance(hass, freezer, timedelta(minutes=60))

    set_position(hass, 9000, accuracy=500)
    await hass.async_block_till_done()

    assert coordinator_of(ready).data.status is TripStatus.MERGEABLE


async def test_manual_start_and_end(
    hass: HomeAssistant, ready: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    coordinator = coordinator_of(ready)

    coordinator.async_start_trip()
    assert coordinator.data.status is TripStatus.PAUSED

    await advance(hass, freezer, timedelta(minutes=5))
    set_position(hass, 3000)
    await hass.async_block_till_done()
    coordinator.async_end_trip()
    assert coordinator.data.status is TripStatus.PROCESSING

    await hass.async_block_till_done()
    assert coordinator.data.status is TripStatus.MERGEABLE


async def test_trip_survives_restart(
    hass: HomeAssistant, ready: MockConfigEntry, freezer: FrozenDateTimeFactory, hass_storage: dict[str, Any]
) -> None:
    hass.states.async_set(DPLUS, "ON")
    await advance(hass, freezer, timedelta(minutes=1))
    set_position(hass, 2000)
    await hass.async_block_till_done()
    start = coordinator_of(ready).data.trip_start

    assert await hass.config_entries.async_unload(ready.entry_id)
    assert f"reiseverlauftracker.{ready.entry_id}.detector" in hass_storage
    assert f"reiseverlauftracker.{ready.entry_id}.trip_log" in hass_storage

    hass.states.async_set(DPLUS, "unavailable")
    await hass.config_entries.async_setup(ready.entry_id)
    await hass.async_block_till_done()

    coordinator = coordinator_of(ready)
    assert coordinator.data.status is TripStatus.DRIVING
    assert coordinator.data.trip_start == start
    assert coordinator.data.distance_km == pytest.approx(2.0, rel=1e-3)


async def test_restart_with_dplus_on_and_no_state_starts_at_last_changed(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set(DPLUS, "ON")
    switched_on = hass.states.get(DPLUS).last_changed
    await advance(hass, freezer, timedelta(minutes=30))

    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    data = coordinator_of(config_entry).data
    assert data.status is TripStatus.DRIVING
    assert data.trip_start == switched_on
