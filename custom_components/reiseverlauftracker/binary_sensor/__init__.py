"""Binary sensor platform for reiseverlauftracker."""

from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription

PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.data import ReiseverlaufConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

TRIP_ACTIVE = BinarySensorEntityDescription(key="trip_active", translation_key="trip_active")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    async_add_entities([ReiseverlaufTripActiveSensor(entry.runtime_data.coordinator, TRIP_ACTIVE)])


class ReiseverlaufTripActiveSensor(BinarySensorEntity, ReiseverlaufEntity):
    """On while a trip runs, including stops within the end delay."""

    @property
    def is_on(self) -> bool:
        """Return whether a trip is running."""
        return self.coordinator.data.active
