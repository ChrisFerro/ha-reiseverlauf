"""Handlers for the fahrtenbuch_* actions: add, change and delete entries, write the CSV file."""

from typing import TYPE_CHECKING, Any

from custom_components.reiseverlauftracker.const import DOMAIN
from custom_components.reiseverlauftracker.coordinator.export_runner import MEDIA_SOURCE_DIR
from custom_components.reiseverlauftracker.coordinator.logbook import LogbookEntry, Refill
from custom_components.reiseverlauftracker.coordinator.logbook_keeper import CSV_NAME, entry_data
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

from .entry import ATTR_CONFIG_ENTRY_ID, get_loaded_entry

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
    from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse

ATTR_ENTRY = "eintrag"
ATTR_OCCASION_TIME = "anlass_zeit"
ATTR_TIME = "zeit"
ATTR_ODOMETER = "kilometerstand"
ATTR_FUEL = "kraftstoff"
ATTR_GAS_1 = "gas_1"
ATTR_GAS_2 = "gas_2"
ATTR_FUEL_LITRES = "diesel_liter"
ATTR_FUEL_AMOUNT = "diesel_betrag"
ATTR_GAS_LITRES = "gas_liter"
ATTR_GAS_AMOUNT = "gas_betrag"

LEVEL_FIELDS = {
    ATTR_ODOMETER: "odometer_km",
    ATTR_FUEL: "fuel_percent",
    ATTR_GAS_1: "gas1_percent",
    ATTR_GAS_2: "gas2_percent",
}
REFILL_FIELDS = {"fuel": (ATTR_FUEL_LITRES, ATTR_FUEL_AMOUNT), "gas": (ATTR_GAS_LITRES, ATTR_GAS_AMOUNT)}


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> ReiseverlaufDataUpdateCoordinator:
    return get_loaded_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID]).runtime_data.coordinator


def _changes(data: dict[str, Any], current: LogbookEntry | None = None) -> dict[str, Any]:
    """
    Translate action fields into entry fields.

    Litres of 0 remove a refill; an amount alone changes the amount of the
    existing refill.

    Raises:
        ServiceValidationError: An amount is given without litres for an entry without that refill.

    """
    changes: dict[str, Any] = {LEVEL_FIELDS[key]: value for key, value in data.items() if key in LEVEL_FIELDS}
    if ATTR_TIME in data:
        changes["time"] = dt_util.as_utc(data[ATTR_TIME])
    for name, (litres_key, amount_key) in REFILL_FIELDS.items():
        if litres_key not in data and amount_key not in data:
            continue
        existing: Refill | None = getattr(current, name) if current else None
        litres = data.get(litres_key, existing.litres if existing else None)
        if litres is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="amount_without_litres", translation_placeholders={}
            )
        amount = data.get(amount_key, existing.amount if existing else None)
        changes[name] = Refill(litres, amount or None) if litres > 0 else None
    return changes


async def async_handle_add(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """
    Add a manual logbook entry.

    Returns:
        The new entry.

    """
    coordinator = _coordinator(hass, call)
    context = await coordinator.async_logbook_context()
    entry = await coordinator.logbook.async_add(_changes(dict(call.data)), context)
    return {ATTR_ENTRY: entry_data(entry)}


async def async_handle_save_form(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """
    Save the logbook form, like the save button.

    With `anlass_zeit`, only while that occasion is still pending: a tap on an
    old notification must not save the form for a later occasion or as a
    manual entry.

    Returns:
        The new entry.

    Raises:
        ServiceValidationError: The given occasion is no longer pending.

    """
    coordinator = _coordinator(hass, call)
    if ATTR_OCCASION_TIME in call.data:
        pending = coordinator.logbook.pending
        occasion_time = dt_util.as_utc(call.data[ATTR_OCCASION_TIME])
        if pending is None or pending.time != occasion_time:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="logbook_occasion_not_pending",
                translation_placeholders={"time": occasion_time.isoformat()},
            )
    entry = await coordinator.async_save_logbook_form()
    return {ATTR_ENTRY: entry_data(entry)}


async def async_handle_late(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """
    Add a refill at an earlier time; a remembered stop close to that time is taken as its stop.

    Returns:
        The new or completed entry.

    Raises:
        ServiceValidationError: Neither litres are given, or the odometer at that time is unknown and not given.

    """
    data = dict(call.data)
    refills = {name: _refill(data, litres, amount) for name, (litres, amount) in REFILL_FIELDS.items()}
    if not any(refills.values()):
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="late_without_refill")
    try:
        entry = await _coordinator(hass, call).late_form.async_add(
            data[ATTR_TIME], odometer_km=data.get(ATTR_ODOMETER), **refills
        )
    except ValueError as err:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="late_odometer_required") from err
    return {ATTR_ENTRY: entry_data(entry)}


def _refill(data: dict[str, Any], litres_key: str, amount_key: str) -> Refill | None:
    """Return the refill of the action fields, or None without litres."""
    litres = data.get(litres_key) or 0
    return Refill(litres, data.get(amount_key) or None) if litres > 0 else None


async def async_handle_update(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """
    Change fields of a logbook entry; a new time also brings the counters and place of that time.

    Returns:
        The changed entry.

    Raises:
        ServiceValidationError: No entry has the given id.

    """
    coordinator = _coordinator(hass, call)
    keeper = coordinator.logbook
    entry_id = call.data[ATTR_ENTRY]
    if (current := keeper.logbook.get(entry_id)) is None:
        raise _unknown(entry_id)
    changes = _changes(dict(call.data), current)
    if "time" in changes:
        changes |= await coordinator.late_form.async_moved(current, changes["time"])
    entry = await keeper.async_update(entry_id, changes)
    return {ATTR_ENTRY: entry_data(entry)}


async def async_handle_remove(hass: HomeAssistant, call: ServiceCall) -> None:
    """
    Delete a logbook entry.

    Raises:
        ServiceValidationError: No entry has the given id.

    """
    keeper = _coordinator(hass, call).logbook
    entry_id = call.data[ATTR_ENTRY]
    try:
        await keeper.async_remove(entry_id)
    except KeyError as err:
        raise _unknown(entry_id) from err


async def async_handle_csv(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """
    Write the CSV file of the logbook.

    Returns:
        Path and media URL of the file.

    Raises:
        HomeAssistantError: The file could not be written.

    """
    coordinator = _coordinator(hass, call)
    try:
        path = await coordinator.logbook.async_write_csv()
    except OSError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="csv_failed", translation_placeholders={"error": str(err)}
        ) from err
    return {
        "pfad": str(path),
        "url": f"/media/{MEDIA_SOURCE_DIR}/{coordinator.settings.output_dir}/{CSV_NAME}",
        "eintraege": len(coordinator.logbook.logbook.entries),
    }


def _unknown(entry_id: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN, translation_key="logbook_entry_not_found", translation_placeholders={"id": entry_id}
    )
