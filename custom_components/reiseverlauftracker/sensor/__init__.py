"""Sensor platform for reiseverlauftracker."""

from typing import TYPE_CHECKING

from .current_trip import ENTITY_DESCRIPTIONS as CURRENT_TRIP_DESCRIPTIONS
from .entity import ReiseverlaufSensor
from .last_trip import ENTITY_DESCRIPTIONS as LAST_TRIP_DESCRIPTIONS

PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.data import ReiseverlaufConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

ENTITY_DESCRIPTIONS = (*CURRENT_TRIP_DESCRIPTIONS, *LAST_TRIP_DESCRIPTIONS)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    async_add_entities(
        ReiseverlaufSensor(entry.runtime_data.coordinator, description) for description in ENTITY_DESCRIPTIONS
    )
