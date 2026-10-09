"""Config flow schema for the user and reconfigure steps."""

import voluptuous as vol

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


def get_user_schema() -> vol.Schema:
    """
    Build the schema for the user and reconfigure steps.

    Returns:
        The voluptuous schema for the data sources and the output folder.

    """
    return vol.Schema(
        {
            vol.Required(CONF_DPLUS_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["binary_sensor", "sensor"]),
            ),
            vol.Required(CONF_DPLUS_ON_VALUE, default=DEFAULT_DPLUS_ON_VALUE): selector.TextSelector(),
            vol.Required(CONF_TRACKER_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="device_tracker"),
            ),
            vol.Required(CONF_SPEED_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor"),
            ),
            vol.Optional(CONF_ALTITUDE_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor"),
            ),
            vol.Required(CONF_OUTPUT_DIR, default=DEFAULT_OUTPUT_DIR): selector.TextSelector(),
        },
    )


__all__ = ["get_user_schema"]
