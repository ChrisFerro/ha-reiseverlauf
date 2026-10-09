"""Tests for the exportieren, aufraeumen, reise_starten and reise_beenden actions."""

from datetime import timedelta
from pathlib import Path
import re

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events, async_fire_time_changed
from pytest_homeassistant_custom_component.components.recorder.common import async_wait_recording_done

from custom_components.reiseverlauftracker.const import DOMAIN, EVENT_TRIP_EXPORTED
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
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


async def setup(hass: HomeAssistant, entry: MockConfigEntry, media_dir: Path) -> MockConfigEntry:
    """Set up the integration with the vehicle parked and its media folder in `media_dir`."""
    hass.config.media_dirs = {"local": str(media_dir)}
    hass.states.async_set(DPLUS, "OFF")
    set_position(hass, 0)
    hass.states.async_set(SPEED, "0")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def call(hass: HomeAssistant, service: str, data: dict, *, response: bool = False) -> dict | None:
    """Call one of the actions of the integration and wait for it."""
    return await hass.services.async_call(DOMAIN, service, data, blocking=True, return_response=response)


async def test_actions_exist_without_entry(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    for service in ("exportieren", "aufraeumen", "reise_starten", "reise_beenden"):
        assert hass.services.has_service(DOMAIN, service)

    with pytest.raises(ServiceValidationError) as err:
        await call(hass, "reise_starten", {"config_entry_id": "missing"})
    assert err.value.translation_key == "entry_not_found"


async def test_export_period_from_history(
    recorder_mock: object,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    media_dir: Path,
) -> None:
    hass.config.language = "de"
    entry = await setup(hass, config_entry, media_dir)
    events = async_capture_events(hass, EVENT_TRIP_EXPORTED)
    start = dt_util.utcnow() - timedelta(minutes=1)
    for step in range(1, 6):
        hass.states.async_set(SPEED, str(1118656744 if step == 1 else 50 + step))
        set_position(hass, 1000 * step)
    await async_wait_recording_done(hass)

    result = await call(
        hass,
        "exportieren",
        {
            "config_entry_id": entry.entry_id,
            "von": start.isoformat(),
            "bis": (dt_util.utcnow() + timedelta(minutes=1)).isoformat(),
            "titel": "Testfahrt",  # codespell:ignore titel
            "skala": 1,
        },
        response=True,
    )

    assert result is not None
    assert result["titel"] == "Testfahrt"  # codespell:ignore titel
    assert result["strecke_km"] == pytest.approx(5.0, abs=0.1)
    assert re.fullmatch(r"\d{4}-\d\d-\d\d_\d{4}-\d{4}", result["ordner"])  # codespell:ignore ordner
    assert (media_dir / "reiseverlauf" / result["ordner"] / "export.json").exists()  # codespell:ignore ordner
    assert {f["typ"] for f in result["dateien"]} == {"composite", "map", "profile", "gpx", "stats", "raw"}
    assert len(events) == 1
    assert events[0].data["titel"] == "Testfahrt"  # codespell:ignore titel
    exports = entry.runtime_data.coordinator.data.exports
    assert [info.automatic for info in exports] == [False]
    assert entry.runtime_data.coordinator.data.last_export is None


async def test_export_rejects_bad_period(
    recorder_mock: object, hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path
) -> None:
    entry = await setup(hass, config_entry, media_dir)
    now = dt_util.utcnow()

    with pytest.raises(ServiceValidationError) as err:
        await call(
            hass,
            "exportieren",
            {"config_entry_id": entry.entry_id, "von": now.isoformat(), "bis": (now - timedelta(hours=1)).isoformat()},
        )
    assert err.value.translation_key == "invalid_period"

    with pytest.raises(ServiceValidationError) as err:
        await call(
            hass,
            "exportieren",
            {
                "config_entry_id": entry.entry_id,
                "von": (now - timedelta(hours=1)).isoformat(),
                "bis": now.isoformat(),
            },
        )
    assert err.value.translation_key == "no_movement"


async def drive(hass: HomeAssistant, freezer: FrozenDateTimeFactory, start_m: float) -> None:
    """Drive 5 km with D+ on, switch it off and wait until the trip is exported."""
    hass.states.async_set(DPLUS, "ON")
    for step in range(1, 6):
        freezer.tick(timedelta(minutes=1))
        async_fire_time_changed(hass, dt_util.utcnow())
        hass.states.async_set(SPEED, "60")
        set_position(hass, start_m + 1000 * step)
        await hass.async_block_till_done()
    hass.states.async_set(DPLUS, "OFF")
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=61))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def test_cleanup_removes_chosen_types_and_then_folder(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory, media_dir: Path
) -> None:
    entry = await setup(hass, config_entry, media_dir)
    await drive(hass, freezer, 0)
    coordinator = entry.runtime_data.coordinator
    info = coordinator.data.last_export
    assert info is not None
    label = info.label(dt_util.get_default_time_zone())

    result = await call(
        hass,
        "aufraeumen",
        {"config_entry_id": entry.entry_id, "export": label, "dateitypen": ["raw", "gpx"]},
        response=True,
    )
    assert result == {"ordner": [info.folder], "dateitypen": ["gpx", "raw"]}  # codespell:ignore ordner
    remaining = coordinator.data.last_export
    assert remaining is not None
    assert {kind.value for kind in remaining.files} == {"composite", "map", "profile", "stats"}

    await call(hass, "aufraeumen", {"config_entry_id": entry.entry_id, "export": info.folder})
    assert coordinator.data.exports == ()
    assert coordinator.data.last_export is None
    assert not (media_dir / "reiseverlauf" / info.folder).exists()


