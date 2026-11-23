"""Datetime platform for reiseverlauftracker: the free time of a late logbook entry and the period of a tour."""

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
TOUR_START = DateTimeEntityDescription(key="tour_start", translation_key="tour_start")
TOUR_END = DateTimeEntityDescription(key="tour_end", translation_key="tour_end")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the datetime platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            ReiseverlaufLateTime(coordinator, LATE_TIME),
            ReiseverlaufTourStart(coordinator, TOUR_START),
            ReiseverlaufTourEnd(coordinator, TOUR_END),
        ]
    )


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


class ReiseverlaufTourStart(DateTimeEntity, ReiseverlaufEntity):
    """Start of a new tour, or of the tour chosen in the export selection."""

    @property
    def native_value(self) -> datetime | None:
        """Return the start in the tour form."""
        return self.coordinator.tour_form.start

    async def async_set_value(self, value: datetime) -> None:
        """Change the start for the chosen export."""
        self.coordinator.tour_form.set_start(value)


class ReiseverlaufTourEnd(DateTimeEntity, ReiseverlaufEntity):
    """End of a new tour (now unless set), or of the tour chosen in the export selection."""

    @property
    def native_value(self) -> datetime:
        """Return the end in the tour form."""
        return self.coordinator.tour_form.end

    async def async_set_value(self, value: datetime) -> None:
        """Change the end for the chosen export."""
        self.coordinator.tour_form.set_end(value)
