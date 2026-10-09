"""Config flow for reiseverlauftracker — user setup and reconfigure."""

from typing import Any

from custom_components.reiseverlauftracker.const import CONF_OUTPUT_DIR, CONF_TRACKER_ENTITY, DOMAIN
from homeassistant import config_entries

from .options_flow import ReiseverlaufOptionsFlow
from .schemas import get_user_schema
from .validators import InvalidOutputDirError, normalize_output_dir


class ReiseverlaufConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up one vehicle, identified by its position tracker."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ReiseverlaufOptionsFlow:
        """
        Return the options flow for this handler.

        Returns:
            The options flow instance.

        """
        return ReiseverlaufOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Handle a flow started by the user.

        Returns:
            The form, or the created config entry.

        """
        errors: dict[str, str] = {}

        if user_input is not None:
            data, errors = _validate(user_input)
            if not errors:
                await self.async_set_unique_id(data[CONF_TRACKER_ENTITY])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=self._tracker_name(data[CONF_TRACKER_ENTITY]), data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(get_user_schema(), user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Change the data sources or the output folder of an existing entry.

        Returns:
            The form, or the abort that follows the entry update.

        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            data, errors = _validate(user_input)
            if not errors:
                await self.async_set_unique_id(data[CONF_TRACKER_ENTITY])
                if data[CONF_TRACKER_ENTITY] != entry.unique_id:
                    self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(entry, unique_id=data[CONF_TRACKER_ENTITY], data=data)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(get_user_schema(), user_input or entry.data),
            errors=errors,
        )

    def _tracker_name(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        return state.name if state is not None else entity_id


def _validate(user_input: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """
    Normalise the submitted data.

    Returns:
        The cleaned data and the errors for the form; no errors means the data is valid.

    """
    try:
        output_dir = normalize_output_dir(user_input[CONF_OUTPUT_DIR])
    except InvalidOutputDirError:
        return user_input, {CONF_OUTPUT_DIR: "invalid_output_dir"}
    return {**user_input, CONF_OUTPUT_DIR: output_dir}, {}


__all__ = ["ReiseverlaufConfigFlowHandler"]
