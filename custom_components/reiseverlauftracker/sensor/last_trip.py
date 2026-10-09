"""Sensors for the last exported trip."""

from collections.abc import Mapping
from typing import Any

from custom_components.reiseverlauftracker.coordinator.export_runner import media_url
from custom_components.reiseverlauftracker.coordinator.models import TripSnapshot
from custom_components.reiseverlauftracker.settings import ReiseverlaufSettings
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfLength, UnitOfTime

from .entity import ReiseverlaufSensorEntityDescription


def _title_attributes(data: TripSnapshot, settings: ReiseverlaufSettings) -> Mapping[str, Any]:
    info = data.last_export
    if info is None:
        return {}
    return {
        "ordner": info.folder,  # codespell:ignore ordner
        "start": info.start.isoformat(),
        "dateien": [
            {"typ": kind.value, "name": name, "url": media_url(settings, info.folder, name)}
            for kind, name in info.files.items()
        ],
        "statistik": info.stats_text,
    }


ENTITY_DESCRIPTIONS = (
    ReiseverlaufSensorEntityDescription(
        key="last_trip_title",
        translation_key="last_trip_title",
        value_fn=lambda data: data.last_export.title if data.last_export else None,
        attributes_fn=_title_attributes,
    ),
    ReiseverlaufSensorEntityDescription(
        key="last_trip_distance",
        translation_key="last_trip_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        value_fn=lambda data: data.last_export.distance_km if data.last_export else None,
    ),
    ReiseverlaufSensorEntityDescription(
        key="last_trip_driving_time",
        translation_key="last_trip_driving_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=lambda data: data.last_export.driving_time.total_seconds() / 60 if data.last_export else None,
    ),
    ReiseverlaufSensorEntityDescription(
        key="last_trip_duration",
        translation_key="last_trip_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=lambda data: data.last_export.duration.total_seconds() / 60 if data.last_export else None,
    ),
    ReiseverlaufSensorEntityDescription(
        key="last_trip_end",
        translation_key="last_trip_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.last_export.end if data.last_export else None,
    ),
)
