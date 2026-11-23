"""Handlers for the reisekosten_* and keine_maut actions (docs/features/feat-09-nachtraege.md 6.3)."""

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from custom_components.reiseverlauftracker.const import DOMAIN, EXPORT_CHOICE_ALL
from custom_components.reiseverlauftracker.coordinator.cost_form import travel_cost_data
from custom_components.reiseverlauftracker.coordinator.logbook import CostCategory
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .entry import ATTR_CONFIG_ENTRY_ID, get_loaded_entry

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
    from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse

ATTR_DAY = "datum"
ATTR_TRIP = "reise"
ATTR_CATEGORY = "kategorie"
ATTR_AMOUNT = "betrag"
ATTR_COUNTRY = "land"
ATTR_NOTE = "notiz"
ATTR_COST = "eintrag"
ATTR_ON = "an"


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> ReiseverlaufDataUpdateCoordinator:
    return get_loaded_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID]).runtime_data.coordinator


def _error(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=key, translation_placeholders=placeholders)


def trip_start_of(coordinator: ReiseverlaufDataUpdateCoordinator, value: str) -> datetime:
    """
    Return the start of the trip that `value` names: an export folder, its selection label or the start time.

    The running trip counts too, by its start time.

    Raises:
        ServiceValidationError: No such trip.

    """
    if value != EXPORT_CHOICE_ALL and (exports := coordinator.find_exports(value)):
        return exports[0].start
    if (parsed := dt_util.parse_datetime(value)) is not None:
        start = dt_util.as_utc(parsed if parsed.tzinfo else parsed.replace(tzinfo=dt_util.get_default_time_zone()))
        starts = {info.start for info in coordinator.exports}
        if coordinator.log is not None:
            starts.add(coordinator.log.start)
        if start in starts:
            return start
    raise _error("unknown_trip", trip=value)


def _country(value: str | None) -> str | None:
    return (value.strip().upper() or None) if value else None


async def async_handle_add(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """
    Add a travel cost for a trip, or for a day without a trip.

    Returns:
        The new cost.

    Raises:
        ServiceValidationError: Neither day nor trip, an unknown trip, or an invalid amount or country.

    """
    coordinator = _coordinator(hass, call)
    data = call.data
    trip_start = trip_start_of(coordinator, data[ATTR_TRIP]) if data.get(ATTR_TRIP) else None
    day: date | None = data.get(ATTR_DAY)
    if day is None:
        if trip_start is None:
            raise _error("travel_cost_needs_day")
        day = dt_util.as_local(trip_start).date()
    try:
        cost = await coordinator.logbook.async_add_travel_cost(
            day,
            CostCategory(data[ATTR_CATEGORY]),
            data[ATTR_AMOUNT],
            trip_start=trip_start,
            country=_country(data.get(ATTR_COUNTRY)),
            note=data.get(ATTR_NOTE),
        )
    except ValueError as err:
        raise _error("invalid_travel_cost") from err
    return {ATTR_COST: travel_cost_data(cost)}


async def async_handle_update(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """
    Change fields of a travel cost; an empty country or note removes it.

    Returns:
        The changed cost.

    Raises:
        ServiceValidationError: Unknown cost or trip, or an invalid amount or country.

    """
    coordinator = _coordinator(hass, call)
    data = call.data
    changes: dict[str, Any] = {}
    if ATTR_DAY in data:
        changes["day"] = data[ATTR_DAY]
    if ATTR_TRIP in data:
        changes["trip_start"] = trip_start_of(coordinator, data[ATTR_TRIP]) if data[ATTR_TRIP] else None
    if ATTR_CATEGORY in data:
        changes["category"] = CostCategory(data[ATTR_CATEGORY])
    if ATTR_AMOUNT in data:
        changes["amount"] = data[ATTR_AMOUNT]
    if ATTR_COUNTRY in data:
        changes["country"] = _country(data[ATTR_COUNTRY])
    if ATTR_NOTE in data:
        changes["note"] = data[ATTR_NOTE].strip() or None
    try:
        cost = await coordinator.logbook.async_update_travel_cost(data[ATTR_COST], changes)
    except KeyError as err:
        raise _error("unknown_travel_cost", entry=data[ATTR_COST]) from err
    except ValueError as err:
        raise _error("invalid_travel_cost") from err
    return {ATTR_COST: travel_cost_data(cost)}


async def async_handle_remove(hass: HomeAssistant, call: ServiceCall) -> None:
    """
    Delete a travel cost.

    Raises:
        ServiceValidationError: No cost has the given id.

    """
    coordinator = _coordinator(hass, call)
    try:
        await coordinator.logbook.async_remove_travel_cost(call.data[ATTR_COST])
    except KeyError as err:
        raise _error("unknown_travel_cost", entry=call.data[ATTR_COST]) from err


async def async_handle_no_toll(hass: HomeAssistant, call: ServiceCall) -> None:
    """Mark a trip as having no toll, or remove the mark."""
    coordinator = _coordinator(hass, call)
    trip_start = trip_start_of(coordinator, call.data[ATTR_TRIP])
    await coordinator.logbook.async_set_no_toll(trip_start, call.data[ATTR_ON])
