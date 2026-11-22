"""
Custom integration that records motorhome trips in Home Assistant.

For more details about this integration, please refer to:
https://github.com/ChrisFerro/ha-reiseverlauf
"""

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv
from homeassistant.loader import async_get_loaded_integration

from .const import DOMAIN
from .coordinator import ReiseverlaufDataUpdateCoordinator
from .data import ReiseverlaufData
from .download import async_register_views
from .sensor.logbook import REMOVED_KEYS
from .service_actions import async_setup_services
from .settings import ReiseverlaufSettings

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import ReiseverlaufConfigEntry

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DATE,
    Platform.DATETIME,
    Platform.IMAGE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.TEXT,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """
    Register the service actions and the download views.

    Returns:
        True once the actions and views are registered.

    """
    await async_setup_services(hass)
    async_register_views(hass)
    return True


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
    _remove_replaced_entities(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


def _remove_replaced_entities(hass: HomeAssistant, entry: ReiseverlaufConfigEntry) -> None:
    """Remove entities of earlier versions that new ones with another unique ID replace."""
    registry = er.async_get(hass)
    for key in REMOVED_KEYS:
        if (entity_id := registry.async_get_entity_id(Platform.SENSOR, DOMAIN, f"{entry.entry_id}_{key}")) is not None:
            registry.async_remove(entity_id)


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
