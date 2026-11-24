"""
Ferry crossings: detected at the end of a stop, or marked by hand (docs/features/feat-12-kartensymbole.md 6.2, 6.3).

A crossing counts neither as distance nor as driving time (5.10). Marking a stop
counts the trip's distance anew and moves the logbook counters measured after the
crossing by the difference, so the distances between later entries stay right.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.const import LOGGER
from homeassistant.util import dt as dt_util

from .export_runner import NOMINATIM_INTERVAL_S, media_base
from .exports import write_raw
from .places import async_on_water
from .trip_log import FerryMark, TrackCounters, TripLog, TripStop

if TYPE_CHECKING:
    from .base import ReiseverlaufDataUpdateCoordinator
    from .exports import ExportInfo

# A time given for a stop may be a little off its start, e.g. rounded to the minute.
STOP_TOLERANCE = timedelta(minutes=2)


class FerryError(Exception):
    """A stop cannot be marked; `reason` is the translation key of the message."""

    def __init__(self, reason: str) -> None:
        """Remember why."""
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class FerryChange:
    """A stop marked or unmarked as ferry crossing, and how the trip's distance changed."""

    stop: TripStop
    delta: TrackCounters


class Ferries:
    """Detects ferry crossings of the running trip and marks stops by hand."""

    def __init__(self, coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
        """Keep the coordinator whose trip log and logbook are changed."""
        self.coordinator = coordinator

    def check(self, stop: TripStop) -> None:
        """Ask in the background whether the stop that just ended was a ferry crossing."""
        coordinator = self.coordinator
        log = coordinator.log
        if log is None or stop.ferry is not None or (probe := log.ferry_probe(stop)) is None:
            return

        async def check() -> None:
            # Keep Nominatim's limit of one request a second after the stop's place name.
            await asyncio.sleep(NOMINATIM_INTERVAL_S)
            water = await async_on_water(coordinator.hass, coordinator.settings, probe.lat, probe.lon)
            current = coordinator.log
            if not water or current is not log:
                return
            known = next((s for s in log.stops if s.start == stop.start), None)
            if known is None or known.ferry is not None:
                return
            LOGGER.info("Stop from %s was a ferry crossing", stop.start)
            await self._async_apply_running(log, stop.start, FerryMark.AUTO)

        coordinator.config_entry.async_create_task(coordinator.hass, check(), "reiseverlauftracker ferry check")

    async def async_mark(self, trip_start: datetime, time: datetime, ferry: bool) -> FerryChange:
        """
        Mark the stop of a trip at `time` as ferry crossing, or remove the mark, and renew the export.

        Returns:
            The changed stop and how the trip's distance changed.

        Raises:
            FerryError: No such stop, or the trip's raw data are missing.

        """
        coordinator = self.coordinator
        mark = FerryMark.HAND if ferry else FerryMark.NONE
        log = coordinator.log
        if log is not None and log.start == trip_start:
            change = await self._async_apply_running(log, _stop_at(log, time).start, mark)
            info = _export_of(coordinator, trip_start)
            if info is not None and await coordinator.async_raw_log(info) is not None:
                await self._async_write_raw(info, log)
                await coordinator.refresher.async_refresh(trip_start)
            return change
        info = _export_of(coordinator, trip_start)
        if info is None:
            raise FerryError("unknown_stop")
        raw = await coordinator.async_raw_log(info)
        if raw is None:
            raise FerryError("ferry_without_raw_data")
        change = await self._async_apply_closed(info, raw, _stop_at(raw, time), mark)
        await coordinator.refresher.async_refresh(trip_start)
        return change

    async def async_check_closed(self, info: ExportInfo) -> int:
        """
        Ask once for each stop of a finished trip not checked yet whether it was a ferry crossing (6.8).

        Meant for trips from before the detection; their export is not renewed here.

        Returns:
            How many stops turned out to be ferry crossings.

        """
        coordinator = self.coordinator
        raw = await coordinator.async_raw_log(info)
        if raw is None:
            return 0
        found = 0
        for stop in [s for s in raw.stops if s.end is not None and s.ferry is None]:
            if (probe := raw.ferry_probe(stop)) is None:
                continue
            await asyncio.sleep(NOMINATIM_INTERVAL_S)
            if await async_on_water(coordinator.hass, coordinator.settings, probe.lat, probe.lon):
                LOGGER.info("Stop from %s of the trip %s was a ferry crossing", stop.start, info.folder)
                await self._async_apply_closed(info, raw, stop, FerryMark.AUTO)
                found += 1
        return found

    async def _async_apply_closed(self, info: ExportInfo, raw: TripLog, stop: TripStop, mark: FerryMark) -> FerryChange:
        """Mark a stop in the raw data of a finished trip, store them and move the later logbook counters."""
        after = _counter_before(self.coordinator, raw, stop)
        before = raw.counters_at(info.end) or raw.counters
        changed = raw.set_ferry(stop.start, mark)
        if changed is None:
            raise FerryError("unknown_stop")
        delta = (raw.counters_at(info.end) or raw.counters) - before
        await self._async_write_raw(info, raw)
        await self._async_shift(info.start, changed, after, delta, closed_trip=True)
        return FerryChange(changed, delta)

    async def _async_apply_running(self, log: TripLog, start: datetime, mark: FerryMark) -> FerryChange:
        coordinator = self.coordinator
        stop = next(s for s in log.stops if s.start == start)
        after = _counter_before(coordinator, log, stop)
        before = log.counters
        changed = log.set_ferry(start, mark)
        if changed is None:
            raise FerryError("unknown_stop")
        delta = log.counters - before
        coordinator.logbook.set_running_trip(log.distance_m, log.ascent_m, log.descent_m)
        await self._async_shift(log.start, changed, after, delta, closed_trip=False)
        coordinator.save_log()
        coordinator.publish()
        return FerryChange(changed, delta)

    async def _async_shift(
        self, trip_start: datetime, stop: TripStop, after: float | None, delta: TrackCounters, *, closed_trip: bool
    ) -> None:
        keeper = self.coordinator.logbook
        keeper.set_stop_ferry(stop.start, stop.is_ferry)
        if after is None:
            LOGGER.warning("Counters at the stop from %s are unknown; the logbook entries keep theirs", stop.start)
            return
        await keeper.async_shift_counters(trip_start, after, delta, closed_trip=closed_trip)

    async def _async_write_raw(self, info: ExportInfo, log: TripLog) -> None:
        coordinator = self.coordinator
        await coordinator.hass.async_add_executor_job(
            write_raw, media_base(coordinator.hass, coordinator.settings), info, log.as_dict()
        )


def _stop_at(log: TripLog, time: datetime) -> TripStop:
    """
    Return the closed stop of `log` that contains `time` or began close to it.

    Raises:
        FerryError: No such stop.

    """
    time = dt_util.as_utc(time)
    candidates = [
        s for s in log.stops if s.end is not None and s.start - STOP_TOLERANCE <= time <= s.end + STOP_TOLERANCE
    ]
    stop = min(candidates, key=lambda s: abs((s.start - time).total_seconds()), default=None)
    if stop is None:
        raise FerryError("unknown_stop")
    return stop


def _counter_before(coordinator: ReiseverlaufDataUpdateCoordinator, log: TripLog, stop: TripStop) -> float | None:
    """Return the logbook distance counter when `stop` began: from the remembered stop, else from the log."""
    known = next((s for s in coordinator.logbook.logbook.stops if s.start == stop.start), None)
    if known is not None:
        return known.distance_counter_m
    counters = log.counters_at(stop.start)
    return counters.distance_m if counters is not None else None


def _export_of(coordinator: ReiseverlaufDataUpdateCoordinator, trip_start: datetime) -> ExportInfo | None:
    return next((i for i in coordinator.exports if i.automatic and i.start == trip_start), None)
