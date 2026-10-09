"""Typed view of a config entry's data and options, with defaults for missing keys."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from .const import (
    CONF_ALTITUDE_ENTITY,
    CONF_DPLUS_ENTITY,
    CONF_DPLUS_ON_VALUE,
    CONF_ELEVATION_HYSTERESIS,
    CONF_END_DELAY,
    CONF_MARGIN,
    CONF_MAX_ACCURACY,
    CONF_MERGE_WINDOW,
    CONF_MIN_MOVEMENT,
    CONF_MIN_POINT_DISTANCE,
    CONF_OUTPUT_DIR,
    CONF_PLACE_NAMES,
    CONF_SCALE,
    CONF_SPEED_ENTITY,
    CONF_STANDSTILL_SPEED,
    CONF_TITLE_FORMAT,
    CONF_TRACKER_ENTITY,
    DEFAULT_DPLUS_ON_VALUE,
    DEFAULT_ELEVATION_HYSTERESIS_M,
    DEFAULT_END_DELAY_MIN,
    DEFAULT_MARGIN_MIN,
    DEFAULT_MAX_ACCURACY_M,
    DEFAULT_MERGE_WINDOW_H,
    DEFAULT_MIN_MOVEMENT_M,
    DEFAULT_MIN_POINT_DISTANCE_M,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PLACE_NAMES,
    DEFAULT_SCALE,
    DEFAULT_STANDSTILL_SPEED_KMH,
    DEFAULT_TITLE_FORMAT,
    SECTION_DETECTION,
    SECTION_EXPORT,
    SECTION_THRESHOLDS,
)


@dataclass(frozen=True, slots=True)
class ReiseverlaufSettings:
    """Everything the integration reads from its config entry."""

    dplus_entity: str
    dplus_on_value: str
    tracker_entity: str
    speed_entity: str
    altitude_entity: str | None
    output_dir: str
    end_delay: timedelta
    merge_window: timedelta
    min_movement_m: float
    scale: float
    margin: timedelta
    title_format: str
    place_names: bool
    standstill_kmh: float
    max_accuracy_m: float
    min_point_distance_m: float
    elevation_hysteresis_m: float

    @classmethod
    def from_entry(cls, data: Mapping[str, Any], options: Mapping[str, Any]) -> ReiseverlaufSettings:
        """Build the settings from `entry.data` and `entry.options`."""
        detection = options.get(SECTION_DETECTION, {})
        export = options.get(SECTION_EXPORT, {})
        thresholds = options.get(SECTION_THRESHOLDS, {})
        return cls(
            dplus_entity=data[CONF_DPLUS_ENTITY],
            dplus_on_value=data.get(CONF_DPLUS_ON_VALUE, DEFAULT_DPLUS_ON_VALUE),
            tracker_entity=data[CONF_TRACKER_ENTITY],
            speed_entity=data[CONF_SPEED_ENTITY],
            altitude_entity=data.get(CONF_ALTITUDE_ENTITY) or None,
            output_dir=data.get(CONF_OUTPUT_DIR, DEFAULT_OUTPUT_DIR),
            end_delay=timedelta(minutes=detection.get(CONF_END_DELAY, DEFAULT_END_DELAY_MIN)),
            merge_window=timedelta(hours=detection.get(CONF_MERGE_WINDOW, DEFAULT_MERGE_WINDOW_H)),
            min_movement_m=detection.get(CONF_MIN_MOVEMENT, DEFAULT_MIN_MOVEMENT_M),
            scale=export.get(CONF_SCALE, DEFAULT_SCALE),
            margin=timedelta(minutes=export.get(CONF_MARGIN, DEFAULT_MARGIN_MIN)),
            title_format=export.get(CONF_TITLE_FORMAT, DEFAULT_TITLE_FORMAT),
            place_names=export.get(CONF_PLACE_NAMES, DEFAULT_PLACE_NAMES),
            standstill_kmh=thresholds.get(CONF_STANDSTILL_SPEED, DEFAULT_STANDSTILL_SPEED_KMH),
            max_accuracy_m=thresholds.get(CONF_MAX_ACCURACY, DEFAULT_MAX_ACCURACY_M),
            min_point_distance_m=thresholds.get(CONF_MIN_POINT_DISTANCE, DEFAULT_MIN_POINT_DISTANCE_M),
            elevation_hysteresis_m=thresholds.get(CONF_ELEVATION_HYSTERESIS, DEFAULT_ELEVATION_HYSTERESIS_M),
        )

    def is_dplus_on(self, state: str) -> bool:
        """Return whether a D+ state string means "on"; case does not matter."""
        return state.casefold() == self.dplus_on_value.casefold()
