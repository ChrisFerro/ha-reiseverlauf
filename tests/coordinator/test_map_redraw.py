"""Tests for drawing the map of one export anew with tiles (docs/features/feat-12-kartensymbole.md 6.8)."""

from collections.abc import Generator
from dataclasses import replace
from datetime import timedelta
import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
from PIL import Image
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_capture_events, async_fire_time_changed

from custom_components.reiseverlauftracker.const import DOMAIN, EVENT_TOUR, EVENT_TRIP_ENDED
from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator, ferries
from custom_components.reiseverlauftracker.coordinator.exports import read_export, write_metadata
from custom_components.reiseverlauftracker.export import ExportFile
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

DPLUS = "sensor.camper_dplus"
TRACKER = "device_tracker.camper_gps"
SPEED = "sensor.camper_speed"
ALTITUDE = "sensor.camper_altitude"
CHOICE = "select.camper_gps_export_auswahl"
REDRAW = "button.camper_gps_karte_neu_zeichnen"
METRES_PER_DEGREE_LAT = 111195.0
# The steps onto and off the ship belong to the crossing: 1 km on, 9 km on board, 0.5 km off.
DRIVEN_KM = 9.5
FERRY_KM = 10.5


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


def _tile() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), (235, 235, 220)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def tiles() -> Generator[None]:
    """Serve complete tiles; drawing a map anew refuses blank ones."""
    tile = _tile()
    with patch(
        "custom_components.reiseverlauftracker.export.exporter.http_tile_fetcher", return_value=lambda _url: tile
    ):
        yield


