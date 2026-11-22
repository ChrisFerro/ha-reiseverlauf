"""Service action registration for reiseverlauftracker."""

from typing import TYPE_CHECKING, Any

import probatio

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
from .logbook import (
    ATTR_ENTRY,
    ATTR_FUEL,
    ATTR_FUEL_AMOUNT,
    ATTR_FUEL_LITRES,
    ATTR_GAS_1,
    ATTR_GAS_2,
    ATTR_GAS_AMOUNT,
    ATTR_GAS_LITRES,
    ATTR_OCCASION_TIME,
    ATTR_ODOMETER,
    ATTR_TIME,
    async_handle_add,
    async_handle_csv,
    async_handle_late,
    async_handle_remove,
    async_handle_save_form,
    async_handle_update,
)
from .trip import async_handle_end_trip, async_handle_start_trip

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse

SERVICE_CLEANUP = "aufraeumen"
SERVICE_END_TRIP = "reise_beenden"
SERVICE_EXPORT = "exportieren"
SERVICE_START_TRIP = "reise_starten"
SERVICE_LOGBOOK_ADD = "fahrtenbuch_eintragen"
SERVICE_LOGBOOK_UPDATE = "fahrtenbuch_aendern"
SERVICE_LOGBOOK_REMOVE = "fahrtenbuch_loeschen"
SERVICE_LOGBOOK_CSV = "fahrtenbuch_csv"
SERVICE_LOGBOOK_SAVE_FORM = "fahrtenbuch_speichern"
SERVICE_LOGBOOK_LATE = "fahrtenbuch_nachtragen"

ENTRY_SCHEMA = probatio.Schema({probatio.Required(ATTR_CONFIG_ENTRY_ID): cv.string})

EXPORT_SCHEMA = ENTRY_SCHEMA.extend(
    {
        probatio.Required(ATTR_START): cv.datetime,
        probatio.Required(ATTR_END): cv.datetime,
        probatio.Optional(ATTR_TITLE): cv.string,
        probatio.Optional(ATTR_SCALE): probatio.All(probatio.Coerce(float), probatio.Range(min=1, max=4)),
        probatio.Optional(ATTR_MARGIN): probatio.All(probatio.Coerce(float), probatio.Range(min=0, max=120)),
    }
)

CLEANUP_SCHEMA = ENTRY_SCHEMA.extend(
    {
        probatio.Optional(ATTR_EXPORT): cv.string,
        probatio.Optional(ATTR_FILE_TYPES, default=[kind.value for kind in ExportFile]): probatio.All(
            cv.ensure_list, [probatio.In([kind.value for kind in ExportFile])], probatio.Length(min=1)
        ),
    }
)


def _range(maximum: float) -> Any:
    return probatio.All(probatio.Coerce(float), probatio.Range(min=0, max=maximum))


LOGBOOK_FIELDS = {
    probatio.Optional(ATTR_TIME): cv.datetime,
    probatio.Optional(ATTR_ODOMETER): _range(9_999_999),
    probatio.Optional(ATTR_FUEL): _range(100),
    probatio.Optional(ATTR_GAS_1): _range(100),
    probatio.Optional(ATTR_GAS_2): _range(100),
    probatio.Optional(ATTR_FUEL_LITRES): _range(1000),
    probatio.Optional(ATTR_FUEL_AMOUNT): _range(10000),
    probatio.Optional(ATTR_GAS_LITRES): _range(1000),
    probatio.Optional(ATTR_GAS_AMOUNT): _range(10000),
}
LOGBOOK_ADD_SCHEMA = ENTRY_SCHEMA.extend(LOGBOOK_FIELDS)
LOGBOOK_ENTRY_SCHEMA = ENTRY_SCHEMA.extend({probatio.Required(ATTR_ENTRY): cv.string})
LOGBOOK_UPDATE_SCHEMA = LOGBOOK_ENTRY_SCHEMA.extend(LOGBOOK_FIELDS)
LOGBOOK_SAVE_FORM_SCHEMA = ENTRY_SCHEMA.extend({probatio.Optional(ATTR_OCCASION_TIME): cv.datetime})
LOGBOOK_LATE_SCHEMA = ENTRY_SCHEMA.extend(
    {
        probatio.Required(ATTR_TIME): cv.datetime,
        probatio.Optional(ATTR_ODOMETER): _range(9_999_999),
        probatio.Optional(ATTR_FUEL_LITRES): _range(1000),
        probatio.Optional(ATTR_FUEL_AMOUNT): _range(10000),
        probatio.Optional(ATTR_GAS_LITRES): _range(1000),
        probatio.Optional(ATTR_GAS_AMOUNT): _range(10000),
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

    async def handle_logbook_add(call: ServiceCall) -> ServiceResponse:
        return await async_handle_add(hass, call)

    async def handle_logbook_save_form(call: ServiceCall) -> ServiceResponse:
        return await async_handle_save_form(hass, call)

    async def handle_logbook_update(call: ServiceCall) -> ServiceResponse:
        return await async_handle_update(hass, call)

    async def handle_logbook_remove(call: ServiceCall) -> None:
        await async_handle_remove(hass, call)

    async def handle_logbook_csv(call: ServiceCall) -> ServiceResponse:
        return await async_handle_csv(hass, call)

    async def handle_logbook_late(call: ServiceCall) -> ServiceResponse:
        return await async_handle_late(hass, call)

    actions: tuple[tuple[str, Any, probatio.Schema, SupportsResponse], ...] = (
        (SERVICE_EXPORT, handle_export, EXPORT_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_CLEANUP, handle_cleanup, CLEANUP_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_START_TRIP, handle_start_trip, ENTRY_SCHEMA, SupportsResponse.NONE),
        (SERVICE_END_TRIP, handle_end_trip, ENTRY_SCHEMA, SupportsResponse.NONE),
        (SERVICE_LOGBOOK_ADD, handle_logbook_add, LOGBOOK_ADD_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_LOGBOOK_SAVE_FORM, handle_logbook_save_form, LOGBOOK_SAVE_FORM_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_LOGBOOK_UPDATE, handle_logbook_update, LOGBOOK_UPDATE_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_LOGBOOK_REMOVE, handle_logbook_remove, LOGBOOK_ENTRY_SCHEMA, SupportsResponse.NONE),
        (SERVICE_LOGBOOK_CSV, handle_logbook_csv, ENTRY_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_LOGBOOK_LATE, handle_logbook_late, LOGBOOK_LATE_SCHEMA, SupportsResponse.OPTIONAL),
    )
    for name, handler, schema, supports_response in actions:
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handler, schema=schema, supports_response=supports_response)
