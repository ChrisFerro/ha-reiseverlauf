"""Tests for the export that runs when a trip ends."""

from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events, async_fire_time_changed

from custom_components.reiseverlauftracker.const import EVENT_TRIP_ENDED, SECTION_EXPORT
from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
from custom_components.reiseverlauftracker.coordinator.models import TripStatus
from homeassistant.core import HomeAssistant
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


async def test_ended_trip_is_exported_and_announced(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    media_dir: Path,
) -> None:
    hass.config.language = "de"
    events = async_capture_events(hass, EVENT_TRIP_ENDED)
    coordinator = await setup(hass, config_entry)
    await drive(hass, freezer, 0, 5000)

    await advance(hass, freezer, timedelta(minutes=60))

    assert coordinator.data.status is TripStatus.MERGEABLE
    info = coordinator.data.last_export
    assert info is not None
    assert info.title.startswith("Startort – Zielort, ")
    assert info.distance_km == pytest.approx(5.0, rel=0.01)
    folder = media_dir / "reiseverlauf" / info.folder
    assert sorted(p.name for p in folder.iterdir()) == sorted([*info.files.values(), "export.json"])
    assert {kind.value for kind in info.files} == {"composite", "map", "profile", "gpx", "stats", "raw"}

    assert len(events) == 1
    data = events[0].data
    assert data["entry_id"] == config_entry.entry_id
    assert data["titel"] == info.title
    assert data["fortgesetzt"] is False
    assert data["strecke_km"] == pytest.approx(5.0, abs=0.1)
    assert data["gesamtbild"] == str(folder / info.files[next(k for k in info.files if k.value == "composite")])
    assert data["gesamtbild_url"].startswith(f"/media/local/reiseverlauf/{info.folder}/")
    assert {f["typ"] for f in data["dateien"]} == {kind.value for kind in info.files}
    assert "Strecke" in data["statistik"]
    json.dumps(data)


async def test_merged_trip_replaces_previous_export(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    media_dir: Path,
) -> None:
    events = async_capture_events(hass, EVENT_TRIP_ENDED)
    coordinator = await setup(hass, config_entry)
    await drive(hass, freezer, 0, 5000)
    await advance(hass, freezer, timedelta(minutes=60))
    first = coordinator.data.last_export

    await drive(hass, freezer, 5000, 5000)
    await advance(hass, freezer, timedelta(minutes=60))

    second = coordinator.data.last_export
    assert first is not None
    assert second is not None
    assert second.folder == first.folder
    assert second.distance_km == pytest.approx(10.0, rel=0.01)
    assert [e.data["fortgesetzt"] for e in events] == [False, True]
    assert len(list((media_dir / "reiseverlauf").iterdir())) == 1


async def test_date_title_without_place_lookup(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    entry_data: dict,
    geocode: AsyncMock,
) -> None:
    hass.config.language = "de"
    entry = MockConfigEntry(
        domain="reiseverlauftracker",
        unique_id=TRACKER,
        data=entry_data,
        options={SECTION_EXPORT: {"place_names": False}},
    )
    coordinator = await setup(hass, entry)
    await drive(hass, freezer, 0, 5000)
    await advance(hass, freezer, timedelta(minutes=60))

    assert coordinator.data.last_export is not None
    assert coordinator.data.last_export.title.startswith("Wohnmobil ")
    geocode.assert_not_called()


async def test_failed_export_shows_error_until_next_trip(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    coordinator = await setup(hass, config_entry)
    await drive(hass, freezer, 0, 5000)

    with patch(
        "custom_components.reiseverlauftracker.coordinator.export_runner.export_trip",
        side_effect=OSError("disk full"),
    ):
        await advance(hass, freezer, timedelta(minutes=60))

    assert coordinator.data.status is TripStatus.ERROR

    hass.states.async_set(DPLUS, "ON")
    await hass.async_block_till_done()
    assert coordinator.data.status is TripStatus.DRIVING


async def test_last_export_is_loaded_after_restart(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    coordinator = await setup(hass, config_entry)
    await drive(hass, freezer, 0, 5000)
    await advance(hass, freezer, timedelta(minutes=60))
    exported = coordinator.data.last_export

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.runtime_data.coordinator.data.last_export == exported


async def test_stops_are_tracked_live_and_listed_in_the_export(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    hass.config.language = "de"
    events = async_capture_events(hass, EVENT_TRIP_ENDED)
    coordinator = await setup(hass, config_entry)
    await drive(hass, freezer, 0, 5000)

    await advance(hass, freezer, timedelta(minutes=2))
    assert coordinator.data.stops == ()
    await advance(hass, freezer, timedelta(minutes=4))
    assert [(s.place, s.end) for s in coordinator.data.stops] == [("Zielort", None)]

    await advance(hass, freezer, timedelta(minutes=4))
    await drive(hass, freezer, 5000, 5000)
    await advance(hass, freezer, timedelta(minutes=60))

    stops = events[0].data["halte"]
    assert [(s["ort"], s["dauer_min"]) for s in stops] == [("Zielort", 10)]
    assert "Halte:\n  Zielort" in events[0].data["statistik"]
    assert coordinator.data.last_export is not None
    assert len(coordinator.data.last_export.stops) == 1


async def test_short_stops_are_not_listed(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    events = async_capture_events(hass, EVENT_TRIP_ENDED)
    await setup(hass, config_entry)
    await drive(hass, freezer, 0, 5000)
    await advance(hass, freezer, timedelta(minutes=2))
    await drive(hass, freezer, 5000, 5000)
    await advance(hass, freezer, timedelta(minutes=60))

    assert events[0].data["halte"] == []


async def test_pause_time_and_average_update_while_standing(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    coordinator = await setup(hass, config_entry)
    await drive(hass, freezer, 0, 5000)
    data = coordinator.data
    assert data.average_kmh == pytest.approx(30.0, rel=0.01)
    assert data.driving_time == timedelta(minutes=10)
    pause = data.pause_time
    assert pause is not None

    await advance(hass, freezer, timedelta(minutes=5))

    assert coordinator.data.pause_time == pause + timedelta(minutes=5)
