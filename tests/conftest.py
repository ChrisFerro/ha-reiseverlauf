"""Shared fixtures for the reiseverlauftracker tests."""

from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reiseverlauftracker.const import (
    CONF_ALTITUDE_ENTITY,
    CONF_DPLUS_ENTITY,
    CONF_DPLUS_ON_VALUE,
    CONF_OUTPUT_DIR,
    CONF_SPEED_ENTITY,
    CONF_TRACKER_ENTITY,
    DOMAIN,
)
from homeassistant.core import HomeAssistant

TRACKER = "device_tracker.camper_gps"

ENTRY_DATA: dict[str, Any] = {
    CONF_DPLUS_ENTITY: "sensor.camper_dplus",
    CONF_DPLUS_ON_VALUE: "ON",
    CONF_TRACKER_ENTITY: TRACKER,
    CONF_SPEED_ENTITY: "sensor.camper_speed",
    CONF_ALTITUDE_ENTITY: "sensor.camper_altitude",
    CONF_OUTPUT_DIR: "reiseverlauf",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom integrations in every test."""


@pytest.fixture(autouse=True)
def media_dir(hass: HomeAssistant, tmp_path: Path) -> Path:
    """Point the local media directory at a temporary folder."""
    hass.config.media_dirs = {"local": str(tmp_path)}
    return tmp_path


@pytest.fixture(autouse=True)
def no_tiles() -> Generator[None]:
    """Render maps from blank tiles instead of downloading them."""
    with patch(
        "custom_components.reiseverlauftracker.export.exporter.http_tile_fetcher",
        return_value=lambda _url: None,
    ):
        yield


def _fake_place(_session: Any, lat: float, _lon: float, _language: str, _user_agent: str) -> str:
    """Name the start point of the test tracks "Startort" and every other place "Zielort"."""
    return "Startort" if lat < 50.0001 else "Zielort"


@pytest.fixture(autouse=True)
def geocode() -> Generator[AsyncMock]:
    """Answer place-name lookups by position instead of asking Nominatim."""
    with (
        patch(
            "custom_components.reiseverlauftracker.coordinator.places.async_reverse_geocode",
            side_effect=_fake_place,
        ) as mock,
        patch("custom_components.reiseverlauftracker.coordinator.export_runner.NOMINATIM_INTERVAL_S", 0),
    ):
        yield mock


@pytest.fixture
def entry_data() -> dict[str, Any]:
    """Return the data a set-up entry holds."""
    return dict(ENTRY_DATA)


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry for this integration."""
    return MockConfigEntry(domain=DOMAIN, title="Camper GPS", unique_id=TRACKER, data=ENTRY_DATA)


@pytest.fixture
async def init_integration(hass: HomeAssistant, config_entry: MockConfigEntry) -> MockConfigEntry:
    """
    Set up the integration from a config entry.

    Returns:
        The config entry, now loaded.

    """
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
