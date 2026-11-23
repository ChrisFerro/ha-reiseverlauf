"""Tests for changing and deleting stored logbook entries in the form, and for empty fields (Feat-11)."""

from datetime import UTC, datetime, timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reiseverlauftracker.const import CLEAR_CHOICE_NONE, DOMAIN, EDIT_CHOICE_NEW
from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
from custom_components.reiseverlauftracker.coordinator.edit_form import entries_between, entry_label
from custom_components.reiseverlauftracker.coordinator.logbook import Draft, FormField, Logbook, Occasion, Refill
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.components.datetime import ATTR_DATETIME, SERVICE_SET_VALUE as SET_DATETIME
from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.components.select import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

DPLUS = "sensor.camper_dplus"
TRACKER = "device_tracker.camper_gps"
SPEED = "sensor.camper_speed"
T0 = datetime(2026, 9, 27, 15, 30, tzinfo=UTC)


@pytest.fixture
async def loaded(hass: HomeAssistant, config_entry: MockConfigEntry) -> MockConfigEntry:
    """Set up the integration with D+ off and the vehicle parked."""
    hass.config.language = "de"
    hass.states.async_set(DPLUS, "OFF")
    hass.states.async_set(TRACKER, "not_home", {"latitude": 50.0, "longitude": 8.0, "gps_accuracy": 10})
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


async def call(hass: HomeAssistant, platform: Platform, service: str, target: str, **data: object) -> None:
    """Call an entity service and wait for it."""
    await hass.services.async_call(platform, service, {ATTR_ENTITY_ID: target, **data}, blocking=True)


async def choose(hass: HomeAssistant, entry: MockConfigEntry, text: str) -> str:
    """Choose the stored entry whose label contains `text` and return the label."""
    select = entity_id(hass, entry, Platform.SELECT, "logbook_edit")
    coordinator_of(entry).async_update_listeners()
    await hass.async_block_till_done()
    label = next(o for o in hass.states.get(select).attributes["options"] if text in o)
    await call(hass, Platform.SELECT, SERVICE_SELECT_OPTION, select, **{ATTR_OPTION: label})
    return label


