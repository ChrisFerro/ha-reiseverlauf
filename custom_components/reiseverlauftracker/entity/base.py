"""Base entity class for reiseverlauftracker."""

from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.const import DOMAIN
from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

if TYPE_CHECKING:
    from homeassistant.helpers.entity import EntityDescription


class ReiseverlaufEntity(CoordinatorEntity[ReiseverlaufDataUpdateCoordinator]):
    """
    Base entity on the trip recording service device of a config entry.

    The unique ID is `{entry_id}_{key}`: the integration derives its values from
    other entities, so there is no serial or account ID to use instead.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ReiseverlaufDataUpdateCoordinator,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{entity_description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Reiseverlauf Tracker",
            model="Reiseaufzeichnung",
            entry_type=DeviceEntryType.SERVICE,
        )
