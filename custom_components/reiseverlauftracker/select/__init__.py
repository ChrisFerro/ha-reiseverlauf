"""Select platform for reiseverlauftracker."""

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntityDescription

from .cost_choice import ReiseverlaufCostCategory, ReiseverlaufCostCountry
from .export_choice import ReiseverlaufExportChoice
from .logbook_edit import ReiseverlaufLogbookClear, ReiseverlaufLogbookEdit
from .logbook_time import ReiseverlaufLogbookTime

PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.data import ReiseverlaufConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

EXPORT_CHOICE = SelectEntityDescription(key="export_choice", translation_key="export_choice")
LOGBOOK_TIME = SelectEntityDescription(key="logbook_time", translation_key="logbook_time")
LOGBOOK_EDIT = SelectEntityDescription(key="logbook_edit", translation_key="logbook_edit")
LOGBOOK_CLEAR = SelectEntityDescription(key="logbook_clear", translation_key="logbook_clear")
COST_CATEGORY = SelectEntityDescription(key="travel_cost_category", translation_key="travel_cost_category")
COST_COUNTRY = SelectEntityDescription(key="travel_cost_country", translation_key="travel_cost_country")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            ReiseverlaufExportChoice(coordinator, EXPORT_CHOICE),
            ReiseverlaufLogbookTime(coordinator, LOGBOOK_TIME),
            ReiseverlaufLogbookEdit(coordinator, LOGBOOK_EDIT),
            ReiseverlaufLogbookClear(coordinator, LOGBOOK_CLEAR),
            ReiseverlaufCostCategory(coordinator, COST_CATEGORY),
            ReiseverlaufCostCountry(coordinator, COST_COUNTRY),
        ]
    )
