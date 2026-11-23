"""Selection of the time the logbook form is filled in for: the current occasion, a stop or another time."""

from collections.abc import Mapping
from typing import Any

from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.select import SelectEntity


class ReiseverlaufLogbookTime(SelectEntity, ReiseverlaufEntity):
    """Lists "current", the remembered stops newest first and "other time"; the choice lives on the coordinator."""

    @property
    def options(self) -> list[str]:
        """Return the fixed choices and the stops in between."""
        return self.coordinator.late_form.options()

    @property
    def current_option(self) -> str | None:
        """Return the chosen time."""
        return self.coordinator.late_form.current_option()

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the chosen earlier time and whether its odometer must be confirmed."""
        late = self.coordinator.logbook.late
        return {
            "zeit": late.time.isoformat() if late else None,
            "ort": late.place if late else None,
            "geschaetzt": late.estimated if late else False,
        }

    async def async_select_option(self, option: str) -> None:
        """Fill the form for the chosen time."""
        await self.coordinator.late_form.async_select(option)
        self.async_write_ha_state()
