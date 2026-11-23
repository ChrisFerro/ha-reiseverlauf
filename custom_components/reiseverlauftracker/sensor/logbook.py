"""Logbook sensors: pending entry, odometer, last levels, consumption, costs and open toll."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from custom_components.reiseverlauftracker.const import OPEN_TOLL_PERIOD
from custom_components.reiseverlauftracker.coordinator.download_links import ATTR_DOWNLOADS
from custom_components.reiseverlauftracker.coordinator.edit_form import field_names
from custom_components.reiseverlauftracker.coordinator.logbook import CostCategory, Logbook
from custom_components.reiseverlauftracker.coordinator.logbook_keeper import entry_data
from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfLength
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
    from custom_components.reiseverlauftracker.coordinator.exports import ExportInfo

CONSUMPTION_UNIT = "l/100 km"
PER_DAY_UNIT = "l/d"

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

    # Signed links change every hour and must not reach the history.
    _unrecorded_attributes = frozenset({ATTR_DOWNLOADS})

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
            "nicht_abgelesen": field_names(keeper.draft.not_read_off(), self.coordinator.hass.config.language),
            "letzte_eintraege": [entry_data(e) for e in reversed(keeper.logbook.entries[-LATEST_ENTRIES:])],
            # The CSV files are written after every change, so they exist once there is an entry or a cost.
            ATTR_DOWNLOADS: self.coordinator.download_links.for_logbook(
                keeper.csv_path.name if keeper.logbook.entries else None,
                keeper.travel_csv_path.name if keeper.logbook.travel_costs else None,
            ),
        }


@dataclass(frozen=True, kw_only=True)
class LogbookSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor computed from the logbook."""

    value_fn: Callable[[Logbook, datetime], float | None]
    attributes_fn: Callable[[Logbook, datetime], Mapping[str, Any]] | None = None
    currency: bool = False


def _last(field: str) -> Callable[[Logbook, datetime], float | None]:
    def value(book: Logbook, _now: datetime) -> float | None:
        entry = book.last(having=field)
        return getattr(entry, field) if entry else None

    return value


def _month(now: datetime) -> tuple[datetime, datetime]:
    start = dt_util.as_local(now).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, (start + timedelta(days=32)).replace(day=1)


def _year(now: datetime) -> tuple[datetime, datetime]:
    start = dt_util.as_local(now).replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, start.replace(year=start.year + 1)


def _costs(period: Callable[[datetime], tuple[datetime, datetime]]) -> Callable[[Logbook, datetime], float]:
    def value(book: Logbook, now: datetime) -> float:
        return round(book.costs_between(*period(now)).total, 2)

    return value


def _cost_parts(
    period: Callable[[datetime], tuple[datetime, datetime]],
) -> Callable[[Logbook, datetime], Mapping[str, Any]]:
    def attributes(book: Logbook, now: datetime) -> Mapping[str, Any]:
        costs = book.costs_between(*period(now))
        return {
            "diesel": round(costs.fuel, 2),
            "gas": round(costs.gas, 2),
            **{category.value: round(costs.travel.get(category, 0.0), 2) for category in CostCategory},
        }

    return attributes


def _consumption(book: Logbook, _now: datetime) -> float | None:
    value = book.average_consumption()
    return round(value, 1) if value is not None else None


def _parked_heating(book: Logbook, _now: datetime) -> float | None:
    parked = book.parked_consumption()
    value = parked.litres_per_day if parked else None
    return round(value, 2) if value is not None else None


def _parked_heating_attributes(book: Logbook, _now: datetime) -> Mapping[str, Any]:
    parked = book.parked_consumption()
    return {
        "standzeiten": parked.periods if parked else 0,
        "standtage": round(parked.days, 1) if parked else 0.0,
        "abnahme_liter": round(parked.litres, 1) if parked else 0.0,
    }


def _level(key: str, field: str) -> LogbookSensorEntityDescription:
    return LogbookSensorEntityDescription(
        key=key,
        translation_key=key,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_last(field),
    )


def _cost(key: str, period: Callable[[datetime], tuple[datetime, datetime]]) -> LogbookSensorEntityDescription:
    return LogbookSensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        value_fn=_costs(period),
        attributes_fn=_cost_parts(period),
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
    LogbookSensorEntityDescription(
        key="parked_heating_read",
        translation_key="parked_heating_read",
        native_unit_of_measurement=PER_DAY_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_parked_heating,
        attributes_fn=_parked_heating_attributes,
    ),
    _cost("travel_costs_month", _month),
    _cost("travel_costs_year", _year),
)
# Replaced by the travel cost sensors in 0.3.0; removed from the entity registry at setup.
REMOVED_KEYS = ("costs_month", "costs_year")


class ReiseverlaufLogbookSensor(SensorEntity, ReiseverlaufEntity):
    """
    Value computed from the logbook.

    The odometer follows the distance measured since the last reading; levels
    are those of the latest entry that has them; costs count fuel, gas and travel costs.
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

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return what the value was computed from, for sensors that explain it."""
        if (attributes_fn := self.entity_description.attributes_fn) is None:
            return None
        return attributes_fn(self.coordinator.logbook.logbook, dt_util.utcnow())


OPEN_TOLL = SensorEntityDescription(key="open_toll", translation_key="open_toll")


class ReiseverlaufOpenTollSensor(SensorEntity, ReiseverlaufEntity):
    """
    Finished trips of the last 12 months through a toll country without a toll entry or "no toll" mark.

    Trips whose countries are unknown do not count (docs/features/feat-09-nachtraege.md 5.9, 6.5).
    """

    @property
    def native_value(self) -> int:
        """Return how many trips wait for their toll."""
        return len(self._open_trips())

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the trips, newest first."""
        tolls = set(self.coordinator.settings.toll_countries)
        return {
            "reisen": [
                {
                    "titel": info.title,
                    "start": info.start.isoformat(),
                    "ordner": info.folder,
                    "laender": [c for c in info.countries or () if c in tolls],
                }
                for info in self._open_trips()
            ]
        }

    def _open_trips(self) -> list[ExportInfo]:
        coordinator = self.coordinator
        book = coordinator.logbook.logbook
        tolls = set(coordinator.settings.toll_countries)
        since = dt_util.utcnow() - OPEN_TOLL_PERIOD
        return [
            info
            for info in coordinator.exports
            if info.automatic
            and info.start >= since
            and tolls.intersection(info.countries or ())
            and not book.toll_settled(info.start)
        ]
