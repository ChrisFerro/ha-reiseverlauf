"""Selection of an export, used by the cleanup action when it names no export."""

from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.restore_state import RestoreEntity


class ReiseverlaufExportChoice(SelectEntity, ReiseverlaufEntity, RestoreEntity):
    """Lists every export, newest first, plus "all exports"; the choice lives on the coordinator."""

    @property
    def options(self) -> list[str]:
        """Return the export labels and the "all" choice at the end."""
        return self.coordinator.export_choice_options()

    @property
    def current_option(self) -> str | None:
        """Return the chosen export, or the newest one if the choice is gone."""
        return self.coordinator.current_export_choice()

    async def async_added_to_hass(self) -> None:
        """Restore the last choice."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self.coordinator.export_choice = last.state

    async def async_select_option(self, option: str) -> None:
        """Remember the chosen export."""
        self.coordinator.export_choice = option
        self.async_write_ha_state()
