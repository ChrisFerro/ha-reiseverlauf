"""
Draw the map of one export anew with tiles (docs/features/feat-12-kartensymbole.md 6.8).

Old exports get their map symbols, base map and legend this way. A trip from
before the ferry detection has its stops checked for ferries once, and its
arrival is looked up once more for a camp site. No "ended" or tour event fires.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.const import EXPORT_CHOICE_ALL
from custom_components.reiseverlauftracker.export import NoMovementError, NotEnoughPointsError

from .tours import TourError

if TYPE_CHECKING:
    from .base import ReiseverlaufDataUpdateCoordinator
    from .exports import ExportInfo


class RedrawError(Exception):
    """
    The map cannot be drawn anew; `key` is the translation key of the message.

    `invalid` tells a wrong request (a validation error) from a failure while drawing.
    """

    def __init__(self, key: str, placeholders: dict[str, str] | None = None, *, invalid: bool = True) -> None:
        """Remember why."""
        super().__init__(key)
        self.key = key
        self.invalid = invalid
        self.placeholders = placeholders or {}


@dataclass(frozen=True, slots=True)
class RedrawResult:
    """The export with its new map, and how many ferry crossings were found on the way."""

    info: ExportInfo
    ferries_found: int = 0


def chosen_export(coordinator: ReiseverlaufDataUpdateCoordinator, choice: str | None) -> ExportInfo:
    """
    Return the one export a selection label or folder name refers to; without one, the export selection's choice.

    Raises:
        RedrawError: Nothing chosen, "all" chosen, or no such export.

    """
    choice = choice or coordinator.current_export_choice()
    if choice is None:
        raise RedrawError("no_export_chosen")
    if choice == EXPORT_CHOICE_ALL:
        raise RedrawError("redraw_all")
    exports = coordinator.find_exports(choice)
    if not exports:
        raise RedrawError("export_not_found", {"export": choice})
    return exports[0]


async def async_redraw_map(coordinator: ReiseverlaufDataUpdateCoordinator, choice: str | None) -> RedrawResult:
    """
    Draw the map, base map and composite image of one trip or tour anew from its raw data.

    Returns:
        The renewed export and how many stops turned out to be ferry crossings.

    Raises:
        RedrawError: No single export chosen, no raw data, no movement, or the files or tiles failed.

    """
    info = chosen_export(coordinator, choice)
    if info.is_tour:
        try:
            tour = await coordinator.tours.async_redraw(info)
        except TourError as err:
            raise RedrawError(err.key, err.placeholders) from err
        except OSError as err:
            raise RedrawError("export_failed", {"error": str(err)}, invalid=False) from err
        if tour.base_map is None:
            raise RedrawError("map_tiles_failed", invalid=False)
        return RedrawResult(tour)

    if await coordinator.async_raw_log(info) is None:
        raise RedrawError("redraw_without_raw_data")
    found = 0
    log = coordinator.log
    # The running trip's stops were checked when they ended.
    if info.automatic and (log is None or log.start != info.start):
        found = await coordinator.ferries.async_check_closed(info)
    try:
        refreshed, redrawn = await coordinator.refresher.async_redraw(info)
    except (NotEnoughPointsError, NoMovementError) as err:
        raise RedrawError("no_movement") from err
    except OSError as err:
        raise RedrawError("export_failed", {"error": str(err)}, invalid=False) from err
    if not redrawn:
        raise RedrawError("map_tiles_failed", invalid=False)
    return RedrawResult(refreshed, found)
