"""Config flow schema for the user and reconfigure steps."""

import probatio

from custom_components.reiseverlauftracker.const import (
    CONF_ALTITUDE_ENTITY,
    CONF_DPLUS_ENTITY,
    CONF_DPLUS_ON_VALUE,
    CONF_OUTPUT_DIR,
    CONF_SPEED_ENTITY,
    CONF_TRACKER_ENTITY,
    DEFAULT_DPLUS_ON_VALUE,
    DEFAULT_OUTPUT_DIR,
)
from homeassistant.helpers import selector


def get_user_schema() -> probatio.Schema:
    """
    Build the schema for the user and reconfigure steps.

    Returns:
        The probatio schema for the data sources and the output folder.

    """
    return probatio.Schema(
        {
            probatio.Required(CONF_DPLUS_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["binary_sensor", "sensor"]),
            ),
            probatio.Required(CONF_DPLUS_ON_VALUE, default=DEFAULT_DPLUS_ON_VALUE): selector.TextSelector(),
            probatio.Required(CONF_TRACKER_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="device_tracker"),
            ),
            probatio.Required(CONF_SPEED_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor"),
            ),
            probatio.Optional(CONF_ALTITUDE_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor"),
            ),
            probatio.Required(CONF_OUTPUT_DIR, default=DEFAULT_OUTPUT_DIR): selector.TextSelector(),
        },
    )


__all__ = ["get_user_schema"]
