"""
Runtime data types for reiseverlauftracker.

Access pattern: entry.runtime_data.settings
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .settings import ReiseverlaufSettings


type ReiseverlaufConfigEntry = ConfigEntry[ReiseverlaufData]


@dataclass
class ReiseverlaufData:
    """Runtime data stored on the config entry after a successful setup."""

    settings: ReiseverlaufSettings
    integration: Integration
