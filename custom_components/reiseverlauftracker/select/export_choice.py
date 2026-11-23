"""Selection of an export, used by the cleanup action when it names no export."""

from collections.abc import Mapping
from typing import Any

from custom_components.reiseverlauftracker.const import EXPORT_CHOICE_ALL
from custom_components.reiseverlauftracker.coordinator.cost_form import trip_costs_data
from custom_components.reiseverlauftracker.coordinator.download_links import ATTR_DOWNLOADS
from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.restore_state import RestoreEntity


class ReiseverlaufExportChoice(SelectEntity, ReiseverlaufEntity, RestoreEntity):
    """Lists every export, newest first, plus "all exports"; the choice lives on the coordinator."""

    # Signed links change every hour and must not reach the history; the costs are in the logbook store anyway.
    _unrecorded_attributes = frozenset({ATTR_DOWNLOADS, "reisekosten"})

    @property
    def options(self) -> list[str]:
        """Return the export labels and the "all" choice at the end."""
        return self.coordinator.export_choice_options()

    @property
    def current_option(self) -> str | None:
        """Return the chosen export, or the newest one if the choice is gone."""
        return self.coordinator.current_export_choice()

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the signed download links and the travel costs of the chosen export; none for "all exports"."""
        choice = self.current_option
        exports = self.coordinator.find_exports(choice) if choice and choice != EXPORT_CHOICE_ALL else []
        return {
            ATTR_DOWNLOADS: self.coordinator.download_links.for_export(exports[0]) if exports else [],
            "reisekosten": trip_costs_data(self.coordinator, exports[0]) if exports else None,
        }

    async def async_added_to_hass(self) -> None:
        """Restore the last choice."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self.coordinator.export_choice = last.state

    async def async_select_option(self, option: str) -> None:
        """Remember the chosen export; the travel costs form follows it."""
        self.coordinator.export_choice = option
        self.coordinator.async_update_listeners()
