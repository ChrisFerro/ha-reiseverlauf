"""Datetime platform for reiseverlauftracker: the free time of a late logbook entry."""

from datetime import datetime
from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.datetime import DateTimeEntity, DateTimeEntityDescription

PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.data import ReiseverlaufConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

LATE_TIME = DateTimeEntityDescription(key="logbook_late_time", translation_key="logbook_late_time")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the datetime platform."""
    async_add_entities([ReiseverlaufLateTime(entry.runtime_data.coordinator, LATE_TIME)])


class ReiseverlaufLateTime(DateTimeEntity, ReiseverlaufEntity):
    """Time of a late entry when "other time" is chosen in the logbook time selection."""

    @property
    def native_value(self) -> datetime | None:
        """Return the chosen time, in UTC."""
        return self.coordinator.late_form.time

    async def async_set_value(self, value: datetime) -> None:
        """Set the time; the form follows while "other time" is chosen."""
        await self.coordinator.late_form.async_set_time(value)
        self.async_write_ha_state()
