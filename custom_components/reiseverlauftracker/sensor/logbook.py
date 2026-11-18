"""Logbook sensors: pending entry, odometer, last levels, consumption and costs."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from custom_components.reiseverlauftracker.coordinator.logbook import Logbook
from custom_components.reiseverlauftracker.coordinator.logbook_keeper import entry_data
from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfLength
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator

CONSUMPTION_UNIT = "l/100 km"

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


@dataclass(frozen=True, kw_only=True)
class LogbookSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor computed from the logbook."""

    value_fn: Callable[[Logbook, datetime], float | None]
    currency: bool = False


def _last(field: str) -> Callable[[Logbook, datetime], float | None]:
    def value(book: Logbook, _now: datetime) -> float | None:
        entry = book.last(having=field)
        return getattr(entry, field) if entry else None

    return value


def _cost_this_month(book: Logbook, now: datetime) -> float:
    start = dt_util.as_local(now).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start + timedelta(days=32)).replace(day=1)
    return round(book.cost_between(start, end), 2)


def _cost_this_year(book: Logbook, now: datetime) -> float:
    start = dt_util.as_local(now).replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return round(book.cost_between(start, start.replace(year=start.year + 1)), 2)


def _consumption(book: Logbook, _now: datetime) -> float | None:
    value = book.average_consumption()
    return round(value, 1) if value is not None else None


def _level(key: str, field: str) -> LogbookSensorEntityDescription:
    return LogbookSensorEntityDescription(
        key=key,
        translation_key=key,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_last(field),
    )


def _cost(key: str, value_fn: Callable[[Logbook, datetime], float | None]) -> LogbookSensorEntityDescription:
    return LogbookSensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        value_fn=value_fn,
        currency=True,
    )


LOGBOOK_DESCRIPTIONS = (
    LogbookSensorEntityDescription(
        key="odometer",
        translation_key="odometer",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=0,
        value_fn=lambda book, _now: book.suggest_odometer(),
    ),
    _level("fuel_level", "fuel_percent"),
    _level("gas_1_level", "gas1_percent"),
    _level("gas_2_level", "gas2_percent"),
    LogbookSensorEntityDescription(
        key="average_consumption",
        translation_key="average_consumption",
        native_unit_of_measurement=CONSUMPTION_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_consumption,
    ),
    _cost("costs_month", _cost_this_month),
    _cost("costs_year", _cost_this_year),
)


class ReiseverlaufLogbookSensor(SensorEntity, ReiseverlaufEntity):
    """
    Value computed from the logbook.

    The odometer follows the distance measured since the last reading; levels
    are those of the latest entry that has them; costs count fuel and gas.
    """

    entity_description: LogbookSensorEntityDescription

    def __init__(
        self, coordinator: ReiseverlaufDataUpdateCoordinator, entity_description: LogbookSensorEntityDescription
    ) -> None:
        """Initialize the sensor; costs use the currency of the instance."""
        super().__init__(coordinator, entity_description)
        if entity_description.currency:
            self._attr_native_unit_of_measurement = coordinator.hass.config.currency

    @property
    def native_value(self) -> float | None:
        """Return the value computed from the logbook."""
        return self.entity_description.value_fn(self.coordinator.logbook.logbook, dt_util.utcnow())
