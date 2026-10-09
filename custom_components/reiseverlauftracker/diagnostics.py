"""
Diagnostics support for reiseverlauftracker.

https://developers.home-assistant.io/docs/core/integration_diagnostics
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import ReiseverlaufConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
) -> dict[str, Any]:
    """
    Return diagnostics for a config entry.

    Returns:
        The entry configuration; it holds entity IDs and thresholds, nothing secret.

    """
    return {
        "entry": {
            "version": entry.version,
            "minor_version": entry.minor_version,
            "state": str(entry.state),
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
    }
