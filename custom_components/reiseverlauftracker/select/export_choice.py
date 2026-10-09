"""Selection of an export, for the cleanup action on a dashboard."""

from custom_components.reiseverlauftracker.const import EXPORT_CHOICE_ALL
from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util


class ReiseverlaufExportChoice(SelectEntity, ReiseverlaufEntity, RestoreEntity):
    """
    Lists every export, newest first, plus "all exports".

    The choice is kept across restarts. It never falls back to "all" on its own,
    so a dashboard button cannot delete everything by accident.
    """

    _attr_current_option: str | None = None

    @property
    def options(self) -> list[str]:
        """Return the export labels and the "all" choice at the end."""
        tz = dt_util.get_default_time_zone()
        return [*(info.label(tz) for info in self.coordinator.data.exports), EXPORT_CHOICE_ALL]

    @property
    def current_option(self) -> str | None:
        """Return the chosen export, or the newest one if the choice is gone."""
        options = self.options
        if self._attr_current_option in options:
            return self._attr_current_option
        return options[0] if len(options) > 1 else None

    async def async_added_to_hass(self) -> None:
        """Restore the last choice."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._attr_current_option = last.state

    async def async_select_option(self, option: str) -> None:
        """Remember the chosen export."""
        self._attr_current_option = option
        self.async_write_ha_state()
