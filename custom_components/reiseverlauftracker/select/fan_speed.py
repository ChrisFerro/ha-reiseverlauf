"""Fan speed select for reiseverlauftracker."""

from custom_components.reiseverlauftracker.api import FAN_SPEEDS, ReiseverlaufApiClientError
from custom_components.reiseverlauftracker.const import DOMAIN
from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

ENTITY_DESCRIPTIONS: tuple[SelectEntityDescription, ...] = (
    SelectEntityDescription(
        key="fan_speed",
        translation_key="fan_speed",
        options=list(FAN_SPEEDS),
    ),
)


class ReiseverlaufFanSpeedSelect(SelectEntity, ReiseverlaufEntity):
    """Select entity for the device's fan speed."""

    @property
    def current_option(self) -> str | None:
        """Return the fan speed read from coordinator data."""
        return self.coordinator.data.get("fan_speed")

    async def async_select_option(self, option: str) -> None:
        """Write the fan speed to the device."""
        if option not in FAN_SPEEDS:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_fan_speed",
                translation_placeholders={"speed": option},
            )

        client = self.coordinator.config_entry.runtime_data.client
        try:
            await client.async_set_fan_speed(option)
        except ReiseverlaufApiClientError as exception:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="fan_speed_set_failed",
            ) from exception

        await self.coordinator.async_request_refresh()
