"""Tests for ferry crossings: detected at the end of a stop, or marked by hand (Feat-12 6.2, 6.3)."""

from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_capture_events, async_fire_time_changed

from custom_components.reiseverlauftracker.const import DOMAIN, EVENT_TRIP_ENDED, LATE_CHOICE_CURRENT
from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator, ferries
from custom_components.reiseverlauftracker.coordinator.logbook import Occasion
from custom_components.reiseverlauftracker.coordinator.trip_log import FerryMark
from custom_components.reiseverlauftracker.export import ExportFile
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
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
    await hass.async_block_till_done(wait_background_tasks=True)


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
    """Drive `metres` north from `start_m` with D+ on, then switch D+ off."""
    hass.states.async_set(DPLUS, "ON")
    for step in range(1, 11):
        await advance(hass, freezer, timedelta(minutes=1))
        hass.states.async_set(SPEED, str(50 + step))
        hass.states.async_set(ALTITUDE, str(100 + 10 * step))
        set_position(hass, start_m + metres * step / 10)
    await advance(hass, freezer, timedelta(minutes=1))
    hass.states.async_set(SPEED, "0")
    hass.states.async_set(DPLUS, "OFF")
    await hass.async_block_till_done()


@pytest.fixture(autouse=True)
def no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the pause before asking Nominatim."""
    monkeypatch.setattr(ferries, "NOMINATIM_INTERVAL_S", 0)


async def cross(hass: HomeAssistant, freezer: FrozenDateTimeFactory, start_m: float, metres: float) -> None:
    """Stand with D+ off long enough for a stop, then move `metres` north with D+ still off, as on a ferry."""
    await advance(hass, freezer, timedelta(minutes=6))
    for step in range(1, 11):
        await advance(hass, freezer, timedelta(minutes=3))
        hass.states.async_set(SPEED, "20")
        set_position(hass, start_m + metres * step / 10)
    await advance(hass, freezer, timedelta(minutes=3))
    hass.states.async_set(SPEED, "0")
    await hass.async_block_till_done()


MARK_FERRY = "button.camper_gps_als_faehre_markieren"
# The steps onto and off the ship belong to the crossing: 1 km on, 9 km on board, 0.5 km off.
DRIVEN_KM = 9.5
FERRY_KM = 10.5


async def trip_with_crossing(
    hass: HomeAssistant, entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> ReiseverlaufDataUpdateCoordinator:
    """Drive 5 km, cross 10 km on a ferry, drive 5 km more and let the trip end."""
    coordinator = await setup(hass, entry)
    await drive(hass, freezer, 0, 5000)
    await cross(hass, freezer, 5000, 10_000)
    await drive(hass, freezer, 15_000, 5000)
    await advance(hass, freezer, timedelta(minutes=60))
    return coordinator


async def test_crossing_on_water_is_a_ferry_and_not_driven(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    on_water: AsyncMock,
    media_dir: Path,
) -> None:
    hass.config.language = "de"
    on_water.return_value = True
    events = async_capture_events(hass, EVENT_TRIP_ENDED)

    coordinator = await trip_with_crossing(hass, config_entry, freezer)

    on_water.assert_awaited_once()
    info = coordinator.data.last_export
    assert info is not None
    assert info.distance_km == pytest.approx(DRIVEN_KM, abs=0.1)
    assert info.ferry_km == pytest.approx(FERRY_KM, abs=0.1)
    assert info.ferry_time == timedelta(minutes=39)
    [stop] = info.stops
    assert stop.ferry
    assert "Fähre:" in info.stats_text
    data = events[0].data
    assert data["strecke_km"] == pytest.approx(DRIVEN_KM, abs=0.1)
    assert data["faehre_km"] == pytest.approx(FERRY_KM, abs=0.1)
    assert data["faehre_min"] == 39
    assert data["halte"][0]["faehre"] is True
    # The logbook counts only what was driven.
    assert coordinator.logbook.logbook.distance_counter_m == pytest.approx(DRIVEN_KM * 1000, abs=100)
    stored = json.loads((media_dir / "reiseverlauf" / info.folder / "export.json").read_text(encoding="utf-8"))
    assert stored["stops"][0]["ferry"] is True
    assert stored["ferry_km"] == pytest.approx(FERRY_KM, abs=0.1)
    assert coordinator.logbook.logbook.stops[0].ferry


async def test_stop_on_land_is_no_ferry(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory, on_water: AsyncMock
) -> None:
    coordinator = await trip_with_crossing(hass, config_entry, freezer)

    on_water.assert_awaited_once()
    info = coordinator.data.last_export
    assert info is not None
    assert info.distance_km == pytest.approx(20.0, rel=0.02)
    assert info.ferry_km == 0
    assert not info.stops[0].ferry


async def test_stop_without_movement_is_not_checked(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory, on_water: AsyncMock
) -> None:
    await setup(hass, config_entry)
    await drive(hass, freezer, 0, 5000)
    await advance(hass, freezer, timedelta(minutes=10))
    await drive(hass, freezer, 5000, 5000)

    on_water.assert_not_awaited()


async def test_ferry_marked_by_hand_renews_the_export_and_moves_later_counters(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory, media_dir: Path
) -> None:
    coordinator = await trip_with_crossing(hass, config_entry, freezer)
    info = coordinator.data.last_export
    assert info is not None
    book = coordinator.logbook.logbook
    after = book.add(dt_util.utcnow(), Occasion.MANUAL, odometer_km=34320)
    assert after.distance_counter_m == pytest.approx(20_000, rel=0.02)
    stop = info.stops[0]
    # The log of the trip is gone; the raw data of the export are used.
    await advance(hass, freezer, timedelta(hours=7))
    assert coordinator.log is None

    response = await hass.services.async_call(
        DOMAIN,
        "faehre_markieren",
        {"config_entry_id": config_entry.entry_id, "halt": stop.start + timedelta(minutes=1)},
        blocking=True,
        return_response=True,
    )

    assert response is not None
    assert response["faehre"] is True
    assert response["strecke_km_aenderung"] == pytest.approx(-FERRY_KM, abs=0.1)
    renewed = next(i for i in coordinator.exports if i.folder == info.folder)
    assert renewed.distance_km == pytest.approx(DRIVEN_KM, abs=0.1)
    assert renewed.ferry_km == pytest.approx(FERRY_KM, abs=0.1)
    assert renewed.stops[0].ferry
    raw = json.loads((media_dir / "reiseverlauf" / info.folder / info.files[ExportFile.RAW]).read_text())
    assert raw["stops"][0]["ferry"] == FerryMark.HAND
    moved = book.get(after.id)
    assert moved is not None
    assert moved.distance_counter_m == pytest.approx(DRIVEN_KM * 1000, abs=100)
    assert moved.odometer_km == 34320
    assert book.distance_counter_m == pytest.approx(DRIVEN_KM * 1000, abs=100)

    await hass.services.async_call(
        DOMAIN,
        "faehre_markieren",
        {"config_entry_id": config_entry.entry_id, "halt": stop.start, "faehre": False},
        blocking=True,
    )

    renewed = next(i for i in coordinator.exports if i.folder == info.folder)
    assert renewed.distance_km == pytest.approx(20.0, rel=0.02)
    assert not renewed.stops[0].ferry
    moved = book.get(after.id)
    assert moved is not None
    assert moved.distance_counter_m == pytest.approx(after.distance_counter_m)


async def test_unknown_stop_is_refused(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    coordinator = await trip_with_crossing(hass, config_entry, freezer)
    info = coordinator.data.last_export
    assert info is not None

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "faehre_markieren",
            {"config_entry_id": config_entry.entry_id, "halt": info.start + timedelta(minutes=2)},
            blocking=True,
        )

    assert err.value.translation_key == "unknown_stop"


async def test_button_marks_the_chosen_stop_of_the_running_trip(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    hass.config.language = "de"
    coordinator = await setup(hass, config_entry)
    await drive(hass, freezer, 0, 5000)
    await cross(hass, freezer, 5000, 10_000)
    hass.states.async_set(DPLUS, "ON")
    await advance(hass, freezer, timedelta(minutes=1))
    log = coordinator.log
    assert log is not None
    assert log.distance_m == pytest.approx(15_000, rel=0.02)
    form = coordinator.late_form
    label = next(o for o in form.options() if o != LATE_CHOICE_CURRENT and "Zielort" in o)
    await form.async_select(label)

    await hass.services.async_call("button", "press", {"entity_id": MARK_FERRY}, blocking=True)

    assert log.distance_m == pytest.approx(5000, rel=0.02)
    assert log.stops[0].ferry is FerryMark.HAND
    assert form.current_option().endswith("· Fähre")
    assert coordinator.data.stops[0].is_ferry
    assert coordinator.logbook.logbook.distance_counter_m == pytest.approx(5000, rel=0.02)

    await hass.services.async_call("button", "press", {"entity_id": MARK_FERRY}, blocking=True)

    assert log.stops[0].ferry is FerryMark.NONE
    assert log.distance_m == pytest.approx(15_000, rel=0.02)