def add_entries(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    """Store a halt with a refill and Gas 1 not read off, and a later manual entry."""
    book = coordinator.logbook.logbook
    now = dt_util.utcnow()
    book.add(
        now - timedelta(days=2),
        Occasion.STOP,
        odometer_km=33_768,
        fuel_percent=40,
        gas2_percent=80,
        fuel=Refill(50, 85.5),
        place="Irschenberg",
    )
    book.add(now - timedelta(days=1), Occasion.MANUAL, odometer_km=33_900, fuel_percent=90, place="Daheim")


@pytest.mark.unit
def test_label_shows_time_occasion_place_and_odometer() -> None:
    book = Logbook()
    entry = book.add(T0, Occasion.LATE, odometer_km=33_768, place="Irschenberg")
    tz = dt_util.get_time_zone("Europe/Berlin")
    assert tz is not None

    assert entry_label(entry, tz, "de", T0) == "27.09. 17:30 · Nachtrag · Irschenberg · 33768 km"
    assert (
        entry_label(entry, tz, "en", T0 + timedelta(days=400)) == "27.09.26 17:30 · Late entry · Irschenberg · 33768 km"
    )


@pytest.mark.unit
def test_a_trip_lists_its_entries_and_those_parked_after_it() -> None:
    book = Logbook()
    before = book.add(T0 - timedelta(hours=1), Occasion.MANUAL)
    start = book.add(T0, Occasion.TRIP_START, trip_start=T0)
    parked = book.add(T0 + timedelta(days=1), Occasion.LATE)
    book.add(T0 + timedelta(days=3), Occasion.TRIP_START, trip_start=T0 + timedelta(days=3))

    entries = entries_between(book, T0, T0 + timedelta(days=3), T0)

    assert entries == [parked, start]
    assert before not in entries


@pytest.mark.unit
def test_cleared_reading_is_not_read_off_and_cleared_litres_are_zero() -> None:
    draft = Draft(odometer_km=1000, fuel_percent=0, gas1_percent=50, fuel_litres=40)

    assert draft.not_read_off() == [FormField.GAS2]
    cleared = draft.cleared(FormField.GAS1).cleared(FormField.FUEL_LITRES)
    assert (cleared.gas1_percent, cleared.fuel_litres, cleared.fuel_percent) == (None, 0.0, 0)
    assert cleared.not_read_off() == [FormField.GAS1, FormField.GAS2]


async def test_entities_exist_with_german_entity_ids(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    select = entity_id(hass, loaded, Platform.SELECT, "logbook_edit")
    assert select.endswith("_fahrtenbuch_bearbeiten")
    assert entity_id(hass, loaded, Platform.SELECT, "logbook_clear").endswith("_fahrtenbuch_feld_leeren")
    assert entity_id(hass, loaded, Platform.BUTTON, "logbook_update").endswith("_fahrtenbuch_aendern")
    assert entity_id(hass, loaded, Platform.BUTTON, "logbook_remove").endswith("_fahrtenbuch_loeschen")
    assert hass.states.get(select).state == EDIT_CHOICE_NEW


async def test_choosing_an_entry_fills_the_form_and_changing_stores_it(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    coordinator = coordinator_of(loaded)
    add_entries(coordinator)
    keeper = coordinator.logbook

    label = await choose(hass, loaded, "Irschenberg")

    select = entity_id(hass, loaded, Platform.SELECT, "logbook_edit")
    assert hass.states.get(select).state == label
    assert hass.states.get(select).attributes["eintrag"]["ort"] == "Irschenberg"
    gas_1 = entity_id(hass, loaded, Platform.NUMBER, "logbook_gas_1")
    assert hass.states.get(gas_1).state == "unknown"
    sensor = hass.states.get("sensor.reiseverlauf_fahrtenbuch_eintrag") or next(
        s for s in hass.states.async_all("sensor") if s.entity_id.endswith("_fahrtenbuch_eintrag")
    )
    assert sensor.attributes["nicht_abgelesen"] == ["Gas 1"]
    assert float(hass.states.get(entity_id(hass, loaded, Platform.NUMBER, "logbook_fuel_amount")).state) == 85.5

    await call(hass, Platform.NUMBER, SERVICE_SET_VALUE, gas_1, **{ATTR_VALUE: 0})
    await call(hass, Platform.BUTTON, SERVICE_PRESS, entity_id(hass, loaded, Platform.BUTTON, "logbook_update"))

    changed = keeper.logbook.entries[0]
    assert (changed.gas1_percent, changed.fuel, changed.odometer_km) == (0, Refill(50, 85.5), 33_768)
    assert len(keeper.logbook.entries) == 2
    assert hass.states.get(select).state == EDIT_CHOICE_NEW
    # Without a pending occasion, the form follows the suggestion again.
    assert keeper.draft == Draft.from_suggestion(keeper.logbook.suggestion())


async def test_changing_the_time_moves_the_entry(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    coordinator = coordinator_of(loaded)
    add_entries(coordinator)
    await choose(hass, loaded, "Irschenberg")
    later = dt_util.as_local(dt_util.utcnow() - timedelta(hours=5)).replace(second=0, microsecond=0)

    await call(
        hass,
        Platform.DATETIME,
        SET_DATETIME,
        entity_id(hass, loaded, Platform.DATETIME, "logbook_late_time"),
        **{ATTR_DATETIME: later},
    )
    await call(hass, Platform.BUTTON, SERVICE_PRESS, entity_id(hass, loaded, Platform.BUTTON, "logbook_update"))

    entries = coordinator.logbook.logbook.entries
    assert entries[-1].place == "Irschenberg"
    assert entries[-1].time == dt_util.as_utc(later)
    assert coordinator.logbook.late is None


async def test_save_and_late_are_refused_while_an_entry_is_chosen(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    coordinator = coordinator_of(loaded)
    add_entries(coordinator)
    await choose(hass, loaded, "Daheim")

    for key in ("logbook_save", "logbook_late"):
        with pytest.raises(ServiceValidationError) as err:
            await call(hass, Platform.BUTTON, SERVICE_PRESS, entity_id(hass, loaded, Platform.BUTTON, key))
        assert err.value.translation_key == "logbook_editing"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "fahrtenbuch_speichern", {"config_entry_id": loaded.entry_id}, blocking=True, return_response=True
        )
    assert len(coordinator.logbook.logbook.entries) == 2

    await call(hass, Platform.BUTTON, SERVICE_PRESS, entity_id(hass, loaded, Platform.BUTTON, "logbook_discard"))
    assert coordinator.logbook.editing is None


async def test_deleting_removes_the_chosen_entry(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    coordinator = coordinator_of(loaded)
    add_entries(coordinator)
    remove = entity_id(hass, loaded, Platform.BUTTON, "logbook_remove")
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, Platform.BUTTON, SERVICE_PRESS, remove)
    assert err.value.translation_key == "no_entry_chosen"

    await choose(hass, loaded, "Daheim")
    await call(hass, Platform.BUTTON, SERVICE_PRESS, remove)

    assert [e.place for e in coordinator.logbook.logbook.entries] == ["Irschenberg"]
    assert coordinator.logbook.editing is None
    assert hass.states.get(entity_id(hass, loaded, Platform.SELECT, "logbook_edit")).state == EDIT_CHOICE_NEW


async def test_clear_field_empties_a_reading_and_rests_on_none(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    coordinator = coordinator_of(loaded)
    fuel = entity_id(hass, loaded, Platform.NUMBER, "logbook_fuel")
    await call(hass, Platform.NUMBER, SERVICE_SET_VALUE, fuel, **{ATTR_VALUE: 30})
    clear = entity_id(hass, loaded, Platform.SELECT, "logbook_clear")

    await call(hass, Platform.SELECT, SERVICE_SELECT_OPTION, clear, **{ATTR_OPTION: FormField.FUEL.value})

    assert coordinator.logbook.draft.fuel_percent is None
    assert hass.states.get(fuel).state == "unknown"
    assert hass.states.get(clear).state == CLEAR_CHOICE_NONE
