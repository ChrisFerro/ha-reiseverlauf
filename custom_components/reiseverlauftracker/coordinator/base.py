"""Coordinator that feeds sensor changes into trip detection and records the trip."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from custom_components.reiseverlauftracker.const import (
    DOMAIN,
    EVENT_TRIP_ENDED,
    EVENT_TRIP_EXPORTED,
    EVENT_TRIP_STARTED,
    EXPORT_CHOICE_ALL,
    LOGGER,
)
from custom_components.reiseverlauftracker.export import (
    ExportFile,
    NoMovementError,
    NotEnoughPointsError,
    StepSeries,
    Stop,
    TrackPoint,
)
from custom_components.reiseverlauftracker.utils.geo import Position
from homeassistant.const import ATTR_GPS_ACCURACY, ATTR_LATITUDE, ATTR_LONGITUDE, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_utc_time,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.loader import async_get_loaded_integration
from homeassistant.util import dt as dt_util

from .export_runner import async_export, event_data, media_base
from .exports import ExportInfo, list_exports, remove_files
from .models import TripSnapshot
from .places import async_place_name
from .snapshot import ExportState, build_snapshot
from .trip_detector import (
    DetectorSettings,
    TripClosed,
    TripDetector,
    TripDiscarded,
    TripEnded,
    TripEvent,
    TripPhase,
    TripResumed,
    TripStarted,
)
from .trip_log import RunningStatsSettings, TripLog

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.data import ReiseverlaufConfigEntry
    from custom_components.reiseverlauftracker.settings import ReiseverlaufSettings

STORAGE_VERSION = 1
DETECTOR_SAVE_DELAY_S = 10
LOG_SAVE_DELAY_S = 60
INVALID_STATES = {STATE_UNAVAILABLE, STATE_UNKNOWN}
REFRESH_INTERVAL = timedelta(minutes=1)


class ReiseverlaufDataUpdateCoordinator(DataUpdateCoordinator[TripSnapshot]):
    """Push-driven: state changes and deadlines update the snapshot, nothing is polled."""

    config_entry: ReiseverlaufConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ReiseverlaufConfigEntry, settings: ReiseverlaufSettings) -> None:
        """Create the coordinator; `async_start()` loads the stored state and subscribes."""
        super().__init__(hass, LOGGER, config_entry=entry, name=DOMAIN, update_interval=None)
        self.settings = settings
        self.detector = TripDetector(_detector_settings(settings))
        self.log: TripLog | None = None
        self._detector_store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.detector"
        )
        self._log_store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.trip_log")
        self._unsub_deadline: Callable[[], None] | None = None
        self._unsub_states: Callable[[], None] | None = None
        self._unsub_refresh: Callable[[], None] | None = None
        self._unsub_stop_check: Callable[[], None] | None = None
        self._export_lock = asyncio.Lock()
        self._exporting = False
        self._export_failed = False
        self.last_export: ExportInfo | None = None
        self.exports: tuple[ExportInfo, ...] = ()
        self.export_choice: str | None = None

    async def async_start(self) -> None:
        """Restore detector and trip log, reconcile with the current D+ state and subscribe."""
        if (stored := await self._detector_store.async_load()) is not None:
            try:
                self.detector = TripDetector(self.detector.settings, stored)
            except KeyError, ValueError:
                LOGGER.warning("Stored trip detection state is unreadable, starting fresh")
        if self.detector.phase is not TripPhase.IDLE and (stored_log := await self._log_store.async_load()):
            try:
                self.log = TripLog.from_dict(stored_log, self._log_settings())
            except KeyError, ValueError, TypeError:
                LOGGER.warning("Stored trip points are unreadable, recording continues without them")

        await self._async_load_exports()
        self.last_export = next((info for info in self.exports if info.automatic), None)

        now = dt_util.utcnow()
        dplus = self.hass.states.get(self.settings.dplus_entity)
        if dplus is not None and dplus.state not in INVALID_STATES:
            events = self.detector.restore(self.settings.is_dplus_on(dplus.state), dplus.last_changed, now)
        else:
            events = self.detector.tick(now)
        self._handle(events)
        if (tracker := self.hass.states.get(self.settings.tracker_entity)) is not None:
            self._on_position(tracker, record=False)

        entities = [self.settings.dplus_entity, self.settings.tracker_entity, self.settings.speed_entity]
        if self.settings.altitude_entity:
            entities.append(self.settings.altitude_entity)
        self._unsub_states = async_track_state_change_event(self.hass, entities, self._on_state_change)
        self._unsub_refresh = async_track_time_interval(self.hass, self._on_refresh, REFRESH_INTERVAL)
        self._schedule_stop_check()
        self._publish()

    async def async_stop(self) -> None:
        """Unsubscribe and write pending state immediately."""
        for unsub in (self._unsub_states, self._unsub_deadline, self._unsub_refresh, self._unsub_stop_check):
            if unsub is not None:
                unsub()
        self._unsub_states = self._unsub_deadline = self._unsub_refresh = self._unsub_stop_check = None
        await self._detector_store.async_save(self.detector.as_dict())
        if self.log is not None:
            await self._log_store.async_save(self.log.as_dict())

    async def async_refresh_exports(self) -> None:
        """Re-read the export folders, for example after files were deleted."""
        await self._async_load_exports()
        if self.last_export is not None:
            self.last_export = next((i for i in self.exports if i.folder == self.last_export.folder), None)
        self._publish()

    async def async_export_period(
        self,
        data: tuple[list[TrackPoint], StepSeries | None, StepSeries | None],
        start: datetime,
        end: datetime,
        settings: ReiseverlaufSettings,
        title: str | None,
    ) -> dict[str, Any]:
        """
        Export any period on request, announce it and return the event payload.

        The folder name holds start and end, so a manual export never replaces an automatic one.

        Raises:
            NotEnoughPointsError: Fewer than two usable positions.
            NoMovementError: The vehicle never left the minimum movement radius.

        """
        tz = dt_util.get_default_time_zone()
        local_start, local_end = start.astimezone(tz), end.astimezone(tz)
        end_format = "%H%M" if local_start.date() == local_end.date() else "%Y-%m-%d_%H%M"
        folder = f"{local_start:%Y-%m-%d_%H%M}-{local_end.strftime(end_format)}"
        async with self._export_lock:
            info = await async_export(
                self.hass,
                settings,
                data,
                start,
                end,
                version=async_get_loaded_integration(self.hass, DOMAIN).version,
                raw=TripLog.from_export_inputs(start, data, self._log_settings()).as_dict(),
                title=title,
                automatic=False,
                folder=folder,
            )
        await self._async_load_exports()
        self._publish()
        payload = event_data(self.settings, info, media_base(self.hass, self.settings))
        self.hass.bus.async_fire(EVENT_TRIP_EXPORTED, {"entry_id": self.config_entry.entry_id, **payload})
        return payload

    def export_choice_options(self) -> list[str]:
        """Return the labels of all exports, newest first, and the "all" choice at the end."""
        tz = dt_util.get_default_time_zone()
        return [*(info.label(tz) for info in self.exports), EXPORT_CHOICE_ALL]

    def current_export_choice(self) -> str | None:
        """
        Return the chosen export, or the newest one if the choice is gone.

        It never falls back to "all" on its own, so a dashboard button cannot delete everything by accident.
        """
        options = self.export_choice_options()
        if self.export_choice in options:
            return self.export_choice
        return options[0] if len(options) > 1 else None

    def find_exports(self, choice: str) -> list[ExportInfo]:
        """Return the exports a selection label, a folder name or "all" refers to."""
        if choice == EXPORT_CHOICE_ALL:
            return list(self.exports)
        tz = dt_util.get_default_time_zone()
        return [info for info in self.exports if choice in {info.folder, info.label(tz)}]

    async def async_remove_files(self, exports: list[ExportInfo], kinds: set[ExportFile]) -> None:
        """Delete the given file kinds of the given exports and refresh the list."""
        base = media_base(self.hass, self.settings)
        for info in exports:
            await self.hass.async_add_executor_job(remove_files, base, info.folder, kinds)
        await self.async_refresh_exports()

    async def _async_load_exports(self) -> None:
        exports = await self.hass.async_add_executor_job(list_exports, media_base(self.hass, self.settings))
        self.exports = tuple(exports)

    @callback
    def async_start_trip(self) -> None:
        """Start a trip, or resume the ended one, without D+."""
        self._handle(self.detector.start_manually(dt_util.utcnow()))
        self._publish()

    @callback
    def async_end_trip(self) -> None:
        """End the running trip now."""
        self._handle(self.detector.end_manually(dt_util.utcnow()))
        self._publish()

    async def _async_update_data(self) -> TripSnapshot:
        """Return the current snapshot; only used by a manual refresh."""
        return self._snapshot()

    @callback
    def _on_state_change(self, event: Event[EventStateChangedData]) -> None:
        state = event.data["new_state"]
        if state is None or state.state in INVALID_STATES:
            return
        entity_id = event.data["entity_id"]
        if entity_id == self.settings.dplus_entity:
            dplus_on = self.settings.is_dplus_on(state.state)
            self._handle(self.detector.update_dplus(dplus_on, state.last_changed))
            self._on_dplus_for_stops(dplus_on, state.last_changed)
        elif entity_id == self.settings.tracker_entity:
            self._on_position(state)
        elif (value := _float(state.state)) is not None and self.log is not None:
            if entity_id == self.settings.speed_entity:
                self.log.add_speed(state.last_updated, value)
            else:
                self.log.add_altitude(state.last_updated, value)
            self._save_log()
            return
        else:
            return
        self._publish()

    def _on_position(self, state: State, *, record: bool = True) -> None:
        lat, lon = _float(state.attributes.get(ATTR_LATITUDE)), _float(state.attributes.get(ATTR_LONGITUDE))
        if lat is None or lon is None:
            return
        accuracy = _float(state.attributes.get(ATTR_GPS_ACCURACY))
        at = state.last_updated
        if accuracy is None or accuracy <= self.settings.max_accuracy_m:
            self._handle(self.detector.update_position(Position(lat, lon), at))
        if record and self.log is not None:
            self.log.add_position(at, lat, lon, accuracy)
            self._save_log()

    def _on_dplus_for_stops(self, dplus_on: bool, at: datetime) -> None:
        if self.log is None:
            return
        if not dplus_on:
            self.log.begin_stop(at)
            self._schedule_stop_check()
        elif (stop := self.log.end_stop(at, self.settings.min_stop_duration)) is not None and stop.place is None:
            self._lookup_stop_place(stop.start, stop.lat, stop.lon)
        self._save_log()

    def _schedule_stop_check(self) -> None:
        if self._unsub_stop_check is not None:
            self._unsub_stop_check()
            self._unsub_stop_check = None
        stop = self.log.open_stop if self.log is not None else None
        if stop is None or stop.place is not None:
            return
        remaining = stop.start + self.settings.min_stop_duration - dt_util.utcnow()
        self._unsub_stop_check = async_call_later(self.hass, max(remaining.total_seconds(), 0), self._on_stop_check)

    @callback
    def _on_stop_check(self, _now: datetime) -> None:
        self._unsub_stop_check = None
        stop = self.log.open_stop if self.log is not None else None
        if stop is not None and stop.place is None:
            self._lookup_stop_place(stop.start, stop.lat, stop.lon)
        self._publish()

    def _lookup_stop_place(self, start: datetime, lat: float | None, lon: float | None) -> None:
        async def lookup() -> None:
            place = await async_place_name(self.hass, self.settings, lat, lon)
            if self.log is not None and place is not None:
                self.log.set_stop_place(start, place)
                self._save_log()
                self._publish()

        self.config_entry.async_create_task(self.hass, lookup(), "reiseverlauftracker stop place")

    @callback
    def _on_refresh(self, _now: datetime) -> None:
        if self.detector.phase is TripPhase.ACTIVE:
            self._publish()

    @callback
    def _on_deadline(self, now: datetime) -> None:
        self._unsub_deadline = None
        self._handle(self.detector.tick(now))
        self._publish()

    def _handle(self, events: list[TripEvent]) -> None:
        for trip_event in events:
            LOGGER.debug("Trip event: %s", trip_event)
            match trip_event:
                case TripStarted(start=start):
                    self._export_failed = False
                    self._begin_log(start)
                    self.config_entry.async_create_task(
                        self.hass, self._async_announce_start(start), "reiseverlauftracker start place"
                    )
                case TripResumed(start=start):
                    self._export_failed = False
                    if self.log is None:
                        self._begin_log(start)
                    self._fire_started(start, resumed=True)
                case TripEnded():
                    self._on_trip_ended(trip_event)
                case TripDiscarded() | TripClosed():
                    self._drop_log()
        self._detector_store.async_delay_save(self.detector.as_dict, DETECTOR_SAVE_DELAY_S)
        self._schedule_deadline()

    def _on_trip_ended(self, trip_event: TripEnded) -> None:
        LOGGER.info("Trip from %s to %s ended", trip_event.start, trip_event.end)
        if self.log is None:
            LOGGER.warning("No points were recorded for the trip that started at %s", trip_event.start)
            self._export_failed = True
            return
        positions, speed, altitude = self.log.export_inputs()
        data = ([p for p in positions if p.time <= trip_event.end], speed, altitude)
        stops = self.log.export_stops(trip_event.end)
        self._exporting = True
        self.config_entry.async_create_task(
            self.hass,
            self._async_export_ended(trip_event, data, self.log.as_dict(), stops),
            "reiseverlauftracker export",
        )

    async def _async_export_ended(
        self, trip_event: TripEnded, data: Any, raw: dict[str, Any], stops: tuple[Stop, ...]
    ) -> None:
        async with self._export_lock:
            try:
                info = await async_export(
                    self.hass,
                    self.settings,
                    data,
                    trip_event.start,
                    trip_event.end,
                    version=async_get_loaded_integration(self.hass, DOMAIN).version,
                    raw=raw,
                    stops=stops,
                )
            except NotEnoughPointsError, NoMovementError:
                LOGGER.warning("Trip from %s has no usable movement to export", trip_event.start)
                self._export_failed = True
            except Exception:  # noqa: BLE001 - A failed export must not leave the status stuck.
                LOGGER.exception("Export of the trip from %s failed", trip_event.start)
                self._export_failed = True
            else:
                self.last_export = info
                self._export_failed = False
                await self._async_load_exports()
                payload = event_data(self.settings, info, media_base(self.hass, self.settings))
                self.hass.bus.async_fire(
                    EVENT_TRIP_ENDED,
                    {"entry_id": self.config_entry.entry_id, "fortgesetzt": trip_event.resumed, **payload},
                )
            finally:
                self._exporting = False
                self._publish()

    def _begin_log(self, start: datetime) -> None:
        self.log = TripLog(start, self._log_settings())
        if (tracker := self.hass.states.get(self.settings.tracker_entity)) is not None:
            lat, lon = _float(tracker.attributes.get(ATTR_LATITUDE)), _float(tracker.attributes.get(ATTR_LONGITUDE))
            if lat is not None and lon is not None:
                accuracy = _float(tracker.attributes.get(ATTR_GPS_ACCURACY))
                self.log.add_position(min(start, tracker.last_updated), lat, lon, accuracy)
        for entity_id, add in (
            (self.settings.speed_entity, self.log.add_speed),
            (self.settings.altitude_entity, self.log.add_altitude),
        ):
            if entity_id and (sensor := self.hass.states.get(entity_id)) is not None:
                if (value := _float(sensor.state)) is not None:
                    add(min(start, sensor.last_updated), value)
        self._save_log()

    def _drop_log(self) -> None:
        self.log = None
        self.config_entry.async_create_task(self.hass, self._log_store.async_remove())

    def _save_log(self) -> None:
        if self.log is not None:
            self._log_store.async_delay_save(self.log.as_dict, LOG_SAVE_DELAY_S)

    async def _async_announce_start(self, start: datetime) -> None:
        log = self.log
        first = log.positions[0] if log and log.positions else None
        place = await async_place_name(
            self.hass, self.settings, first.lat if first else None, first.lon if first else None
        )
        if log is not None and log is self.log:
            log.start_place = place
            self._save_log()
            self._publish()
        self._fire_started(start, resumed=False)

    def _fire_started(self, start: datetime, *, resumed: bool) -> None:
        self.hass.bus.async_fire(
            EVENT_TRIP_STARTED,
            {
                "entry_id": self.config_entry.entry_id,
                "start": start.isoformat(),
                "resumed": resumed,
                "startort": self.log.start_place if self.log else None,
            },
        )

    def _schedule_deadline(self) -> None:
        if self._unsub_deadline is not None:
            self._unsub_deadline()
            self._unsub_deadline = None
        if (deadline := self.detector.next_deadline()) is not None:
            self._unsub_deadline = async_track_point_in_utc_time(self.hass, self._on_deadline, deadline)

    def _publish(self) -> None:
        self.async_set_updated_data(self._snapshot())

    def _snapshot(self) -> TripSnapshot:
        exports = ExportState(self.last_export, self.exports, self._exporting, self._export_failed)
        return build_snapshot(self.detector, self.log, exports, dt_util.utcnow(), self.settings.min_stop_duration)

    def _log_settings(self) -> RunningStatsSettings:
        return RunningStatsSettings(
            max_accuracy_m=self.settings.max_accuracy_m,
            standstill_kmh=self.settings.standstill_kmh,
        )


def _detector_settings(settings: ReiseverlaufSettings) -> DetectorSettings:
    return DetectorSettings(
        end_delay=settings.end_delay,
        merge_window=settings.merge_window,
        min_movement_m=settings.min_movement_m,
    )


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except TypeError, ValueError:
        return None
