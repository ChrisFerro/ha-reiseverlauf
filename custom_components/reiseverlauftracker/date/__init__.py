"""Date platform for reiseverlauftracker: the day of the travel costs form."""

from datetime import date
from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.date import DateEntity, DateEntityDescription

PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.data import ReiseverlaufConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

COST_DATE = DateEntityDescription(key="travel_cost_date", translation_key="travel_cost_date")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the date platform."""
    async_add_entities([ReiseverlaufCostDate(entry.runtime_data.coordinator, COST_DATE)])


class ReiseverlaufCostDate(DateEntity, ReiseverlaufEntity):
    """Day of the next travel cost; it follows the start of the trip chosen in the export selection."""

    @property
    def native_value(self) -> date:
        """Return the day in the form."""
        return self.coordinator.cost_form.day

    async def async_set_value(self, value: date) -> None:
        """Change the day for the chosen trip."""
        self.coordinator.cost_form.set_day(value)
