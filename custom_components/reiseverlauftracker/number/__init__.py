"""Number platform for reiseverlauftracker: the fields of the logbook form."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.coordinator.logbook import FormField
from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfVolume

PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
    from custom_components.reiseverlauftracker.data import ReiseverlaufConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


@dataclass(frozen=True, kw_only=True)
class LogbookNumberEntityDescription(NumberEntityDescription):
    """Describes one field of the logbook form."""

    form_field: FormField
    currency: bool = False


def _level(key: str, form_field: FormField) -> LogbookNumberEntityDescription:
    return LogbookNumberEntityDescription(
        key=key,
        translation_key=key,
        form_field=form_field,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
    )


def _litres(key: str, form_field: FormField) -> LogbookNumberEntityDescription:
    return LogbookNumberEntityDescription(
        key=key,
        translation_key=key,
        form_field=form_field,
        native_min_value=0,
        native_max_value=1000,
        native_step=0.01,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=NumberDeviceClass.VOLUME,
        mode=NumberMode.BOX,
    )


def _amount(key: str, form_field: FormField) -> LogbookNumberEntityDescription:
    return LogbookNumberEntityDescription(
        key=key,
        translation_key=key,
        form_field=form_field,
        native_min_value=0,
        native_max_value=10000,
        native_step=0.01,
        device_class=NumberDeviceClass.MONETARY,
        mode=NumberMode.BOX,
        currency=True,
    )


ENTITY_DESCRIPTIONS = (
    LogbookNumberEntityDescription(
        key="logbook_odometer",
        translation_key="logbook_odometer",
        form_field=FormField.ODOMETER,
        native_min_value=0,
        native_max_value=9_999_999,
        native_step=1,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=NumberDeviceClass.DISTANCE,
        mode=NumberMode.BOX,
    ),
    _level("logbook_fuel", FormField.FUEL),
    _level("logbook_gas_1", FormField.GAS1),
    _level("logbook_gas_2", FormField.GAS2),
    _litres("logbook_fuel_litres", FormField.FUEL_LITRES),
    _amount("logbook_fuel_amount", FormField.FUEL_AMOUNT),
    _litres("logbook_gas_litres", FormField.GAS_LITRES),
    _amount("logbook_gas_amount", FormField.GAS_AMOUNT),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform."""
    async_add_entities(
        ReiseverlaufLogbookNumber(entry.runtime_data.coordinator, description) for description in ENTITY_DESCRIPTIONS
    )


class ReiseverlaufLogbookNumber(NumberEntity, ReiseverlaufEntity):
    """One field of the logbook form; the value lives in the form kept by the coordinator."""

    entity_description: LogbookNumberEntityDescription

    def __init__(
        self, coordinator: ReiseverlaufDataUpdateCoordinator, entity_description: LogbookNumberEntityDescription
    ) -> None:
        """Initialize the field; amounts use the currency of the instance."""
        super().__init__(coordinator, entity_description)
        if entity_description.currency:
            self._attr_native_unit_of_measurement = coordinator.hass.config.currency

    @property
    def native_value(self) -> float | None:
        """Return the value in the form."""
        return self.coordinator.logbook.draft.value(self.entity_description.form_field)

    async def async_set_native_value(self, value: float) -> None:
        """Change the value in the form."""
        self.coordinator.logbook.set_field(self.entity_description.form_field, value)
