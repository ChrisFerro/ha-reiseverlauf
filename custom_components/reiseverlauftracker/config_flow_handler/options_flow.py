"""Options flow for reiseverlauftracker."""

from typing import Any

from homeassistant import config_entries

from .schemas import get_options_schema


class ReiseverlaufOptionsFlow(config_entries.OptionsFlow):
    """Let the user tune trip detection, export and thresholds after setup."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Show and process the options form.

        Returns:
            The form, or the stored options.

        """
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(get_options_schema(), self.config_entry.options),
        )


__all__ = ["ReiseverlaufOptionsFlow"]
