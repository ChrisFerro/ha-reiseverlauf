"""
The logbook form for an earlier time: which stop or time is chosen, and where its counters come from.

The selection offers "current", the remembered stops and "other time"; the
counters of a free time come from the running trip or from the raw data of
the export that contains it (docs/features/feat-09-nachtraege.md 6.2).
"""

from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.const import EXPORT_CHOICE_ALL, LATE_CHOICE_CURRENT, LATE_CHOICE_OTHER
from homeassistant.util import dt as dt_util

from .late_entry import (
    LatePoint,
    TripSpan,
    containing_trip,
    matching_stop,
    resolve_time,
    selectable_stops,
    stop_label,
    stop_point,
)
from .logbook import LogbookEntry, RecordedStop, Refill
from .places import async_place_name
from .trip_log import TripLog

if TYPE_CHECKING:
    from .base import ReiseverlaufDataUpdateCoordinator


class LateEntryForm:
    """Selection of the time a logbook entry is made for, and saving it."""

    def __init__(self, coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
        """Start with the current occasion chosen."""
        self.coordinator = coordinator
        self.choice = LATE_CHOICE_CURRENT
        self.time: datetime | None = None

    def options(self) -> list[str]:
        """Return "current", the stops newest first and "other time"."""
        return [LATE_CHOICE_CURRENT, *self._stops_by_label(), LATE_CHOICE_OTHER]

    def current_option(self) -> str:
        """Return the chosen option; after saving or discarding, or once a stop left the list, "current"."""
        if self.coordinator.logbook.late is None or self.choice not in self.options():
            return LATE_CHOICE_CURRENT
        return self.choice

    async def async_select(self, option: str) -> None:
        """Choose the current occasion, a stop or a free time, and fill the form for it."""
        keeper = self.coordinator.logbook
        if option == LATE_CHOICE_OTHER:
            self.choice = option
            self.time = self.time or dt_util.utcnow().replace(second=0, microsecond=0)
            keeper.select_late(await self.async_point_at(self.time))
            return
        stop = self._stops_by_label().get(option)
        self.choice = option if stop is not None else LATE_CHOICE_CURRENT
        keeper.select_late(stop_point(stop) if stop is not None else None)

    async def async_set_time(self, time: datetime) -> None:
        """Set the free time; it fills the form when "other time" is chosen."""
        self.time = dt_util.as_utc(time)
        if self.choice == LATE_CHOICE_OTHER:
            self.coordinator.logbook.select_late(await self.async_point_at(self.time))
        else:
            self.coordinator.async_update_listeners()

    async def async_save(self) -> LogbookEntry:
        """
        Save the form for the chosen time and return to the current occasion.

        Returns:
            The new or completed entry.

        """
        entry = await self.coordinator.logbook.async_save_late()
        self.choice = LATE_CHOICE_CURRENT
        return entry

    async def async_add(
        self,
        time: datetime,
        *,
        odometer_km: float | None = None,
        fuel: Refill | None = None,
        gas: Refill | None = None,
    ) -> LogbookEntry:
        """
        Add a refill at `time` from a service action; a stop close to `time` is taken as its stop.

        Returns:
            The new or completed entry.

        Raises:
            ValueError: The counters at `time` are estimated and no odometer is given.

        """
        keeper = self.coordinator.logbook
        time = dt_util.as_utc(time)
        stop = matching_stop(keeper.logbook, time, dt_util.utcnow())
        point = stop_point(stop) if stop is not None else await self.async_point_at(time)
        if point.estimated and odometer_km is None:
            raise ValueError("odometer")
        return await keeper.async_add_late(point, odometer_km=odometer_km, fuel=fuel, gas=gas)

    async def async_point_at(self, time: datetime) -> LatePoint:
        """Return counters, position and place at a free time."""
        coordinator = self.coordinator
        spans = self._spans()
        span = containing_trip(spans, time)
        track = await self._async_track(span) if span is not None else None
        point = resolve_time(time, coordinator.logbook.logbook, spans, track)
        if point.lat is not None:
            place = await async_place_name(coordinator.hass, coordinator.settings, point.lat, point.lon)
            point = replace(point, place=place)
        return point

    def _stops_by_label(self) -> dict[str, RecordedStop]:
        coordinator = self.coordinator
        tz = dt_util.get_default_time_zone()
        now = dt_util.utcnow()
        language = coordinator.hass.config.language
        minimum = coordinator.settings.min_stop_duration
        return {
            stop_label(stop, tz, language, minimum, now): stop
            for stop in selectable_stops(coordinator.logbook.logbook, self._chosen_trip())
        }

    def _chosen_trip(self) -> datetime | None:
        choice = self.coordinator.current_export_choice()
        if choice is None or choice == EXPORT_CHOICE_ALL:
            return None
        exports = self.coordinator.find_exports(choice)
        return exports[0].start if exports else None

    def _spans(self) -> list[TripSpan]:
        coordinator = self.coordinator
        spans = [
            TripSpan(info.start, info.end, info.counter_start, info.folder)
            for info in coordinator.exports
            if info.automatic
        ]
        if (log := coordinator.log) is not None:
            spans = [s for s in spans if s.start != log.start]
            spans.append(TripSpan(log.start, None, log.counter_start))
        return spans

    async def _async_track(self, span: TripSpan) -> TripLog | None:
        coordinator = self.coordinator
        if (log := coordinator.log) is not None and log.start == span.start:
            return log
        info = next((i for i in coordinator.exports if i.folder == span.folder), None)
        return await coordinator.async_raw_log(info) if info is not None else None
