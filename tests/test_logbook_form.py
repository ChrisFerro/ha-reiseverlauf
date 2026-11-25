"""Tests for the logbook form entities, the logbook actions and the CSV file."""

from datetime import timedelta
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.reiseverlauftracker.const import DOMAIN
from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
from custom_components.reiseverlauftracker.coordinator.logbook import Occasion
from custom_components.reiseverlauftracker.sensor.logbook import STATE_PENDING
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

DPLUS = "sensor.camper_dplus"
TRACKER = "device_tracker.camper_gps"
SPEED = "sensor.camper_speed"
METRES_PER_DEGREE_LAT = 111195.0


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


@pytest.fixture
async def loaded(hass: HomeAssistant, config_entry: MockConfigEntry) -> MockConfigEntry:
    """Set up the integration with D+ off and the vehicle parked."""
    hass.states.async_set(DPLUS, "OFF")
    set_position(hass, 0)
    hass.states.async_set(SPEED, "0")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


def coordinator_of(entry: MockConfigEntry) -> ReiseverlaufDataUpdateCoordinator:
    """Return the coordinator of a loaded entry."""
    return entry.runtime_data.coordinator


def entity_id(hass: HomeAssistant, entry: MockConfigEntry, platform: Platform, key: str) -> str:
    """Return the entity ID of the entity with the given description key."""
    found = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
    assert found is not None
    return found


async def set_field(hass: HomeAssistant, entry: MockConfigEntry, key: str, value: float) -> None:
    """Set one number of the form."""
    await hass.services.async_call(
        Platform.NUMBER,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id(hass, entry, Platform.NUMBER, key), ATTR_VALUE: value},
        blocking=True,
    )


async def press(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> None:
    """Press a button of the form."""
    await hass.services.async_call(
        Platform.BUTTON, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id(hass, entry, Platform.BUTTON, key)}, blocking=True
    )
    await hass.async_block_till_done()


