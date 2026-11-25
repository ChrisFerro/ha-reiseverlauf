"""Selection of an export, used by the cleanup action when it names no export."""

from collections.abc import Mapping
from typing import Any

from custom_components.reiseverlauftracker.const import EXPORT_CHOICE_ALL
from custom_components.reiseverlauftracker.coordinator.cost_form import trip_costs_data
from custom_components.reiseverlauftracker.coordinator.download_links import ATTR_DOWNLOADS
from custom_components.reiseverlauftracker.coordinator.tours import nights_data
from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from custom_components.reiseverlauftracker.export import ExportFile
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.restore_state import RestoreEntity


class ReiseverlaufExportChoice(SelectEntity, ReiseverlaufEntity, RestoreEntity):
    """Lists every export, newest first, plus "all exports"; the choice lives on the coordinator."""

    # Signed links change every hour and must not reach the history; the costs are in the logbook store anyway.
    _unrecorded_attributes = frozenset({ATTR_DOWNLOADS, "reisekosten", "standorte", "tourkosten", "exporte"})

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
        """
        Return the signed download links and the travel costs of the chosen export; none for "all exports".

        A tour has no travel costs of its own; it lists its kind, night places and costs instead. `exporte`
        lists every export with its kind, so a dashboard can tell manual exports from detected trips. `titel`
        carries the full title, which the option shortens.
        """
        choice = self.current_option
        exports = self.coordinator.find_exports(choice) if choice and choice != EXPORT_CHOICE_ALL else []
        info = exports[0] if exports else None
        tour = info is not None and info.is_tour and info.tour is not None
        return {
            "titel": info.title if info else None,
            ATTR_DOWNLOADS: self.coordinator.download_links.for_export(info) if info else [],
            "reisekosten": trip_costs_data(self.coordinator, info) if info and not tour else None,
            "art": info.kind.value if info else None,
            "standorte": nights_data(info) if info and tour else None,
            "tourkosten": info.tour.costs if info and info.tour else None,
            "exporte": [
                {
                    "auswahl": self.coordinator.export_label(export),
                    "titel": export.title,
                    "ordner": export.folder,
                    "art": export.kind.value,
                    "automatisch": export.automatic,
                    "start": export.start.isoformat(),
                    "ende": export.end.isoformat(),
                    "strecke_km": round(export.distance_km, 1),
                    "rohdaten": ExportFile.RAW in export.files,
                }
                for export in self.coordinator.exports
            ],
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
