"""
The tour form: period and title for a new tour, or the changes of the tour chosen in the export selection.

With a trip chosen, the period starts at the trip's start and ends now, without a
title. With a tour chosen, the form shows its period and title, and "update" applies
them (docs/features/feat-10-tour.md 6.2). Values entered by hand hold until another
export is chosen.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.const import EXPORT_CHOICE_ALL
from homeassistant.util import dt as dt_util

from .tours import TourError

if TYPE_CHECKING:
    from .base import ReiseverlaufDataUpdateCoordinator
    from .exports import ExportInfo


class TourForm:
    """Values of the tour form and the actions of its buttons."""

    def __init__(self, coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
        """Start with the values that follow the export selection."""
        self.coordinator = coordinator
        self._start: datetime | None = None
        self._end: datetime | None = None
        self._title: str | None = None
        self._key: str | None = None

    def chosen(self) -> ExportInfo | None:
        """Return the export chosen in the export selection, or None for "all exports"."""
        choice = self.coordinator.current_export_choice()
        if choice is None or choice == EXPORT_CHOICE_ALL:
            return None
        exports = self.coordinator.find_exports(choice)
        return exports[0] if exports else None

    def _follow_choice(self) -> ExportInfo | None:
        """Drop values entered for another export, then return the chosen one."""
        chosen = self.chosen()
        key = chosen.folder if chosen else None
        if key != self._key:
            self._start = self._end = self._title = None
            self._key = key
        return chosen

    @property
    def start(self) -> datetime | None:
        """Return the start of the period: entered by hand, else that of the chosen trip or tour."""
        chosen = self._follow_choice()
        return self._start or (chosen.start if chosen else None)

    @property
    def end(self) -> datetime:
        """Return the end of the period: entered by hand, else that of the chosen tour, else now."""
        chosen = self._follow_choice()
        if self._end is not None:
            return self._end
        return chosen.end if chosen is not None and chosen.is_tour else dt_util.utcnow()

    @property
    def title(self) -> str:
        """Return the title: entered by hand, else that of the chosen tour, else empty for a suggestion."""
        chosen = self._follow_choice()
        if self._title is not None:
            return self._title
        return chosen.title if chosen is not None and chosen.is_tour else ""

    def set_start(self, value: datetime) -> None:
        """Set the start for the chosen export."""
        self._follow_choice()
        self._start = dt_util.as_utc(value)
        self.coordinator.async_update_listeners()

    def set_end(self, value: datetime) -> None:
        """Set the end for the chosen export."""
        self._follow_choice()
        self._end = dt_util.as_utc(value)
        self.coordinator.async_update_listeners()

    def set_title(self, value: str) -> None:
        """Set the title for the chosen export; empty means a suggested title."""
        self._follow_choice()
        self._title = value.strip()
        self.coordinator.async_update_listeners()

    async def async_create(self) -> ExportInfo:
        """
        Create a tour from the form and choose it in the export selection.

        Returns:
            The new tour.

        Raises:
            TourError: No start, or the tour cannot be made.

        """
        start = self.start
        if start is None:
            raise TourError("tour_without_start")
        chosen = self.chosen()
        title = self.title if chosen is None or not chosen.is_tour or self._title is not None else ""
        info = await self.coordinator.tours.async_create(start, self.end, title or None)
        self._choose(info)
        return info

    async def async_update(self) -> ExportInfo:
        """
        Apply title and period of the form to the tour chosen in the export selection.

        Returns:
            The new version of the tour.

        Raises:
            TourError: No tour is chosen, or it cannot be made.

        """
        chosen = self.chosen()
        if chosen is None or not chosen.is_tour:
            raise TourError("tour_not_chosen")
        title = self._title
        info = await self.coordinator.tours.async_change(chosen, title=title, start=self._start, end=self._end)
        self._choose(info)
        return info

    def _choose(self, info: ExportInfo) -> None:
        """Choose `info` in the export selection, so the form shows the tour."""
        tz = dt_util.get_default_time_zone()
        self.coordinator.export_choice = info.label(tz)
        self._start = self._end = self._title = None
        self._key = info.folder
        self.coordinator.async_update_listeners()
