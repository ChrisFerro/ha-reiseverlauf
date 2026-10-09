"""Resolve the config entry a service action targets."""

from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.data import ReiseverlaufConfigEntry
    from homeassistant.core import HomeAssistant

ATTR_CONFIG_ENTRY_ID = "config_entry_id"


def get_loaded_entry(hass: HomeAssistant, entry_id: str) -> ReiseverlaufConfigEntry:
    """
    Resolve a config entry id to a loaded entry of this integration.

    Returns:
        The loaded config entry.

    Raises:
        ServiceValidationError: If the entry is unknown or not loaded.

    """
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found",
            translation_placeholders={"target": entry_id},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"target": entry.title},
        )
    return entry
