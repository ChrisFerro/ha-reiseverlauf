"""
Runtime data types for reiseverlauftracker.

Access pattern: entry.runtime_data.client / entry.runtime_data.coordinator
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import ReiseverlaufApiClient
    from .coordinator import ReiseverlaufDataUpdateCoordinator


type ReiseverlaufConfigEntry = ConfigEntry[ReiseverlaufData]


@dataclass
class ReiseverlaufData:
    """Runtime data stored on the config entry after a successful setup."""

    client: ReiseverlaufApiClient
    coordinator: ReiseverlaufDataUpdateCoordinator
    integration: Integration
