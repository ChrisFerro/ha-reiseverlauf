"""Options flow schema."""

import probatio

from custom_components.reiseverlauftracker.const import (
    CONF_ELEVATION_HYSTERESIS,
    CONF_END_DELAY,
    CONF_MARGIN,
    CONF_MAX_ACCURACY,
    CONF_MERGE_WINDOW,
    CONF_MIN_MOVEMENT,
    CONF_MIN_POINT_DISTANCE,
    CONF_MIN_STOP_DURATION,
    CONF_PLACE_NAMES,
    CONF_SCALE,
    CONF_STANDSTILL_SPEED,
    CONF_TANK_SIZE,
    CONF_TITLE_FORMAT,
    DEFAULT_ELEVATION_HYSTERESIS_M,
    DEFAULT_END_DELAY_MIN,
    DEFAULT_MARGIN_MIN,
    DEFAULT_MAX_ACCURACY_M,
    DEFAULT_MERGE_WINDOW_H,
    DEFAULT_MIN_MOVEMENT_M,
    DEFAULT_MIN_POINT_DISTANCE_M,
    DEFAULT_MIN_STOP_DURATION_MIN,
    DEFAULT_PLACE_NAMES,
    DEFAULT_SCALE,
    DEFAULT_STANDSTILL_SPEED_KMH,
    DEFAULT_TANK_LITRES,
    DEFAULT_TITLE_FORMAT,
    SECTION_DETECTION,
    SECTION_EXPORT,
    SECTION_LOGBOOK,
    SECTION_THRESHOLDS,
    TITLE_FORMATS,
)
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector


def _number(minimum: float, maximum: float, step: float, unit: str | None = None) -> selector.NumberSelector:
    config = selector.NumberSelectorConfig(min=minimum, max=maximum, step=step, mode=selector.NumberSelectorMode.BOX)
    if unit is not None:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


def get_options_schema() -> probatio.Schema:
    """
    Build the options form schema; current values are filled in by the flow.

    Returns:
        The probatio schema with the detection, export, logbook and threshold sections.

    """
    detection = probatio.Schema(
        {
            probatio.Required(CONF_END_DELAY, default=DEFAULT_END_DELAY_MIN): _number(1, 1440, 1, "min"),
            probatio.Required(CONF_MERGE_WINDOW, default=DEFAULT_MERGE_WINDOW_H): _number(0, 72, 0.5, "h"),
            probatio.Required(CONF_MIN_MOVEMENT, default=DEFAULT_MIN_MOVEMENT_M): _number(10, 10000, 10, "m"),
        },
    )
    export = probatio.Schema(
        {
            probatio.Required(CONF_TITLE_FORMAT, default=DEFAULT_TITLE_FORMAT): selector.SelectSelector(
                selector.SelectSelectorConfig(options=TITLE_FORMATS, translation_key=CONF_TITLE_FORMAT),
            ),
            probatio.Required(CONF_PLACE_NAMES, default=DEFAULT_PLACE_NAMES): selector.BooleanSelector(),
            probatio.Required(CONF_SCALE, default=DEFAULT_SCALE): _number(1, 4, 0.5),
            probatio.Required(CONF_MARGIN, default=DEFAULT_MARGIN_MIN): _number(0, 120, 1, "min"),
        },
    )
    thresholds = probatio.Schema(
        {
            probatio.Required(CONF_STANDSTILL_SPEED, default=DEFAULT_STANDSTILL_SPEED_KMH): _number(0, 20, 0.5, "km/h"),
            probatio.Required(CONF_MAX_ACCURACY, default=DEFAULT_MAX_ACCURACY_M): _number(5, 1000, 5, "m"),
            probatio.Required(CONF_MIN_POINT_DISTANCE, default=DEFAULT_MIN_POINT_DISTANCE_M): _number(0, 500, 1, "m"),
            probatio.Required(CONF_ELEVATION_HYSTERESIS, default=DEFAULT_ELEVATION_HYSTERESIS_M): _number(
                0, 50, 0.5, "m"
            ),
            probatio.Required(CONF_MIN_STOP_DURATION, default=DEFAULT_MIN_STOP_DURATION_MIN): _number(1, 120, 1, "min"),
        },
    )
    logbook = probatio.Schema(
        {
            probatio.Required(CONF_TANK_SIZE, default=DEFAULT_TANK_LITRES): _number(10, 500, 1, "L"),
        },
    )
    return probatio.Schema(
        {
            probatio.Required(SECTION_DETECTION): section(detection),
            probatio.Required(SECTION_EXPORT): section(export),
            probatio.Required(SECTION_LOGBOOK): section(logbook),
            probatio.Required(SECTION_THRESHOLDS): section(thresholds, {"collapsed": True}),
        },
    )


__all__ = ["get_options_schema"]
