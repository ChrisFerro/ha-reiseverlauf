"""Tests for the entities of a set-up entry."""

from datetime import timedelta
from http import HTTPStatus

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, mock_restore_cache
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from homeassistant.components.select import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

DPLUS = "sensor.camper_dplus"
TRACKER = "device_tracker.camper_gps"
SPEED = "sensor.camper_speed"
METRES_PER_DEGREE_LAT = 111195.0

STATUS = "sensor.camper_gps_reisestatus"
ACTIVE = "binary_sensor.camper_gps_reise_aktiv"
TRIP_DISTANCE = "sensor.camper_gps_strecke_laufende_reise"
LAST_TITLE = "sensor.camper_gps_letzte_reise"
LAST_DISTANCE = "sensor.camper_gps_letzte_reise_strecke"
IMAGE = "image.camper_gps_letzte_reise_gesamtbild"
CHOICE = "select.camper_gps_export_auswahl"
TRIP_START = "sensor.camper_gps_reisebeginn"
PAUSE = "sensor.camper_gps_pausenzeit_laufende_reise"
AVERAGE = "sensor.camper_gps_durchschnitt_laufende_reise"


def set_position(hass: HomeAssistant, metres_north: float) -> None:
    """Move the tracker `metres_north` of the start point."""
    hass.states.async_set(
        TRACKER,
        "not_home",
        {"latitude": 50.0 + metres_north / METRES_PER_DEGREE_LAT, "longitude": 8.0, "gps_accuracy": 10},
    )


async def advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    """Move the clock forward and run what became due."""
    freezer.tick(delta)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def drive(hass: HomeAssistant, freezer: FrozenDateTimeFactory, start_m: float, metres: float) -> None:
    """Drive with D+ on, then switch D+ off and wait for the end delay."""
    hass.states.async_set(DPLUS, "ON")
    for step in range(1, 6):
        await advance(hass, freezer, timedelta(minutes=1))
        hass.states.async_set(SPEED, "60")
        set_position(hass, start_m + metres * step / 5)
    await advance(hass, freezer, timedelta(minutes=1))
    hass.states.async_set(DPLUS, "OFF")
    await hass.async_block_till_done()
    await advance(hass, freezer, timedelta(minutes=61))


@pytest.fixture
async def loaded(hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory) -> MockConfigEntry:
    """Set up the integration with the vehicle parked."""
    hass.config.language = "de"
    assert await async_setup_component(hass, "http", {})
    hass.states.async_set(DPLUS, "OFF")
    set_position(hass, 0)
    hass.states.async_set(SPEED, "0")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def test_entities_belong_to_one_service_device(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    entities = er.async_entries_for_config_entry(er.async_get(hass), loaded.entry_id)
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), loaded.entry_id)

    assert len(entities) == 14
    assert len(devices) == 1
    assert devices[0].entry_type is dr.DeviceEntryType.SERVICE
    assert {e.device_id for e in entities} == {devices[0].id}


async def test_idle_state(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    assert hass.states.get(STATUS).state == "bereit"
    assert hass.states.get(ACTIVE).state == "off"
    assert hass.states.get(TRIP_DISTANCE).state == "unknown"
    assert hass.states.get(LAST_TITLE).state == "unknown"
    assert hass.states.get(IMAGE).state == "unknown"
    assert hass.states.get(CHOICE).attributes["options"] == ["all"]


async def test_states_follow_the_trip(
    hass: HomeAssistant, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set(DPLUS, "ON")
    await advance(hass, freezer, timedelta(minutes=1))
    set_position(hass, 2000)
    await hass.async_block_till_done()

    assert hass.states.get(STATUS).state == "unterwegs"
    assert hass.states.get(ACTIVE).state == "on"
    assert float(hass.states.get(TRIP_DISTANCE).state) == pytest.approx(2.0, rel=1e-3)
    assert hass.states.get(TRIP_START).attributes["startort"] == "Startort"
    assert float(hass.states.get(AVERAGE).state) == pytest.approx(120.0, rel=0.01)

    hass.states.async_set(DPLUS, "OFF")
    await hass.async_block_till_done()
    await advance(hass, freezer, timedelta(minutes=6))
    pause = hass.states.get(PAUSE)
    assert float(pause.state) == pytest.approx(6.0, abs=0.1)
    assert [h["ort"] for h in pause.attributes["halte"]] == ["Zielort"]
    status = hass.states.get(STATUS)
    assert status.state == "pause"
    assert status.attributes["voraussichtliches_ende"] is not None
    assert hass.states.get(ACTIVE).state == "on"

    await advance(hass, freezer, timedelta(minutes=54))
    status = hass.states.get(STATUS)
    assert status.state == "zusammenfuehrbar"
    assert status.attributes["fortsetzbar_bis"] is not None
    assert hass.states.get(ACTIVE).state == "off"


async def test_last_trip_entities_after_export(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    hass_client: ClientSessionGenerator,
) -> None:
    await drive(hass, freezer, 0, 5000)

    title = hass.states.get(LAST_TITLE)
    assert title.state.startswith("Startort – Zielort, ")
    assert {f["typ"] for f in title.attributes["dateien"]} >= {"composite", "gpx"}
    assert all(f["url"].startswith("/media/local/reiseverlauf/") for f in title.attributes["dateien"])
    assert "Strecke" in title.attributes["statistik"]
    assert float(hass.states.get(LAST_DISTANCE).state) == pytest.approx(5.0, rel=0.01)

    image = hass.states.get(IMAGE)
    assert image.state != "unknown"
    client = await hass_client()
    response = await client.get(f"/api/image_proxy/{IMAGE}?token={image.attributes['access_token']}")
    assert response.status == HTTPStatus.OK
    assert (await response.read()).startswith(b"\x89PNG")

    choice = hass.states.get(CHOICE)
    assert len(choice.attributes["options"]) == 2
    assert choice.state == choice.attributes["options"][0]
    assert choice.state.endswith(f"· {title.state[:17]}…")


async def test_entities_start_with_an_existing_export(
    hass: HomeAssistant, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    await drive(hass, freezer, 0, 5000)

    assert await hass.config_entries.async_reload(loaded.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(IMAGE).state != "unknown"
    assert hass.states.get(LAST_TITLE).state.startswith("Startort – Zielort, ")


async def test_export_choice_keeps_selection(
    hass: HomeAssistant, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    await drive(hass, freezer, 0, 5000)

    await hass.services.async_call(
        "select", SERVICE_SELECT_OPTION, {ATTR_ENTITY_ID: CHOICE, ATTR_OPTION: "all"}, blocking=True
    )
    assert hass.states.get(CHOICE).state == "all"

    await drive(hass, freezer, 5000, 5000)
    assert hass.states.get(CHOICE).state == "all"


async def test_export_choice_is_restored(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    hass.config.language = "de"
    assert await async_setup_component(hass, "http", {})
    mock_restore_cache(hass, [State(CHOICE, "all")])
    hass.states.async_set(DPLUS, "OFF")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(CHOICE).state == "all"
