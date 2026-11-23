"""Binary sensor platform for reiseverlauftracker."""

from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass

PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.data import ReiseverlaufConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

TRIP_ACTIVE = BinarySensorEntityDescription(key="trip_active", translation_key="trip_active")
TOUR_BUSY = BinarySensorEntityDescription(
    key="tour_busy", translation_key="tour_busy", device_class=BinarySensorDeviceClass.RUNNING
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [ReiseverlaufTripActiveSensor(coordinator, TRIP_ACTIVE), ReiseverlaufTourBusySensor(coordinator, TOUR_BUSY)]
    )


class ReiseverlaufTripActiveSensor(BinarySensorEntity, ReiseverlaufEntity):
    """On while a trip runs, including stops within the end delay."""

    @property
    def is_on(self) -> bool:
        """Return whether a trip is running."""
        return self.coordinator.data.active


class ReiseverlaufTourBusySensor(BinarySensorEntity, ReiseverlaufEntity):
    """On while a tour is created, changed or renewed (docs/features/feat-10-tour.md 7)."""

    @property
    def is_on(self) -> bool:
        """Return whether a tour is being built."""
        return self.coordinator.tours.busy
