"""Service action registration for reiseverlauftracker."""

from typing import TYPE_CHECKING, Any

import voluptuous as vol

from custom_components.reiseverlauftracker.const import DOMAIN
from custom_components.reiseverlauftracker.export import ExportFile
from homeassistant.core import SupportsResponse
from homeassistant.helpers import config_validation as cv

from .entry import ATTR_CONFIG_ENTRY_ID
from .export import (
    ATTR_END,
    ATTR_EXPORT,
    ATTR_FILE_TYPES,
    ATTR_MARGIN,
    ATTR_SCALE,
    ATTR_START,
    ATTR_TITLE,
    async_handle_cleanup,
    async_handle_export,
)
from .trip import async_handle_end_trip, async_handle_start_trip

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse

SERVICE_CLEANUP = "aufraeumen"
SERVICE_END_TRIP = "reise_beenden"
SERVICE_EXPORT = "exportieren"
SERVICE_START_TRIP = "reise_starten"

ENTRY_SCHEMA = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string})

EXPORT_SCHEMA = ENTRY_SCHEMA.extend(
    {
        vol.Required(ATTR_START): cv.datetime,
        vol.Required(ATTR_END): cv.datetime,
        vol.Optional(ATTR_TITLE): cv.string,
        vol.Optional(ATTR_SCALE): vol.All(vol.Coerce(float), vol.Range(min=1, max=4)),
        vol.Optional(ATTR_MARGIN): vol.All(vol.Coerce(float), vol.Range(min=0, max=120)),
    }
)

CLEANUP_SCHEMA = ENTRY_SCHEMA.extend(
    {
        vol.Optional(ATTR_EXPORT): cv.string,
        vol.Optional(ATTR_FILE_TYPES, default=[kind.value for kind in ExportFile]): vol.All(
            cv.ensure_list, [vol.In([kind.value for kind in ExportFile])], vol.Length(min=1)
        ),
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the service actions of the integration once, at component level."""

    async def handle_export(call: ServiceCall) -> ServiceResponse:
        return await async_handle_export(hass, call)

    async def handle_cleanup(call: ServiceCall) -> ServiceResponse:
        return await async_handle_cleanup(hass, call)

    async def handle_start_trip(call: ServiceCall) -> None:
        await async_handle_start_trip(hass, call)

    async def handle_end_trip(call: ServiceCall) -> None:
        await async_handle_end_trip(hass, call)

    actions: tuple[tuple[str, Any, vol.Schema, SupportsResponse], ...] = (
        (SERVICE_EXPORT, handle_export, EXPORT_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_CLEANUP, handle_cleanup, CLEANUP_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_START_TRIP, handle_start_trip, ENTRY_SCHEMA, SupportsResponse.NONE),
        (SERVICE_END_TRIP, handle_end_trip, ENTRY_SCHEMA, SupportsResponse.NONE),
    )
    for name, handler, schema, supports_response in actions:
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handler, schema=schema, supports_response=supports_response)
