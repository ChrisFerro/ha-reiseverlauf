"""Options flow schema."""

import voluptuous as vol

from custom_components.reiseverlauftracker.const import (
    CONF_ELEVATION_HYSTERESIS,
    CONF_END_DELAY,
    CONF_MARGIN,
    CONF_MAX_ACCURACY,
    CONF_MERGE_WINDOW,
    CONF_MIN_MOVEMENT,
    CONF_MIN_POINT_DISTANCE,
    CONF_PLACE_NAMES,
    CONF_SCALE,
    CONF_STANDSTILL_SPEED,
    CONF_TITLE_FORMAT,
    DEFAULT_ELEVATION_HYSTERESIS_M,
    DEFAULT_END_DELAY_MIN,
    DEFAULT_MARGIN_MIN,
    DEFAULT_MAX_ACCURACY_M,
    DEFAULT_MERGE_WINDOW_H,
    DEFAULT_MIN_MOVEMENT_M,
    DEFAULT_MIN_POINT_DISTANCE_M,
    DEFAULT_PLACE_NAMES,
    DEFAULT_SCALE,
    DEFAULT_STANDSTILL_SPEED_KMH,
    DEFAULT_TITLE_FORMAT,
    SECTION_DETECTION,
    SECTION_EXPORT,
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


def get_options_schema() -> vol.Schema:
    """
    Build the options form schema; current values are filled in by the flow.

    Returns:
        The voluptuous schema with the detection, export and threshold sections.

    """
    detection = vol.Schema(
        {
            vol.Required(CONF_END_DELAY, default=DEFAULT_END_DELAY_MIN): _number(1, 1440, 1, "min"),
            vol.Required(CONF_MERGE_WINDOW, default=DEFAULT_MERGE_WINDOW_H): _number(0, 72, 0.5, "h"),
            vol.Required(CONF_MIN_MOVEMENT, default=DEFAULT_MIN_MOVEMENT_M): _number(10, 10000, 10, "m"),
        },
    )
    export = vol.Schema(
        {
            vol.Required(CONF_TITLE_FORMAT, default=DEFAULT_TITLE_FORMAT): selector.SelectSelector(
                selector.SelectSelectorConfig(options=TITLE_FORMATS, translation_key=CONF_TITLE_FORMAT),
            ),
            vol.Required(CONF_PLACE_NAMES, default=DEFAULT_PLACE_NAMES): selector.BooleanSelector(),
            vol.Required(CONF_SCALE, default=DEFAULT_SCALE): _number(1, 4, 0.5),
            vol.Required(CONF_MARGIN, default=DEFAULT_MARGIN_MIN): _number(0, 120, 1, "min"),
        },
    )
    thresholds = vol.Schema(
        {
            vol.Required(CONF_STANDSTILL_SPEED, default=DEFAULT_STANDSTILL_SPEED_KMH): _number(0, 20, 0.5, "km/h"),
            vol.Required(CONF_MAX_ACCURACY, default=DEFAULT_MAX_ACCURACY_M): _number(5, 1000, 5, "m"),
            vol.Required(CONF_MIN_POINT_DISTANCE, default=DEFAULT_MIN_POINT_DISTANCE_M): _number(0, 500, 1, "m"),
            vol.Required(CONF_ELEVATION_HYSTERESIS, default=DEFAULT_ELEVATION_HYSTERESIS_M): _number(0, 50, 0.5, "m"),
        },
    )
    return vol.Schema(
        {
            vol.Required(SECTION_DETECTION): section(detection),
            vol.Required(SECTION_EXPORT): section(export),
            vol.Required(SECTION_THRESHOLDS): section(thresholds, {"collapsed": True}),
        },
    )


__all__ = ["get_options_schema"]
