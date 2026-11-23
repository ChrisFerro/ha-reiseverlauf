"""Button platform for reiseverlauftracker: the logbook, travel costs and tour forms."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from custom_components.reiseverlauftracker.const import DOMAIN
from custom_components.reiseverlauftracker.coordinator.cost_form import CostFormError
from custom_components.reiseverlauftracker.coordinator.ferries import FerryError
from custom_components.reiseverlauftracker.coordinator.tours import TourError
from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import slugify

PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
    from custom_components.reiseverlauftracker.data import ReiseverlaufConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


def _not_editing(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    """Refuse to add an entry while a stored one fills the form, so no second entry arises."""
    if coordinator.logbook.editing is not None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="logbook_editing")


async def _save(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    _not_editing(coordinator)
    await coordinator.async_save_logbook_form()


async def _save_late(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    _not_editing(coordinator)
    if coordinator.logbook.late is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_late_time")
    await coordinator.late_form.async_save()


async def _update(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    try:
        await coordinator.edit_form.async_save()
    except ValueError as err:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_entry_chosen") from err


async def _remove(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    try:
        await coordinator.edit_form.async_remove()
    except ValueError as err:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_entry_chosen") from err


async def _save_cost(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    try:
        await coordinator.cost_form.async_save()
    except CostFormError as err:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key=err.args[0]) from err


async def _update_cost(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    try:
        await coordinator.cost_form.async_update()
    except CostFormError as err:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key=err.args[0]) from err


async def _remove_cost(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    try:
        await coordinator.cost_form.async_remove()
    except CostFormError as err:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key=err.args[0]) from err


async def _no_toll(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    try:
        await coordinator.cost_form.async_toggle_no_toll()
    except CostFormError as err:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key=err.args[0]) from err


async def _tour(coordinator: ReiseverlaufDataUpdateCoordinator, *, update: bool) -> None:
    form = coordinator.tour_form
    try:
        await (form.async_update() if update else form.async_create())
    except TourError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key=err.key, translation_placeholders=err.placeholders
        ) from err
    except OSError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="export_failed", translation_placeholders={"error": str(err)}
        ) from err


async def _tour_create(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    await _tour(coordinator, update=False)


async def _tour_update(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    await _tour(coordinator, update=True)


async def _mark_ferry(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    """Switch the ferry mark of the stop chosen for a late entry (docs/features/feat-12-kartensymbole.md 6.3)."""
    try:
        await coordinator.late_form.async_toggle_ferry()
    except FerryError as err:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key=err.reason) from err


async def _discard(coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
    coordinator.logbook.discard()


@dataclass(frozen=True, kw_only=True)
class LogbookButtonEntityDescription(ButtonEntityDescription):
    """Describes a button of the logbook form."""

    press_fn: Callable[[ReiseverlaufDataUpdateCoordinator], Coroutine[Any, Any, None]]
    # German object id for names whose umlauts would be dropped (ä → a); None derives it from the name.
    object_id: str | None = None


ENTITY_DESCRIPTIONS = (
    LogbookButtonEntityDescription(key="logbook_save", translation_key="logbook_save", press_fn=_save),
    LogbookButtonEntityDescription(key="logbook_discard", translation_key="logbook_discard", press_fn=_discard),
    LogbookButtonEntityDescription(key="logbook_late", translation_key="logbook_late", press_fn=_save_late),
    LogbookButtonEntityDescription(
        key="logbook_update", translation_key="logbook_update", press_fn=_update, object_id="fahrtenbuch_aendern"
    ),
    LogbookButtonEntityDescription(
        key="logbook_remove", translation_key="logbook_remove", press_fn=_remove, object_id="fahrtenbuch_loeschen"
    ),
    LogbookButtonEntityDescription(key="travel_cost_save", translation_key="travel_cost_save", press_fn=_save_cost),
    LogbookButtonEntityDescription(
        key="travel_cost_update",
        translation_key="travel_cost_update",
        press_fn=_update_cost,
        object_id="reisekosten_aendern",
    ),
    LogbookButtonEntityDescription(
        key="travel_cost_remove",
        translation_key="travel_cost_remove",
        press_fn=_remove_cost,
        object_id="reisekosten_loeschen",
    ),
    LogbookButtonEntityDescription(key="no_toll", translation_key="no_toll", press_fn=_no_toll),
    LogbookButtonEntityDescription(key="tour_create", translation_key="tour_create", press_fn=_tour_create),
    LogbookButtonEntityDescription(key="tour_update", translation_key="tour_update", press_fn=_tour_update),
    LogbookButtonEntityDescription(
        key="mark_ferry", translation_key="mark_ferry", press_fn=_mark_ferry, object_id="als_faehre_markieren"
    ),
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

    def __init__(
        self, coordinator: ReiseverlaufDataUpdateCoordinator, entity_description: LogbookButtonEntityDescription
    ) -> None:
        """Initialize the button; a fixed object id is prefixed with the device name like the derived ones."""
        super().__init__(coordinator, entity_description)
        if entity_description.object_id is not None:
            self.entity_id = f"button.{slugify(coordinator.config_entry.title)}_{entity_description.object_id}"

    async def async_press(self) -> None:
        """Run the action of the button."""
        await self.entity_description.press_fn(self.coordinator)
