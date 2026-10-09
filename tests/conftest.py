"""Shared fixtures for the reiseverlauftracker tests."""

from typing import Any

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
