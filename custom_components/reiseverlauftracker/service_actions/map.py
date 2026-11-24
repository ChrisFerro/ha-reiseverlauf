"""Handler for the karte_neu_zeichnen action (docs/features/feat-12-kartensymbole.md 6.8)."""

from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.const import DOMAIN
from custom_components.reiseverlauftracker.coordinator.map_redraw import RedrawError, async_redraw_map
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .entry import ATTR_CONFIG_ENTRY_ID, get_loaded_entry
from .export import ATTR_EXPORT

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse


def redraw_error(err: RedrawError) -> HomeAssistantError:
    """Return the error shown for a map that cannot be drawn anew."""
    kind = ServiceValidationError if err.invalid else HomeAssistantError
    return kind(translation_domain=DOMAIN, translation_key=err.key, translation_placeholders=err.placeholders)


async def async_handle_redraw_map(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """
    Draw the map of one export anew with tiles; without an export, the export selection's choice.

    Returns:
        The folder and title of the export and how many ferry crossings were found.

    Raises:
        HomeAssistantError: No single export chosen, no raw data left, or drawing failed.

    """
    coordinator = get_loaded_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID]).runtime_data.coordinator
    try:
        result = await async_redraw_map(coordinator, call.data.get(ATTR_EXPORT) or None)
    except RedrawError as err:
        raise redraw_error(err) from err
    return {"ordner": result.info.folder, "titel": result.info.title, "faehren_erkannt": result.ferries_found}
