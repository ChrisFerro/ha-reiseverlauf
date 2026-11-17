"""Sensor that shows whether a logbook entry is waiting and lists the latest entries."""

from collections.abc import Mapping
from typing import Any

from custom_components.reiseverlauftracker.coordinator.logbook_keeper import entry_data
from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription

STATE_PENDING = "offen"  # codespell:ignore offen
STATE_SAVED = "gespeichert"
LATEST_ENTRIES = 10

LOGBOOK_ENTRY = SensorEntityDescription(
    key="logbook_entry",
    translation_key="logbook_entry",
    device_class=SensorDeviceClass.ENUM,
    options=[STATE_PENDING, STATE_SAVED],
)


class ReiseverlaufLogbookEntrySensor(SensorEntity, ReiseverlaufEntity):
    """Pending while an occasion waits for the form, otherwise saved."""

    @property
    def native_value(self) -> str:
        """Return whether an occasion is pending."""
        return STATE_PENDING if self.coordinator.logbook.pending else STATE_SAVED

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the pending occasion and the latest entries, newest first."""
        keeper = self.coordinator.logbook
        pending = keeper.pending
        return {
            "anlass": pending.occasion.value if pending else None,
            "ort": pending.place if pending else None,
            "halt_start": pending.stop_start.isoformat() if pending and pending.stop_start else None,
            "letzte_eintraege": [entry_data(e) for e in reversed(keeper.logbook.entries[-LATEST_ENTRIES:])],
        }
