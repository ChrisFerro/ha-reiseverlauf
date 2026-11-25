"""Tests for the late-entry entities of the logbook form and the fahrtenbuch_nachtragen action."""

from datetime import timedelta
from pathlib import Path

import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.reiseverlauftracker.const import DOMAIN, LATE_CHOICE_CURRENT, LATE_CHOICE_OTHER
from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
from custom_components.reiseverlauftracker.coordinator.logbook import Occasion, RecordedStop, Refill
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


def remember_stops(coordinator: ReiseverlaufDataUpdateCoordinator) -> tuple[RecordedStop, RecordedStop]:
    """Remember one halt and one short stop of a trip that started three hours ago, with an odometer entry."""
    book = coordinator.logbook.logbook
    trip = dt_util.utcnow() - timedelta(hours=3)
    book.add(trip, Occasion.TRIP_START, odometer_km=34_000, fuel_percent=50, trip_start=trip, distance_counter_m=0)
    halt = book.record_stop(
        RecordedStop(trip, trip + timedelta(hours=1), 60_000, end=trip + timedelta(hours=1, minutes=30), place="Rast")
    )
    short = book.record_stop(
        RecordedStop(trip, trip + timedelta(hours=2), 120_000, end=trip + timedelta(hours=2, minutes=3), place="Tanke")
    )
    book.set_running_trip(150_000)
    book.close_trip()
    return halt, short


async def test_entities_exist_with_german_entity_ids(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    select = entity_id(hass, loaded, Platform.SELECT, "logbook_time")
    assert select.endswith("_fahrtenbuch_zeitpunkt")
    assert entity_id(hass, loaded, Platform.DATETIME, "logbook_late_time").endswith("_fahrtenbuch_nachtrag_zeit")
    assert entity_id(hass, loaded, Platform.BUTTON, "logbook_late").endswith("_fahrtenbuch_nachtragen")
    state = hass.states.get(select)
    assert state is not None
    assert state.state == LATE_CHOICE_CURRENT
    assert state.attributes["options"] == [LATE_CHOICE_CURRENT, LATE_CHOICE_OTHER]


async def test_short_stop_is_chosen_filled_in_and_saved(
    hass: HomeAssistant, loaded: MockConfigEntry, media_dir: Path
) -> None:
    coordinator = coordinator_of(loaded)
    _, short = remember_stops(coordinator)
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    select = entity_id(hass, loaded, Platform.SELECT, "logbook_time")
    options = hass.states.get(select).attributes["options"]
    label = next(o for o in options if "Tanke" in o)
    assert label.endswith("· Tanke · kurz")
    assert options.index(label) == 1

    await call(hass, Platform.SELECT, SERVICE_SELECT_OPTION, select, **{ATTR_OPTION: label})
    odometer = entity_id(hass, loaded, Platform.NUMBER, "logbook_odometer")
    assert float(hass.states.get(odometer).state) == 34_120
    assert hass.states.get(select).attributes["ort"] == "Tanke"
    litres = entity_id(hass, loaded, Platform.NUMBER, "logbook_fuel_litres")
    await call(hass, Platform.NUMBER, SERVICE_SET_VALUE, litres, **{ATTR_VALUE: 45})
    await call(hass, Platform.BUTTON, SERVICE_PRESS, entity_id(hass, loaded, Platform.BUTTON, "logbook_late"))

    entry = coordinator.logbook.logbook.entries[-1]
    assert (entry.occasion, entry.time, entry.odometer_km, entry.fuel) == (
        Occasion.LATE,
        short.start,
        34_120,
        Refill(45),
    )
    assert hass.states.get(select).state == LATE_CHOICE_CURRENT
    assert (media_dir / "reiseverlauf" / "fahrtenbuch.csv").exists()


async def test_other_time_follows_the_datetime_entity(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    coordinator = coordinator_of(loaded)
    remember_stops(coordinator)
    select = entity_id(hass, loaded, Platform.SELECT, "logbook_time")
    when = dt_util.as_local(dt_util.utcnow() - timedelta(days=1)).replace(second=0, microsecond=0)

    await call(
        hass,
        Platform.DATETIME,
        SET_DATETIME,
        entity_id(hass, loaded, Platform.DATETIME, "logbook_late_time"),
        **{ATTR_DATETIME: when},
    )
    await call(hass, Platform.SELECT, SERVICE_SELECT_OPTION, select, **{ATTR_OPTION: LATE_CHOICE_OTHER})

    late = coordinator.logbook.late
    assert late is not None
    assert late.time == dt_util.as_utc(when)
    assert hass.states.get(select).state == LATE_CHOICE_OTHER
    assert hass.states.get(select).attributes["geschaetzt"] is False


async def test_late_button_without_an_earlier_time_is_rejected(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, Platform.BUTTON, SERVICE_PRESS, entity_id(hass, loaded, Platform.BUTTON, "logbook_late"))

    assert err.value.translation_key == "no_late_time"


async def test_action_matches_the_halt_and_completes_its_entry(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    coordinator = coordinator_of(loaded)
    halt, _ = remember_stops(coordinator)
    book = coordinator.logbook.logbook
    book.add(halt.start + timedelta(minutes=6), Occasion.STOP, odometer_km=34_061, stop_start=halt.start)

    response = await hass.services.async_call(
        DOMAIN,
        "fahrtenbuch_nachtragen",
        {
            "config_entry_id": loaded.entry_id,
            "zeit": (halt.start + timedelta(minutes=20)).isoformat(),
            "diesel_liter": 60,
            "diesel_betrag": 102.5,
        },
        blocking=True,
        return_response=True,
    )

    assert len(book.entries) == 2
    assert response is not None
    assert response["eintrag"]["kilometerstand"] == 34_061
    assert (response["eintrag"]["diesel_liter"], response["eintrag"]["kraftstoff"]) == (60, 100)
    assert response["eintrag"]["anlass"] == "halt"


async def test_action_needs_litres(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "fahrtenbuch_nachtragen",
            {"config_entry_id": loaded.entry_id, "zeit": dt_util.utcnow().isoformat(), "diesel_betrag": 20},
            blocking=True,
            return_response=True,
        )

    assert err.value.translation_key == "late_without_refill"


async def test_changing_the_time_takes_the_counters_of_the_new_time(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    coordinator = coordinator_of(loaded)
    remember_stops(coordinator)
    book = coordinator.logbook.logbook
    yesterday = dt_util.utcnow() - timedelta(days=1)
    entry = book.add(yesterday, Occasion.MANUAL, odometer_km=33_900, distance_counter_m=0, place="Daheim")
    later = dt_util.utcnow().replace(second=0, microsecond=0)

    response = await hass.services.async_call(
        DOMAIN,
        "fahrtenbuch_aendern",
        {"config_entry_id": loaded.entry_id, "eintrag": entry.id, "zeit": later.isoformat()},
        blocking=True,
        return_response=True,
    )

    changed = book.get(entry.id)
    assert response is not None
    assert changed is not None
    assert changed.time == later
    # Parked after the last trip: the counters are the current ones; odometer and place stay.
    assert changed.distance_counter_m == 150_000
    assert (changed.odometer_km, changed.odometer_corrected, changed.place) == (33_900, False, "Daheim")
