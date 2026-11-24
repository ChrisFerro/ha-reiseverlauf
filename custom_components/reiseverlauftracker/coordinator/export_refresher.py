"""
Renews the export of a finished trip after its logbook entries or travel costs changed.

Changes are collected for `REFRESH_DELAY`, then each trip is renewed once:
statistics, map symbols, composite image and `export.json` (docs/features/feat-09-nachtraege.md 6.4,
docs/features/feat-12-kartensymbole.md 6.7).
Only automatic exports are renewed, never a trip that is still active (its export follows at its
end), and no "ended" event fires.
"""

from dataclasses import replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.const import DOMAIN, LOGGER
from custom_components.reiseverlauftracker.export import (
    LogbookFigures,
    MapMarker,
    NoMovementError,
    NotEnoughPointsError,
)
from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.loader import async_get_loaded_integration

from .export_runner import async_arrival_stay, async_refresh
from .map_symbols import trip_markers
from .trip_detector import TripPhase

if TYPE_CHECKING:
    from .base import ReiseverlaufDataUpdateCoordinator
    from .exports import ExportInfo
    from .trip_log import TripLog

REFRESH_DELAY = timedelta(seconds=30)


class ExportRefresher:
    """Collects changed trips and renews their exports."""

    def __init__(self, coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
        """Start with nothing to renew."""
        self.coordinator = coordinator
        self._pending: set[datetime] = set()
        self._unsub: CALLBACK_TYPE | None = None

    def schedule(self, trip_start: datetime) -> None:
        """Renew the export of the trip that started at `trip_start` once the changes have settled."""
        coordinator = self.coordinator
        log = coordinator.log
        if log is not None and log.start == trip_start and coordinator.detector.phase is TripPhase.ACTIVE:
            return
        self._pending.add(trip_start)
        if self._unsub is None:
            self._unsub = async_call_later(coordinator.hass, REFRESH_DELAY, self._on_delay)

    def cancel(self) -> None:
        """Forget pending renewals, e.g. on unload."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        self._pending.clear()

    @callback
    def _on_delay(self, _now: datetime) -> None:
        self._unsub = None
        starts, self._pending = sorted(self._pending), set()
        coordinator = self.coordinator
        coordinator.config_entry.async_create_background_task(
            coordinator.hass, self._async_refresh_all(starts), "reiseverlauftracker export refresh"
        )

    async def _async_refresh_all(self, starts: list[datetime]) -> None:
        for start in starts:
            await self.async_refresh(start)

    async def async_refresh(self, trip_start: datetime) -> ExportInfo | None:
        """
        Renew the export of one trip now.

        Returns:
            The renewed export, or None if the trip has no automatic export or renewing failed.

        """
        info = next((i for i in self.coordinator.exports if i.automatic and i.start == trip_start), None)
        if info is None:
            return None
        try:
            refreshed, _ = await self._async_renew(info, redraw=False)
        except (NotEnoughPointsError, NoMovementError, OSError) as err:
            LOGGER.warning("Export %s could not be renewed: %s", info.folder, err)
            return None
        return refreshed

    async def async_redraw(self, info: ExportInfo) -> tuple[ExportInfo, bool]:
        """
        Renew a trip export, automatic or manual, and draw its map anew with tiles.

        The arrival is looked up once more for a camp site (docs/features/feat-12-kartensymbole.md 5.7, 6.8).

        Returns:
            The renewed export, and whether the map could be drawn with tiles.

        Raises:
            NotEnoughPointsError: Fewer than two usable positions.
            NoMovementError: The vehicle never left the minimum movement radius.
            OSError: The output folder cannot be written.

        """
        return await self._async_renew(info, redraw=True)

    async def _async_renew(self, info: ExportInfo, *, redraw: bool) -> tuple[ExportInfo, bool]:
        coordinator = self.coordinator
        log = await coordinator.async_raw_log(info)
        if info.automatic:
            figures = self._figures(info, log)
        else:
            figures = info.logbook
        data = None
        markers: tuple[MapMarker, ...] = ()
        if log is not None:
            positions, speed, altitude = log.export_inputs()
            data = ([p for p in positions if p.time <= info.end], speed, altitude)
            if info.automatic:
                # The raw data know where each stop was, also for exports from before the stops kept it,
                # and which stops were ferry crossings (docs/features/feat-12-kartensymbole.md 6.3).
                logged = log.export_stops(info.end, coordinator.settings.min_stop_duration)
                ferries = {s.start: s.ferry for s in logged}
                info = replace(info, stops=tuple(replace(s, ferry=ferries.get(s.start, s.ferry)) for s in info.stops))
                entries = coordinator.logbook.logbook.trip_entries(info.start)
                markers = trip_markers(logged or info.stops, entries, data[0])
            else:
                entries = coordinator.logbook.logbook.entries_between(info.start, info.end)
                markers = trip_markers((), entries, data[0])
            if redraw and coordinator.settings.place_names:
                stay = await async_arrival_stay(coordinator.hass, coordinator.settings, data[0])
                info = replace(info, arrival_stay=stay)
        else:
            LOGGER.info("Export %s has no raw data; only its metadata gets the new logbook figures", info.folder)
        version = async_get_loaded_integration(coordinator.hass, DOMAIN).version if redraw else None
        async with coordinator.export_lock:
            refreshed, redrawn = await async_refresh(
                coordinator.hass,
                coordinator.settings,
                info,
                data,
                figures,
                markers,
                redraw=redraw,
                version=str(version) if version else None,
            )
        coordinator.replace_export(refreshed)
        return refreshed, redrawn

    def _figures(self, info: ExportInfo, log: TripLog | None) -> LogbookFigures | None:
        """Return the logbook figures of an automatic trip export, up to the next trip."""
        coordinator = self.coordinator
        trip_start = info.start
        automatic = sorted((i for i in coordinator.exports if i.automatic), key=lambda i: i.start)
        later = [i for i in automatic if i.start > trip_start]
        running = coordinator.log.start if coordinator.log is not None else None
        until = later[0].start if later else running if running is not None and running > trip_start else None
        end_counters = log.counters_at(info.end) if log is not None else None
        if end_counters is None and later and later[0].counter_start is not None:
            end_counters = later[0].counter_start
        figures = coordinator.logbook.trip_figures(
            trip_start,
            end_counter_m=end_counters.distance_m if end_counters else None,
            until=until - timedelta(microseconds=1) if until else None,
        )
        if figures is not None and end_counters is None:
            # Without the counter at the trip's end, the odometer at export time is the best there is.
            stored = info.logbook.odometer_end_km if info.logbook else None
            figures = replace(figures, odometer_end_km=stored)
        return figures
