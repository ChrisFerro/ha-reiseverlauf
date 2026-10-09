"""Sensors for the status and the running trip."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from custom_components.reiseverlauftracker.coordinator.models import TripSnapshot, TripStatus
from custom_components.reiseverlauftracker.settings import ReiseverlaufSettings
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfLength, UnitOfTime

from .entity import ReiseverlaufSensorEntityDescription


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _status_attributes(data: TripSnapshot, _settings: ReiseverlaufSettings) -> Mapping[str, Any]:
    return {"voraussichtliches_ende": _iso(data.expected_end), "fortsetzbar_bis": _iso(data.merge_until)}


ENTITY_DESCRIPTIONS = (
    ReiseverlaufSensorEntityDescription(
        key="trip_status",
        translation_key="trip_status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in TripStatus],
        value_fn=lambda data: data.status.value,
        attributes_fn=_status_attributes,
    ),
    ReiseverlaufSensorEntityDescription(
        key="trip_start",
        translation_key="trip_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.trip_start,
    ),
    ReiseverlaufSensorEntityDescription(
        key="trip_distance",
        translation_key="trip_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        value_fn=lambda data: data.distance_km,
    ),
    ReiseverlaufSensorEntityDescription(
        key="trip_driving_time",
        translation_key="trip_driving_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=lambda data: data.driving_time.total_seconds() / 60 if data.driving_time is not None else None,
    ),
)
