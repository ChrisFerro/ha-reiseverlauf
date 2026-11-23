"""Tests for renewing the export of a finished trip after its logbook entries or travel costs changed."""

from datetime import date, timedelta
import json
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events, async_fire_time_changed

from custom_components.reiseverlauftracker.const import EVENT_TRIP_ENDED
from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
from custom_components.reiseverlauftracker.coordinator.exports import ExportInfo
from custom_components.reiseverlauftracker.coordinator.logbook import CostCategory, Occasion, Refill
from custom_components.reiseverlauftracker.export import ExportFile
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

DPLUS = "sensor.camper_dplus"
TRACKER = "device_tracker.camper_gps"
SPEED = "sensor.camper_speed"
IMAGE = "image.camper_gps_letzte_reise_gesamtbild"
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


async def drive(hass: HomeAssistant, freezer: FrozenDateTimeFactory, start_m: float, metres: float) -> None:
    """Drive `metres` north from `start_m` with D+ on, then switch D+ off and wait until the trip ended."""
    hass.states.async_set(DPLUS, "ON")
    for step in range(1, 11):
        await advance(hass, freezer, timedelta(minutes=1))
        hass.states.async_set(SPEED, "60")
        set_position(hass, start_m + metres * step / 10)
    await advance(hass, freezer, timedelta(minutes=1))
    hass.states.async_set(SPEED, "0")
    hass.states.async_set(DPLUS, "OFF")
    await hass.async_block_till_done()
    await advance(hass, freezer, timedelta(minutes=61))
    await advance(hass, freezer, timedelta(seconds=5))


@pytest.fixture
async def finished(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> ReiseverlaufDataUpdateCoordinator:
    """Set up the integration with an odometer reading and drive one 10 km trip."""
    hass.config.language = "de"
    hass.states.async_set(DPLUS, "OFF")
    set_position(hass, 0)
    hass.states.async_set(SPEED, "0")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator: ReiseverlaufDataUpdateCoordinator = config_entry.runtime_data.coordinator
    coordinator.logbook.logbook.add(dt_util.utcnow(), Occasion.MANUAL, odometer_km=34_000, fuel_percent=50)
    await drive(hass, freezer, 0, 10_000)
    assert coordinator.last_export is not None
    return coordinator


def files_of(media_dir: Path, info: ExportInfo) -> dict[ExportFile, Path]:
    """Return the paths of the files of an export."""
    return {kind: media_dir / "reiseverlauf" / info.folder / name for kind, name in info.files.items()}


async def test_travel_cost_renews_statistics_composite_and_metadata(
    hass: HomeAssistant,
    finished: ReiseverlaufDataUpdateCoordinator,
    freezer: FrozenDateTimeFactory,
    media_dir: Path,
) -> None:
    events = async_capture_events(hass, EVENT_TRIP_ENDED)
    info = finished.last_export
    assert info is not None
    paths = files_of(media_dir, info)
    before = {kind: path.read_bytes() for kind, path in paths.items()}
    image_updated = hass.states.get(IMAGE).state

    keeper = finished.logbook
    await keeper.async_add_travel_cost(date(2026, 11, 2), CostCategory.TOLL, 23.4, trip_start=info.start, country="AT")
    await advance(hass, freezer, timedelta(seconds=10))
    await keeper.async_add_travel_cost(date(2026, 11, 2), CostCategory.TOLL, 59.9, trip_start=info.start, country="IT")
    assert finished.last_export.updated is None
    await advance(hass, freezer, timedelta(seconds=31))

    renewed = finished.last_export
    assert renewed is not None
    assert renewed.updated is not None
    assert renewed.logbook is not None
    assert renewed.logbook.travel_costs == {"maut": pytest.approx(83.3)}
    assert renewed.logbook.odometer_end_km == 34_010
    text = paths[ExportFile.STATS].read_text(encoding="utf-8")
    assert text == renewed.stats_text
    assert "Reisekosten:     Maut 83,30 €" in text
    metadata = json.loads((media_dir / "reiseverlauf" / info.folder / "export.json").read_text())
    assert metadata["logbook"]["reisekosten"] == {"maut": 83.3}
    assert metadata["logbook"]["kosten"] == 83.3
    for kind in (ExportFile.MAP, ExportFile.PROFILE, ExportFile.GPX, ExportFile.RAW):
        assert paths[kind].read_bytes() == before[kind]
    assert paths[ExportFile.COMPOSITE].read_bytes() != before[ExportFile.COMPOSITE]
    assert hass.states.get(IMAGE).state != image_updated
    assert events == []


async def test_late_refill_of_the_trip_is_in_the_renewed_export(
    hass: HomeAssistant, finished: ReiseverlaufDataUpdateCoordinator, freezer: FrozenDateTimeFactory
) -> None:
    info = finished.last_export
    assert info is not None

    await finished.late_form.async_add(info.start + timedelta(minutes=5, seconds=30), fuel=Refill(40, 70))
    await advance(hass, freezer, timedelta(seconds=31))

    renewed = finished.last_export
    assert renewed is not None
    assert renewed.logbook is not None
    assert (renewed.logbook.fuel_litres, renewed.logbook.fuel_cost) == (40, 70)
    assert "Getankt:         40,0 l Diesel" in renewed.stats_text


async def test_without_raw_data_only_the_metadata_is_renewed(
    hass: HomeAssistant,
    finished: ReiseverlaufDataUpdateCoordinator,
    freezer: FrozenDateTimeFactory,
    media_dir: Path,
) -> None:
    info = finished.last_export
    assert info is not None
    paths = files_of(media_dir, info)
    paths[ExportFile.RAW].unlink()
    stats = paths[ExportFile.STATS].read_text(encoding="utf-8")

    await finished.logbook.async_add_travel_cost(date(2026, 11, 2), CostCategory.FERRY, 85, trip_start=info.start)
    await advance(hass, freezer, timedelta(seconds=31))

    renewed = finished.last_export
    assert renewed is not None
    assert renewed.logbook is not None
    assert renewed.logbook.travel_costs == {"faehre": 85}
    assert info.logbook is not None
    assert renewed.logbook.odometer_end_km == info.logbook.odometer_end_km
    assert paths[ExportFile.STATS].read_text(encoding="utf-8") == stats


async def test_running_trip_and_costs_without_trip_are_not_renewed(
    hass: HomeAssistant, finished: ReiseverlaufDataUpdateCoordinator, freezer: FrozenDateTimeFactory
) -> None:
    info = finished.last_export
    assert info is not None
    await finished.logbook.async_add_travel_cost(date(2026, 11, 2), CostCategory.PITCH, 18)
    hass.states.async_set(DPLUS, "ON")
    await advance(hass, freezer, timedelta(minutes=1))
    set_position(hass, 12_000)
    await hass.async_block_till_done()
    assert finished.log is not None
    finished.refresher.schedule(finished.log.start)

    await advance(hass, freezer, timedelta(seconds=31))

    assert all(i.updated is None for i in finished.exports)
