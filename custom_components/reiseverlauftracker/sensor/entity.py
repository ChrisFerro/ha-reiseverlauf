"""Sensor entity for reiseverlauftracker."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from custom_components.reiseverlauftracker.coordinator.download_links import ATTR_DOWNLOADS
from custom_components.reiseverlauftracker.coordinator.exports import ExportInfo
from custom_components.reiseverlauftracker.coordinator.models import TripSnapshot
from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from custom_components.reiseverlauftracker.settings import ReiseverlaufSettings
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription


@dataclass(frozen=True, kw_only=True)
class ReiseverlaufSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor and how to read it from the trip snapshot."""

    value_fn: Callable[[TripSnapshot], str | float | datetime | None]
    attributes_fn: Callable[[TripSnapshot, ReiseverlaufSettings], Mapping[str, Any]] | None = None
    download_fn: Callable[[TripSnapshot], ExportInfo | None] | None = None
    """Export whose signed download links the attribute `downloads` lists."""


class ReiseverlaufSensor(SensorEntity, ReiseverlaufEntity):
    """Sensor backed by one value of the trip snapshot."""

    entity_description: ReiseverlaufSensorEntityDescription
    # Signed links change every hour and must not reach the history.
    _unrecorded_attributes = frozenset({ATTR_DOWNLOADS})

    @property
    def native_value(self) -> str | float | datetime | None:
        """Return the value read from the snapshot."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the extra attributes of the description, if it has any."""
        description = self.entity_description
        if description.attributes_fn is None and description.download_fn is None:
            return None
        attributes = (
            dict(description.attributes_fn(self.coordinator.data, self.coordinator.settings))
            if description.attributes_fn
            else {}
        )
        if description.download_fn is not None and (info := description.download_fn(self.coordinator.data)):
            attributes[ATTR_DOWNLOADS] = self.coordinator.download_links.for_export(info)
        return attributes
