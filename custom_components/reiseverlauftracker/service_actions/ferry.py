"""Handler for the faehre_markieren action (docs/features/feat-12-kartensymbole.md 6.3)."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from custom_components.reiseverlauftracker.const import DOMAIN
from custom_components.reiseverlauftracker.coordinator.ferries import FerryChange, FerryError
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .entry import ATTR_CONFIG_ENTRY_ID, get_loaded_entry
from .travel_costs import ATTR_TRIP, trip_start_of

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
    from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse

ATTR_STOP = "halt"
ATTR_FERRY = "faehre"


async def async_handle_mark_ferry(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """
    Mark a stop as ferry crossing, or remove the mark; the trip's export is renewed.

    Returns:
        The stop and how the trip's distance changed.

    Raises:
        ServiceValidationError: Unknown trip or stop, or no raw data left.

    """
    coordinator = get_loaded_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID]).runtime_data.coordinator
    time = dt_util.as_utc(call.data[ATTR_STOP])
    trip = call.data.get(ATTR_TRIP)
    trip_start = trip_start_of(coordinator, trip) if trip else _trip_containing(coordinator, time)
    try:
        change = await coordinator.ferries.async_mark(trip_start, time, call.data[ATTR_FERRY])
    except FerryError as err:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key=err.reason) from err
    return ferry_data(change)


def ferry_data(change: FerryChange) -> dict[str, Any]:
    """Return the changed stop as response data."""
    return {
        "halt": change.stop.start.isoformat(),
        "faehre": change.stop.is_ferry,
        "strecke_km_aenderung": round(change.delta.distance_m / 1000, 1),
    }


def _trip_containing(coordinator: ReiseverlaufDataUpdateCoordinator, time: datetime) -> datetime:
    """
    Return the start of the trip during which `time` lies: the running one or an automatic export.

    Raises:
        ServiceValidationError: No trip contains `time`.

    """
    log = coordinator.log
    if log is not None and log.start <= time:
        return log.start
    trips = [i for i in coordinator.exports if i.automatic and not i.is_tour and i.start <= time <= i.end]
    if not trips:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="unknown_stop")
    return max(trips, key=lambda i: i.start).start
