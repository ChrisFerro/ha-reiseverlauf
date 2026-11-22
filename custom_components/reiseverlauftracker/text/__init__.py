"""Text platform for reiseverlauftracker: the note of the travel costs form."""

from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.text import TextEntity, TextEntityDescription

PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.data import ReiseverlaufConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

COST_NOTE = TextEntityDescription(key="travel_cost_note", translation_key="travel_cost_note", native_max=100)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the text platform."""
    async_add_entities([ReiseverlaufCostNote(entry.runtime_data.coordinator, COST_NOTE)])


class ReiseverlaufCostNote(TextEntity, ReiseverlaufEntity):
    """Note of the next travel cost, e.g. the name of a ferry or pitch."""

    @property
    def native_value(self) -> str:
        """Return the note in the form."""
        return self.coordinator.cost_form.note

    async def async_set_value(self, value: str) -> None:
        """Change the note in the form."""
        self.coordinator.cost_form.set_note(value)
