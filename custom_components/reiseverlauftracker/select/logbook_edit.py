"""Selections of the logbook form: a stored entry to change or delete, and a field to empty."""

from collections.abc import Mapping
from typing import Any

from custom_components.reiseverlauftracker.const import CLEAR_CHOICE_NONE
from custom_components.reiseverlauftracker.coordinator.logbook import FormField
from custom_components.reiseverlauftracker.coordinator.logbook_keeper import entry_data
from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.select import SelectEntity


class ReiseverlaufLogbookEdit(SelectEntity, ReiseverlaufEntity):
    """Lists "new" and the stored entries of the chosen trip, newest first; the choice lives on the keeper."""

    @property
    def options(self) -> list[str]:
        """Return "new" and the entry labels."""
        return self.coordinator.edit_form.options()

    @property
    def current_option(self) -> str:
        """Return the entry being edited, or "new"."""
        return self.coordinator.edit_form.current_option()

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the stored values of the chosen entry, for the dashboard."""
        entry = self.coordinator.edit_form.entry()
        return {"eintrag": entry_data(entry) if entry else None}

    async def async_select_option(self, option: str) -> None:
        """Fill the form with the chosen entry, or return to a new entry."""
        self.coordinator.edit_form.select(option)


class ReiseverlaufLogbookClear(SelectEntity, ReiseverlaufEntity):
    """Empties the chosen field of the form, then rests on "none" again."""

    _attr_options = [CLEAR_CHOICE_NONE, *(f.value for f in FormField)]
    _attr_current_option = CLEAR_CHOICE_NONE

    async def async_select_option(self, option: str) -> None:
        """Empty the chosen field."""
        if option != CLEAR_CHOICE_NONE:
            self.coordinator.logbook.clear_field(FormField(option))
        self.async_write_ha_state()
