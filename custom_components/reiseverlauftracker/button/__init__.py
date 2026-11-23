"""Button platform for reiseverlauftracker: the logbook form (save, discard, late entry) and the travel costs form."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from custom_components.reiseverlauftracker.const import DOMAIN
from custom_components.reiseverlauftracker.coordinator.cost_form import CostFormError
from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.exceptions import ServiceValidationError

PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
    from custom_components.reiseverlauftracker.data import ReiseverlaufConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def _save(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    await coordinator.async_save_logbook_form()


async def _save_late(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    if coordinator.logbook.late is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_late_time")
    await coordinator.late_form.async_save()


async def _save_cost(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    try:
        await coordinator.cost_form.async_save()
    except CostFormError as err:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key=err.args[0]) from err


async def _no_toll(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    try:
        await coordinator.cost_form.async_toggle_no_toll()
    except CostFormError as err:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key=err.args[0]) from err


async def _discard(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    coordinator.logbook.discard()


@dataclass(frozen=True, kw_only=True)
class LogbookButtonEntityDescription(ButtonEntityDescription):
    """Describes a button of the logbook form."""

    press_fn: Callable[[ReiseverlaufDataUpdateCoordinator], Coroutine[Any, Any, None]]


ENTITY_DESCRIPTIONS = (
    LogbookButtonEntityDescription(key="logbook_save", translation_key="logbook_save", press_fn=_save),
    LogbookButtonEntityDescription(key="logbook_discard", translation_key="logbook_discard", press_fn=_discard),
    LogbookButtonEntityDescription(key="logbook_late", translation_key="logbook_late", press_fn=_save_late),
    LogbookButtonEntityDescription(key="travel_cost_save", translation_key="travel_cost_save", press_fn=_save_cost),
    LogbookButtonEntityDescription(key="no_toll", translation_key="no_toll", press_fn=_no_toll),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    async_add_entities(
        ReiseverlaufLogbookButton(entry.runtime_data.coordinator, description) for description in ENTITY_DESCRIPTIONS
    )


class ReiseverlaufLogbookButton(ButtonEntity, ReiseverlaufEntity):
    """Saves the form as a logbook entry, or discards it."""

    entity_description: LogbookButtonEntityDescription

    async def async_press(self) -> None:
        """Run the action of the button."""
        await self.entity_description.press_fn(self.coordinator)