def number_value(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> float | None:
    """Return the value of one number of the form, or None while it is unknown."""
    state = hass.states.get(entity_id(hass, entry, Platform.NUMBER, key))
    assert state is not None
    return None if state.state == "unknown" else float(state.state)


def csv_lines(media_dir: Path) -> list[str]:
    """Return the lines of the logbook CSV file."""
    return (media_dir / "reiseverlauf" / "fahrtenbuch.csv").read_text(encoding="utf-8-sig").splitlines()


async def test_manual_entry_through_the_form(hass: HomeAssistant, loaded: MockConfigEntry, media_dir: Path) -> None:
    status = entity_id(hass, loaded, Platform.SENSOR, "logbook_entry")
    assert hass.states.get(status).state == "gespeichert"
    assert number_value(hass, loaded, "logbook_odometer") is None

    await set_field(hass, loaded, "logbook_odometer", 34299)
    await set_field(hass, loaded, "logbook_fuel", 60)
    await set_field(hass, loaded, "logbook_gas_1", 80)
    await press(hass, loaded, "logbook_save")

    entries = coordinator_of(loaded).logbook.logbook.entries
    assert len(entries) == 1
    entry = entries[0]
    assert entry.occasion is Occasion.MANUAL
    assert (entry.odometer_km, entry.fuel_percent, entry.gas1_percent, entry.gas2_percent) == (34299, 60, 80, None)
    assert entry.place == "Startort"
    assert entry.trip_start is None
    attributes = hass.states.get(status).attributes
    assert attributes["letzte_eintraege"][0]["kilometerstand"] == 34299
    assert number_value(hass, loaded, "logbook_odometer") == 34299.0
    assert len(csv_lines(media_dir)) == 2


async def test_trip_start_prefills_and_saves_for_the_occasion(
    hass: HomeAssistant, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    keeper = coordinator_of(loaded).logbook
    keeper.logbook.add(dt_util.utcnow(), Occasion.MANUAL, odometer_km=1000, fuel_percent=50, gas1_percent=40)
    keeper.discard()

    hass.states.async_set(DPLUS, "ON")
    await advance(hass, freezer, timedelta(minutes=1))
    set_position(hass, 2000)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id(hass, loaded, Platform.SENSOR, "logbook_entry")).state == STATE_PENDING
    assert number_value(hass, loaded, "logbook_odometer") == 1000.0
    assert number_value(hass, loaded, "logbook_fuel") == 50.0

    await set_field(hass, loaded, "logbook_fuel", 45)
    await press(hass, loaded, "logbook_save")

    entry = keeper.logbook.entries[-1]
    assert entry.occasion is Occasion.TRIP_START
    assert entry.trip_start == coordinator_of(loaded).data.trip_start
    assert entry.fuel_percent == 45
    assert keeper.pending is None
    assert number_value(hass, loaded, "logbook_odometer") == 1002.0


async def test_refill_litres_fill_the_tanks(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    await set_field(hass, loaded, "logbook_fuel", 20)
    await set_field(hass, loaded, "logbook_fuel_litres", 70.5)
    await set_field(hass, loaded, "logbook_fuel_amount", 123.4)
    await set_field(hass, loaded, "logbook_gas_litres", 30)

    assert number_value(hass, loaded, "logbook_fuel") == 100.0
    assert number_value(hass, loaded, "logbook_gas_1") == 100.0
    assert number_value(hass, loaded, "logbook_gas_2") == 100.0

    # A corrected level stays when the litres are changed again.
    await set_field(hass, loaded, "logbook_fuel", 95)
    await set_field(hass, loaded, "logbook_fuel_litres", 71)
    assert number_value(hass, loaded, "logbook_fuel") == 95.0

    await press(hass, loaded, "logbook_save")
    entry = coordinator_of(loaded).logbook.logbook.entries[0]
    assert entry.fuel is not None
    assert (entry.fuel.litres, entry.fuel.amount) == (71, 123.4)
    assert entry.gas is not None
    assert (entry.gas.litres, entry.gas.amount) == (30, None)
    assert number_value(hass, loaded, "logbook_fuel_litres") == 0.0


async def test_discard_resets_the_form(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    await set_field(hass, loaded, "logbook_odometer", 500)

    await press(hass, loaded, "logbook_discard")

    assert number_value(hass, loaded, "logbook_odometer") is None
    assert coordinator_of(loaded).logbook.logbook.entries == []


async def call(hass: HomeAssistant, service: str, data: dict, *, response: bool = True) -> dict | None:
    """Call a logbook action and return its response."""
    return await hass.services.async_call(DOMAIN, service, data, blocking=True, return_response=response)


async def test_actions_add_change_and_delete(hass: HomeAssistant, loaded: MockConfigEntry, media_dir: Path) -> None:
    base = {"config_entry_id": loaded.entry_id}
    added = await call(hass, "fahrtenbuch_eintragen", {**base, "kilometerstand": 34299, "diesel_liter": 50})
    assert added is not None
    entry = added["eintrag"]
    assert entry["kilometerstand"] == 34299
    assert entry["diesel_liter"] == 50
    assert entry["ort"] == "Startort"

    changed = await call(
        hass, "fahrtenbuch_aendern", {**base, "eintrag": entry["id"], "diesel_betrag": 85.5, "gas_1": 70}
    )
    assert changed is not None
    assert changed["eintrag"]["diesel_liter"] == 50
    assert changed["eintrag"]["diesel_betrag"] == 85.5
    assert changed["eintrag"]["gas_1"] == 70

    removed = await call(hass, "fahrtenbuch_aendern", {**base, "eintrag": entry["id"], "diesel_liter": 0})
    assert removed is not None
    assert removed["eintrag"]["diesel_liter"] is None

    await call(hass, "fahrtenbuch_loeschen", {**base, "eintrag": entry["id"]}, response=False)
    assert coordinator_of(loaded).logbook.logbook.entries == []
    assert len(csv_lines(media_dir)) == 1


async def test_added_entry_defaults_to_the_carried_forward_odometer(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    base = {"config_entry_id": loaded.entry_id}
    await call(hass, "fahrtenbuch_eintragen", {**base, "kilometerstand": 1000})
    coordinator_of(loaded).logbook.set_running_trip(12_400)

    added = await call(hass, "fahrtenbuch_eintragen", {**base, "gas_liter": 25, "gas_betrag": 24})

    assert added is not None
    assert added["eintrag"]["kilometerstand"] == 1012


async def test_actions_reject_unknown_entries_and_lone_amounts(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    base = {"config_entry_id": loaded.entry_id}
    with pytest.raises(ServiceValidationError):
        await call(hass, "fahrtenbuch_aendern", {**base, "eintrag": "missing", "gas_1": 1})
    with pytest.raises(ServiceValidationError):
        await call(hass, "fahrtenbuch_loeschen", {**base, "eintrag": "missing"}, response=False)
    with pytest.raises(ServiceValidationError):
        await call(hass, "fahrtenbuch_eintragen", {**base, "diesel_betrag": 50})


async def test_save_action_only_saves_the_named_occasion(
    hass: HomeAssistant, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    base = {"config_entry_id": loaded.entry_id}
    keeper = coordinator_of(loaded).logbook
    hass.states.async_set(DPLUS, "ON")
    await advance(hass, freezer, timedelta(minutes=1))
    pending = keeper.pending
    assert pending is not None
    occasion_time = pending.time.isoformat()

    with pytest.raises(ServiceValidationError):
        await call(hass, "fahrtenbuch_speichern", {**base, "anlass_zeit": "2020-01-01T00:00:00+00:00"})
    assert keeper.logbook.entries == []

    saved = await call(hass, "fahrtenbuch_speichern", {**base, "anlass_zeit": occasion_time})
    assert saved is not None
    assert saved["eintrag"]["anlass"] == Occasion.TRIP_START.value
    assert keeper.pending is None

    # A second tap on the same notification must not add a manual entry.
    with pytest.raises(ServiceValidationError):
        await call(hass, "fahrtenbuch_speichern", {**base, "anlass_zeit": occasion_time})
    assert len(keeper.logbook.entries) == 1

    manual = await call(hass, "fahrtenbuch_speichern", base)
    assert manual is not None
    assert manual["eintrag"]["anlass"] == Occasion.MANUAL.value


async def test_csv_action_writes_the_file(hass: HomeAssistant, loaded: MockConfigEntry, media_dir: Path) -> None:
    response = await call(hass, "fahrtenbuch_csv", {"config_entry_id": loaded.entry_id})

    assert response == {
        "pfad": str(media_dir / "reiseverlauf" / "fahrtenbuch.csv"),
        "url": "/media/local/reiseverlauf/fahrtenbuch.csv",
        "eintraege": 0,
    }
    assert len(csv_lines(media_dir)) == 1


def sensor_value(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> float | None:
    """Return the value of a logbook sensor, or None while it is unknown."""
    state = hass.states.get(entity_id(hass, entry, Platform.SENSOR, key))
    assert state is not None
    return None if state.state == "unknown" else float(state.state)


async def test_evaluation_sensors(hass: HomeAssistant, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to("2026-11-17 12:00:00+00:00")
    base = {"config_entry_id": loaded.entry_id}
    assert sensor_value(hass, loaded, "odometer") is None
    assert sensor_value(hass, loaded, "travel_costs_month") == 0

    last_year = {"zeit": "2025-12-30 10:00:00", "diesel_liter": 30, "diesel_betrag": 50}
    await call(hass, "fahrtenbuch_eintragen", {**base, **last_year, "kilometerstand": 1000, "kraftstoff": 100})
    october = {"zeit": "2026-10-05 10:00:00", "gas_liter": 20, "gas_betrag": 19}
    await call(hass, "fahrtenbuch_eintragen", {**base, **october, "gas_1": 100, "gas_2": 100})
    november = {"diesel_liter": 60, "diesel_betrag": 102.5, "kraftstoff": 100, "kilometerstand": 1500}
    await call(hass, "fahrtenbuch_eintragen", {**base, **november})
    coordinator_of(loaded).logbook.set_running_trip(25_000)
    coordinator_of(loaded).async_update_listeners()
    await hass.async_block_till_done()

    assert sensor_value(hass, loaded, "odometer") == 1525
    assert sensor_value(hass, loaded, "fuel_level") == 100
    assert sensor_value(hass, loaded, "gas_1_level") == 100
    assert sensor_value(hass, loaded, "average_consumption") == 12.0
    assert sensor_value(hass, loaded, "travel_costs_month") == 102.5
    assert sensor_value(hass, loaded, "travel_costs_year") == 121.5
    state = hass.states.get(entity_id(hass, loaded, Platform.SENSOR, "travel_costs_year"))
    assert state is not None
    assert state.attributes["unit_of_measurement"] == hass.config.currency
