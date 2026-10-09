"""Tests for the config entry diagnostics."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reiseverlauftracker.diagnostics import async_get_config_entry_diagnostics
from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant


async def test_diagnostics_redact_positions(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    hass.states.async_set("sensor.camper_dplus", "ON")
    hass.states.async_set("device_tracker.camper_gps", "not_home", {"latitude": 50.0, "longitude": 8.0})
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, config_entry)

    assert result["trip"]["status"] == "unterwegs"
    assert result["trip"]["recorded_positions"] == 1
    assert result["detector"]["last_position"] == REDACTED
    assert result["detector"]["start_position"] == REDACTED
    assert "50.0" not in str(result)
    assert result["exports"] == []