@pytest.fixture(autouse=True)
def no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the pause before asking Nominatim."""
    monkeypatch.setattr(ferries, "NOMINATIM_INTERVAL_S", 0)


@pytest.fixture
async def old_trip(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory, media_dir: Path
) -> ReiseverlaufDataUpdateCoordinator:
    """
    A finished trip with a ferry crossing as an export from before Feat-12: no base map, the stop unchecked.

    The ferry check did not know the water then (on land), so the stop's mark stays unchecked.
    """
    hass.config.language = "de"
    hass.states.async_set(DPLUS, "OFF")
    set_position(hass, 0)
    hass.states.async_set(SPEED, "0")
    hass.states.async_set(ALTITUDE, "100.0")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator: ReiseverlaufDataUpdateCoordinator = config_entry.runtime_data.coordinator
    await drive(hass, freezer, 0, 5000)
    await cross(hass, freezer, 5000, 10_000)
    await drive(hass, freezer, 15_000, 5000)
    # The log of the trip is gone; only the export's raw data are left.
    await advance(hass, freezer, timedelta(hours=8))
    assert coordinator.log is None
    info = coordinator.data.last_export
    assert info is not None
    assert info.base_map is not None
    base = media_dir / "reiseverlauf"
    (base / info.folder / info.base_map.name).unlink()
    write_metadata(base, replace(info, base_map=None))
    await coordinator.async_refresh_exports()
    return coordinator


async def redraw(hass: HomeAssistant, entry_id: str, export: str | None = None) -> dict:
    data = {"config_entry_id": entry_id} | ({"export": export} if export else {})
    return await hass.services.async_call(DOMAIN, "karte_neu_zeichnen", data, blocking=True, return_response=True)


async def test_redraw_gives_an_old_trip_its_base_map_ferry_and_pitch(
    hass: HomeAssistant,
    old_trip: ReiseverlaufDataUpdateCoordinator,
    config_entry: MockConfigEntry,
    media_dir: Path,
    on_water: AsyncMock,
    camp_site: AsyncMock,
) -> None:
    info = old_trip.exports[0]
    assert info.distance_km == pytest.approx(20.0, rel=0.02)
    on_water.reset_mock()
    on_water.return_value = True
    camp_site.return_value = "Camping Seeblick"
    events = async_capture_events(hass, EVENT_TRIP_ENDED)

    response = await redraw(hass, config_entry.entry_id, info.folder)

    assert response == {"ordner": info.folder, "titel": info.title, "faehren_erkannt": 1}
    on_water.assert_awaited_once()
    renewed = read_export(media_dir / "reiseverlauf", info.folder)
    assert renewed is not None
    assert renewed.base_map is not None
    assert (media_dir / "reiseverlauf" / info.folder / renewed.base_map.name).is_file()
    assert renewed.distance_km == pytest.approx(DRIVEN_KM, abs=0.1)
    assert renewed.ferry_km == pytest.approx(FERRY_KM, abs=0.1)
    assert renewed.stops[0].ferry
    assert renewed.arrival_stay == "Camping Seeblick"
    assert "Stellplatz:      Camping Seeblick" in renewed.stats_text
    assert renewed.updated is not None
    assert old_trip.logbook.logbook.distance_counter_m == pytest.approx(DRIVEN_KM * 1000, abs=100)
    assert not events

    # The stop is checked now; drawing again does not ask once more.
    on_water.reset_mock()
    response = await redraw(hass, config_entry.entry_id, info.folder)
    assert response["faehren_erkannt"] == 0
    on_water.assert_not_awaited()


async def test_button_redraws_the_chosen_export(
    hass: HomeAssistant, old_trip: ReiseverlaufDataUpdateCoordinator, media_dir: Path
) -> None:
    info = old_trip.exports[0]
    await hass.services.async_call(
        "select", "select_option", {"entity_id": CHOICE, "option": old_trip.export_label(info)}, blocking=True
    )

    await hass.services.async_call("button", "press", {"entity_id": REDRAW}, blocking=True)

    renewed = read_export(media_dir / "reiseverlauf", info.folder)
    assert renewed is not None
    assert renewed.base_map is not None


async def test_all_exports_at_once_are_refused(
    hass: HomeAssistant, old_trip: ReiseverlaufDataUpdateCoordinator, config_entry: MockConfigEntry
) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await redraw(hass, config_entry.entry_id, "all")

    assert err.value.translation_key == "redraw_all"


async def test_without_raw_data_the_export_stays(
    hass: HomeAssistant, old_trip: ReiseverlaufDataUpdateCoordinator, config_entry: MockConfigEntry, media_dir: Path
) -> None:
    info = old_trip.exports[0]
    await old_trip.async_remove_files([info], {ExportFile.RAW})
    before = (media_dir / "reiseverlauf" / info.folder / "export.json").read_text(encoding="utf-8")

    with pytest.raises(ServiceValidationError) as err:
        await redraw(hass, config_entry.entry_id, info.folder)

    assert err.value.translation_key == "redraw_without_raw_data"
    assert (media_dir / "reiseverlauf" / info.folder / "export.json").read_text(encoding="utf-8") == before


async def test_missing_tiles_keep_the_map(
    hass: HomeAssistant, old_trip: ReiseverlaufDataUpdateCoordinator, config_entry: MockConfigEntry, media_dir: Path
) -> None:
    info = old_trip.exports[0]
    map_path = media_dir / "reiseverlauf" / info.folder / info.files[ExportFile.MAP]
    map_bytes = map_path.read_bytes()

    with (
        patch(
            "custom_components.reiseverlauftracker.export.exporter.http_tile_fetcher",
            return_value=lambda _url: None,
        ),
        pytest.raises(HomeAssistantError) as err,
    ):
        await redraw(hass, config_entry.entry_id, info.folder)

    assert err.value.translation_key == "map_tiles_failed"
    assert map_path.read_bytes() == map_bytes
    renewed = read_export(media_dir / "reiseverlauf", info.folder)
    assert renewed is not None
    assert renewed.base_map is None


async def test_redraw_gives_an_old_tour_its_base_map(
    hass: HomeAssistant, old_trip: ReiseverlaufDataUpdateCoordinator, config_entry: MockConfigEntry, media_dir: Path
) -> None:
    trip = old_trip.exports[0]
    tour = await old_trip.tours.async_create(trip.start - timedelta(hours=1), trip.end + timedelta(hours=1))
    assert tour.base_map is not None
    base = media_dir / "reiseverlauf"
    (base / tour.folder / tour.base_map.name).unlink()
    write_metadata(base, replace(tour, base_map=None))
    await old_trip.async_refresh_exports()
    events = async_capture_events(hass, EVENT_TOUR)

    response = await redraw(hass, config_entry.entry_id, tour.folder)

    assert response["ordner"] == tour.folder
    renewed = read_export(base, tour.folder)
    assert renewed is not None
    assert renewed.base_map is not None
    assert (base / tour.folder / renewed.base_map.name).is_file()
    assert not events
