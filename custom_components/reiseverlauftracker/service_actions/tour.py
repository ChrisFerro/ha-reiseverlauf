"""Handlers for the tour_erstellen and tour_aendern actions (docs/features/feat-10-tour.md 6.2)."""

from datetime import date
from typing import TYPE_CHECKING, Any

from custom_components.reiseverlauftracker.const import DOMAIN
from custom_components.reiseverlauftracker.coordinator.tours import (
    OCCASION_CREATED,
    OCCASION_UPDATED,
    TourError,
    event_data,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

from .entry import ATTR_CONFIG_ENTRY_ID, get_loaded_entry
from .export import ATTR_END, ATTR_EXPORT, ATTR_SCALE, ATTR_START, ATTR_TITLE

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.coordinator.exports import ExportInfo
    from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse

ATTR_PLACES = "standorte"
ATTR_NIGHT = "nacht"
ATTR_NAME = "name"


def _error(err: TourError) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN, translation_key=err.key, translation_placeholders=err.placeholders
    )


def _write_error(err: OSError) -> HomeAssistantError:
    return HomeAssistantError(
        translation_domain=DOMAIN, translation_key="export_failed", translation_placeholders={"error": str(err)}
    )


async def async_handle_create(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """
    Create a tour of all trips that start in the period.

    Returns:
        The same data as the reiseverlauftracker_tour event.

    Raises:
        ServiceValidationError: Bad period, no trips, or a trip without raw data.
        HomeAssistantError: The files could not be written.

    """
    coordinator = get_loaded_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID]).runtime_data.coordinator
    start, end = dt_util.as_utc(call.data[ATTR_START]), dt_util.as_utc(call.data[ATTR_END])
    scale = float(call.data[ATTR_SCALE]) if ATTR_SCALE in call.data else None
    try:
        info = await coordinator.tours.async_create(start, end, call.data.get(ATTR_TITLE) or None, scale)
    except TourError as err:
        raise _error(err) from err
    except OSError as err:
        raise _write_error(err) from err
    return event_data(coordinator, info, OCCASION_CREATED)


async def async_handle_change(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """
    Change title, period or night place names of a tour and create it anew.

    Without an export, the tour chosen in the export selection is changed.

    Returns:
        The same data as the reiseverlauftracker_tour event.

    Raises:
        ServiceValidationError: No such tour, a bad period, or a new trip without raw data.
        HomeAssistantError: The files could not be written.

    """
    coordinator = get_loaded_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID]).runtime_data.coordinator
    choice = call.data.get(ATTR_EXPORT) or coordinator.current_export_choice()
    tours: list[ExportInfo] = [i for i in coordinator.find_exports(choice) if i.is_tour] if choice else []
    if not tours:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="tour_not_found",
            translation_placeholders={"export": choice or ""},
        )
    data: dict[str, Any] = call.data
    names: dict[date, str] = {place[ATTR_NIGHT]: place[ATTR_NAME] for place in data.get(ATTR_PLACES, [])}
    try:
        info = await coordinator.tours.async_change(
            tours[0],
            title=data.get(ATTR_TITLE),
            start=dt_util.as_utc(data[ATTR_START]) if ATTR_START in data else None,
            end=dt_util.as_utc(data[ATTR_END]) if ATTR_END in data else None,
            names=names or None,
        )
    except TourError as err:
        raise _error(err) from err
    except OSError as err:
        raise _write_error(err) from err
    return event_data(coordinator, info, OCCASION_UPDATED)
