"""Tests for the cost sensors over all costs and the open toll sensor."""

from dataclasses import replace
from datetime import date, timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reiseverlauftracker.const import DOMAIN
from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
from custom_components.reiseverlauftracker.coordinator.exports import ExportInfo
from custom_components.reiseverlauftracker.coordinator.logbook import CostCategory, Occasion, Refill
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

MONTH = "sensor.camper_gps_reisekosten_monat"
YEAR = "sensor.camper_gps_reisekosten_jahr"
OPEN_TOLL = "sensor.camper_gps_maut_offen"


@pytest.fixture
async def coordinator(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> ReiseverlaufDataUpdateCoordinator:
    """Set up the integration in German on 17 November 2026."""
    freezer.move_to("2026-11-17 12:00:00+00:00")
    hass.config.language = "de"
    hass.states.async_set("sensor.camper_dplus", "OFF")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry.runtime_data.coordinator


async def refresh(hass: HomeAssistant, coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    """Let the entities show the current figures."""
    coordinator.async_update_listeners()
    await hass.async_block_till_done()


def trip(start: str, countries: tuple[str, ...] | None, *, automatic: bool = True) -> ExportInfo:
    """Return an export of a trip that started at `start` (UTC) through `countries`."""
    begin = dt_util.parse_datetime(f"{start}+00:00")
    assert begin is not None
    return ExportInfo(
        folder=f"{begin:%Y-%m-%d_%H%M}",
        title=f"Reise {begin:%d.%m.}",
        start=begin,
        end=begin + timedelta(hours=3),
        distance_km=200,
        driving_time=timedelta(hours=2),
        files={},
        stats_text="",
        automatic=automatic,
        countries=countries,
    )


async def test_cost_sensors_count_all_costs_by_period(
    hass: HomeAssistant, coordinator: ReiseverlaufDataUpdateCoordinator
) -> None:
    book = coordinator.logbook.logbook
    book.add(dt_util.utcnow() - timedelta(days=2), Occasion.MANUAL, fuel=Refill(60, 102.5), gas=Refill(10, 9.5))
    book.add_travel_cost(date(2026, 11, 3), CostCategory.TOLL, 23.4, country="AT")
    book.add_travel_cost(date(2026, 10, 31), CostCategory.FERRY, 85)
    book.add_travel_cost(date(2025, 12, 31), CostCategory.PITCH, 18)
    await refresh(hass, coordinator)

    month = hass.states.get(MONTH)
    assert month is not None
    assert float(month.state) == pytest.approx(135.4)
    assert month.attributes["diesel"] == 102.5
    assert month.attributes["gas"] == 9.5
    assert month.attributes["maut"] == 23.4
    assert month.attributes["faehre"] == 0
    assert month.attributes["unit_of_measurement"] == hass.config.currency
    year = hass.states.get(YEAR)
    assert year is not None
    assert float(year.state) == pytest.approx(220.4)
    assert year.attributes["faehre"] == 85


async def test_old_cost_sensors_are_removed(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    registry = er.async_get(hass)
    config_entry.add_to_hass(hass)
    old = registry.async_get_or_create(
        "sensor", DOMAIN, f"{config_entry.entry_id}_costs_month", config_entry=config_entry
    )
    hass.states.async_set("sensor.camper_dplus", "OFF")

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get(old.entity_id) is None
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{config_entry.entry_id}_travel_costs_month")


async def test_open_toll_counts_finished_trips_through_toll_countries(
    hass: HomeAssistant, coordinator: ReiseverlaufDataUpdateCoordinator
) -> None:
    italy = trip("2026-11-10 07:00:00", ("DE", "AT", "IT"))
    settled = trip("2026-11-01 07:00:00", ("FR",))
    marked = trip("2026-10-20 07:00:00", ("ES",))
    home = trip("2026-10-10 07:00:00", ("DE",))
    unknown = trip("2026-10-05 07:00:00", None)
    manual = trip("2026-10-01 07:00:00", ("AT",), automatic=False)
    old = trip("2025-10-01 07:00:00", ("AT",))
    coordinator.exports = (italy, settled, marked, home, unknown, manual, old)
    book = coordinator.logbook.logbook
    book.add_travel_cost(date(2026, 11, 1), CostCategory.TOLL, 30, trip_start=settled.start, country="FR")
    book.add_travel_cost(date(2026, 11, 10), CostCategory.FERRY, 85, trip_start=italy.start)
    book.set_no_toll(marked.start, True)
    await refresh(hass, coordinator)

    state = hass.states.get(OPEN_TOLL)
    assert state is not None
    assert state.state == "1"
    assert state.attributes["reisen"] == [
        {"titel": "Reise 10.11.", "start": italy.start.isoformat(), "ordner": italy.folder, "laender": ["AT", "IT"]}
    ]

    coordinator.exports = (replace(italy, countries=("DE",)),)
    await refresh(hass, coordinator)
    assert hass.states.get(OPEN_TOLL).state == "0"


async def test_countries_of_recent_trips_are_looked_up_one_after_the_other(
    hass: HomeAssistant, coordinator: ReiseverlaufDataUpdateCoordinator, monkeypatch: pytest.MonkeyPatch
) -> None:
    recent, known, old = (
        trip("2026-11-10 07:00:00", None),
        trip("2026-11-01 07:00:00", ("FR",)),
        trip("2025-10-01 07:00:00", None),
    )
    coordinator.exports = (recent, known, old)
    asked: list[str] = []

    async def raw_log(info: ExportInfo) -> None:
        asked.append(info.folder)

    monkeypatch.setattr(coordinator, "async_raw_log", raw_log)
    coordinator.countries.ensure_recent(dt_util.utcnow() - timedelta(days=365))
    await hass.async_block_till_done(wait_background_tasks=True)

    assert asked == [recent.folder]