async def test_cleanup_all_exports(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory, media_dir: Path
) -> None:
    entry = await setup(hass, config_entry, media_dir)
    await drive(hass, freezer, 0)
    freezer.tick(timedelta(hours=7))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    await drive(hass, freezer, 5000)
    assert len(entry.runtime_data.coordinator.data.exports) == 2

    await call(hass, "aufraeumen", {"config_entry_id": entry.entry_id, "export": "all"})

    assert entry.runtime_data.coordinator.data.exports == ()


async def test_cleanup_unknown_export(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory, media_dir: Path
) -> None:
    entry = await setup(hass, config_entry, media_dir)
    await drive(hass, freezer, 0)

    with pytest.raises(ServiceValidationError) as err:
        await call(hass, "aufraeumen", {"config_entry_id": entry.entry_id, "export": "nope"})
    assert err.value.translation_key == "export_not_found"


async def test_start_and_end_trip(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory, media_dir: Path
) -> None:
    entry = await setup(hass, config_entry, media_dir)
    coordinator = entry.runtime_data.coordinator

    with pytest.raises(ServiceValidationError) as err:
        await call(hass, "reise_beenden", {"config_entry_id": entry.entry_id})
    assert err.value.translation_key == "no_trip"

    await call(hass, "reise_starten", {"config_entry_id": entry.entry_id})
    assert coordinator.data.active

    with pytest.raises(ServiceValidationError) as err:
        await call(hass, "reise_starten", {"config_entry_id": entry.entry_id})
    assert err.value.translation_key == "trip_running"

    freezer.tick(timedelta(minutes=5))
    set_position(hass, 3000)
    await hass.async_block_till_done()
    await call(hass, "reise_beenden", {"config_entry_id": entry.entry_id})
    await hass.async_block_till_done()

    assert not coordinator.data.active
    assert coordinator.data.last_export is not None


async def test_cleanup_without_export_uses_the_selection(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory, media_dir: Path
) -> None:
    entry = await setup(hass, config_entry, media_dir)
    await drive(hass, freezer, 0)
    freezer.tick(timedelta(hours=7))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    await drive(hass, freezer, 5000)
    coordinator = entry.runtime_data.coordinator
    newest, oldest = coordinator.data.exports
    choice = er.async_get(hass).async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_export_choice")
    assert choice is not None

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": choice, "option": oldest.label(dt_util.get_default_time_zone())},
        blocking=True,
    )
    result = await call(hass, "aufraeumen", {"config_entry_id": entry.entry_id}, response=True)

    assert result is not None
    assert result["ordner"] == [oldest.folder]  # codespell:ignore ordner
    assert [info.folder for info in coordinator.data.exports] == [newest.folder]
    assert hass.states.get(choice).state == newest.label(dt_util.get_default_time_zone())
