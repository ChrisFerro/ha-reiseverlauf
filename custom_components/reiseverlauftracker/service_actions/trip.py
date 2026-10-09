"""Handlers for the reise_starten and reise_beenden actions."""

from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.const import DOMAIN
from homeassistant.exceptions import ServiceValidationError

from .entry import ATTR_CONFIG_ENTRY_ID, get_loaded_entry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall


async def async_handle_start_trip(hass: HomeAssistant, call: ServiceCall) -> None:
    """
    Start a trip, or continue the ended one, without D+.

    Raises:
        ServiceValidationError: A trip is already running.

    """
    coordinator = get_loaded_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID]).runtime_data.coordinator
    if coordinator.data.active:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="trip_running")
    coordinator.async_start_trip()


async def async_handle_end_trip(hass: HomeAssistant, call: ServiceCall) -> None:
    """
    End the running trip now; the export follows as after an automatic end.

    Raises:
        ServiceValidationError: No trip is running.

    """
    coordinator = get_loaded_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID]).runtime_data.coordinator
    if not coordinator.data.active:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_trip")
    coordinator.async_end_trip()
