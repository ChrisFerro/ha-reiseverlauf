"""Filter maintenance binary sensor for reiseverlauftracker."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)


@dataclass(frozen=True, kw_only=True)
class ReiseverlaufBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a binary sensor and how to read it from coordinator data."""

    value_fn: Callable[[dict[str, Any]], bool | None]


ENTITY_DESCRIPTIONS: tuple[ReiseverlaufBinarySensorEntityDescription, ...] = (
    ReiseverlaufBinarySensorEntityDescription(
        key="filter_replacement",
        translation_key="filter_replacement",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: data.get("filter_replacement"),
    ),
)


class ReiseverlaufFilterSensor(BinarySensorEntity, ReiseverlaufEntity):
    """Binary sensor reporting whether the filter needs replacing."""

    entity_description: ReiseverlaufBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return the value read from coordinator data."""
        return self.entity_description.value_fn(self.coordinator.data)
