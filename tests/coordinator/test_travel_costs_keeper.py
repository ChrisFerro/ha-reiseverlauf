"""Tests for storing travel costs in the logbook keeper and writing their CSV file."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from custom_components.reiseverlauftracker.coordinator.logbook import CostCategory
from custom_components.reiseverlauftracker.coordinator.logbook_keeper import LogbookKeeper
from homeassistant.core import HomeAssistant

TRIP = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)
STORE_KEY = "reiseverlauftracker.x.logbook"


@pytest.fixture
async def keeper(hass: HomeAssistant, tmp_path: Path) -> LogbookKeeper:
    """Return an empty keeper that knows one trip title."""
    hass.config.language = "de"
    keeper = LogbookKeeper(hass, "x", 90, tmp_path, trip_titles=lambda: {TRIP: "Ulm – Bozen"})
    await keeper.async_load()
    return keeper


async def test_costs_are_written_to_their_csv(keeper: LogbookKeeper) -> None:
    await keeper.async_add_travel_cost(TRIP.date(), CostCategory.TOLL, 23.4, trip_start=TRIP, country="AT")
    italy = await keeper.async_add_travel_cost(TRIP.date(), CostCategory.TOLL, 61.1, trip_start=TRIP, country="IT")
    await keeper.async_add_travel_cost(date(2026, 11, 5), CostCategory.PITCH, 18, note="Seeblick")

    lines = keeper.travel_csv_path.read_text(encoding="utf-8-sig").splitlines()
    assert lines[0].startswith("Datum;Reise;Titel;Kategorie;Land")
    assert len(lines) == 4
    assert "Ulm – Bozen" in lines[1]
    assert "23,40" in lines[1]
    assert lines[3].endswith(";18,00;Seeblick")
    assert italy.recorded is not None

    changed = await keeper.async_update_travel_cost(italy.id, {"amount": 59.9})
    assert changed.amount == 59.9
    assert "59,90" in keeper.travel_csv_path.read_text(encoding="utf-8-sig")

    await keeper.async_remove_travel_cost(italy.id)
    assert len(keeper.travel_csv_path.read_text(encoding="utf-8-sig").splitlines()) == 3
    with pytest.raises(KeyError):
        await keeper.async_remove_travel_cost(italy.id)


async def test_invalid_costs_are_rejected(keeper: LogbookKeeper) -> None:
    with pytest.raises(ValueError):
        await keeper.async_add_travel_cost(TRIP.date(), CostCategory.TOLL, 0)
    with pytest.raises(ValueError):
        await keeper.async_add_travel_cost(TRIP.date(), CostCategory.TOLL, 5, country="Austria")
    assert not keeper.travel_csv_path.exists()


async def test_costs_and_no_toll_mark_survive_a_restart(
    hass: HomeAssistant, keeper: LogbookKeeper, tmp_path: Path, hass_storage: dict[str, Any]
) -> None:
    await keeper.async_add_travel_cost(TRIP.date(), CostCategory.FERRY, 85, trip_start=TRIP)
    later = datetime(2026, 11, 9, 7, 0, tzinfo=UTC)
    await keeper.async_set_no_toll(later, True)
    await keeper.async_save_now()
    assert STORE_KEY in hass_storage

    restored = LogbookKeeper(hass, "x", 90, tmp_path)
    await restored.async_load()

    [cost] = restored.logbook.travel_costs_of_trip(TRIP)
    assert (cost.category, cost.amount) == (CostCategory.FERRY, 85)
    assert restored.logbook.toll_settled(later)
    assert not restored.logbook.toll_settled(TRIP)
