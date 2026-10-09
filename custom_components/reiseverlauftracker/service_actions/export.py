"""Handlers for the exportieren and aufraeumen actions."""

from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.const import DOMAIN
from custom_components.reiseverlauftracker.export import ExportFile, NoMovementError, NotEnoughPointsError
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util
from homeassistant.util.json import JsonValueType

from .entry import ATTR_CONFIG_ENTRY_ID, get_loaded_entry
from .history import async_load_period

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse

ATTR_END = "bis"
ATTR_EXPORT = "export"
ATTR_FILE_TYPES = "dateitypen"
ATTR_MARGIN = "rand_min"
ATTR_SCALE = "skala"
ATTR_START = "von"
ATTR_TITLE = "titel"  # codespell:ignore titel


async def async_handle_export(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """
    Export any period from the recorder history.

    Returns:
        The same data as the reiseverlauftracker_exportiert event.

    Raises:
        ServiceValidationError: Bad period, or no movement in it.
        HomeAssistantError: The recorder is not running or the export failed.

    """
    entry = get_loaded_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID])
    start = dt_util.as_utc(call.data[ATTR_START])
    end = dt_util.as_utc(call.data[ATTR_END])
    if end <= start:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_period")
    if "recorder" not in hass.config.components:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="recorder_missing")

    coordinator = entry.runtime_data.coordinator
    settings = coordinator.settings
    if ATTR_SCALE in call.data:
        settings = replace(settings, scale=float(call.data[ATTR_SCALE]))
    if ATTR_MARGIN in call.data:
        settings = replace(settings, margin=timedelta(minutes=float(call.data[ATTR_MARGIN])))

    data = await async_load_period(hass, settings, start, end)
    try:
        return await coordinator.async_export_period(data, start, end, settings, call.data.get(ATTR_TITLE) or None)
    except (NotEnoughPointsError, NoMovementError) as err:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_movement") from err
    except OSError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="export_failed",
            translation_placeholders={"error": str(err)},
        ) from err


async def async_handle_cleanup(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """
    Delete chosen file types of one export or of all exports.

    Without an export, the current choice of the export selection entity applies.

    Returns:
        The folders that were touched.

    Raises:
        ServiceValidationError: The export does not exist.
        HomeAssistantError: The files could not be deleted.

    """
    entry = get_loaded_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID])
    coordinator = entry.runtime_data.coordinator
    choice = call.data.get(ATTR_EXPORT) or coordinator.current_export_choice()
    if choice is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_export_chosen")
    exports = coordinator.find_exports(choice)
    if not exports and coordinator.exports:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="export_not_found",
            translation_placeholders={"export": choice},
        )
    kinds = {ExportFile(kind) for kind in call.data[ATTR_FILE_TYPES]}
    try:
        await coordinator.async_remove_files(exports, kinds)
    except OSError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="cleanup_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    folders: list[JsonValueType] = [info.folder for info in exports]
    file_types: list[JsonValueType] = [kind.value for kind in sorted(kinds)]
    return {"ordner": folders, "dateitypen": file_types}  # codespell:ignore ordner
