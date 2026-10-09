"""
Custom integration that records motorhome trips in Home Assistant.

For more details about this integration, please refer to:
https://github.com/ChrisFerro/ha-reiseverlauf
"""

from typing import TYPE_CHECKING

from homeassistant.const import Platform
import homeassistant.helpers.config_validation as cv
from homeassistant.loader import async_get_loaded_integration

from .const import DOMAIN
from .coordinator import ReiseverlaufDataUpdateCoordinator
from .data import ReiseverlaufData
from .settings import ReiseverlaufSettings

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import ReiseverlaufConfigEntry

PLATFORMS: list[Platform] = []

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
) -> bool:
    """
    Set up a config entry.

    Returns:
        True once trip detection runs and every platform is forwarded.

    """
    settings = ReiseverlaufSettings.from_entry(entry.data, entry.options)
    coordinator = ReiseverlaufDataUpdateCoordinator(hass, entry, settings)
    entry.runtime_data = ReiseverlaufData(
        settings=settings,
        coordinator=coordinator,
        integration=async_get_loaded_integration(hass, entry.domain),
    )
    await coordinator.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
) -> bool:
    """
    Unload a config entry.

    Returns:
        True if every platform unloaded cleanly.

    """
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.coordinator.async_stop()
    return unloaded


async def async_reload_entry(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
) -> None:
    """Reload the config entry after its data or options changed."""
    await hass.config_entries.async_reload(entry.entry_id)
