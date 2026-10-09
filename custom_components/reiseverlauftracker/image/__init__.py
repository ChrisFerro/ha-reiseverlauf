"""Image platform for reiseverlauftracker."""

from typing import TYPE_CHECKING

from homeassistant.components.image import ImageEntityDescription

from .composite import ReiseverlaufCompositeImage

PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.data import ReiseverlaufConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

LAST_TRIP_COMPOSITE = ImageEntityDescription(key="last_trip_composite", translation_key="last_trip_composite")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the image platform."""
    async_add_entities([ReiseverlaufCompositeImage(entry.runtime_data.coordinator, LAST_TRIP_COMPOSITE)])
