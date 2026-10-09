"""Coordinator that feeds sensor changes into trip detection and records the trip."""

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING, Any

from custom_components.reiseverlauftracker.const import DOMAIN, EVENT_TRIP_ENDED, EVENT_TRIP_STARTED, LOGGER
from custom_components.reiseverlauftracker.export import NoMovementError, NotEnoughPointsError
from custom_components.reiseverlauftracker.utils.geo import Position
from homeassistant.const import ATTR_GPS_ACCURACY, ATTR_LATITUDE, ATTR_LONGITUDE, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_point_in_utc_time, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.loader import async_get_loaded_integration
from homeassistant.util import dt as dt_util

from .export_runner import async_export, event_data, media_base
from .exports import ExportInfo, list_exports
from .models import TripSnapshot, TripStatus
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
        self._export_lock = asyncio.Lock()
        self._exporting = False
        self._export_failed = False
        self.last_export: ExportInfo | None = None

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

        exports = await self.hass.async_add_executor_job(list_exports, media_base(self.hass, self.settings))
        self.last_export = exports[0] if exports else None

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
        self._publish()

    async def async_stop(self) -> None:
        """Unsubscribe and write pending state immediately."""
        if self._unsub_states is not None:
            self._unsub_states()
            self._unsub_states = None
        if self._unsub_deadline is not None:
            self._unsub_deadline()
            self._unsub_deadline = None
        await self._detector_store.async_save(self.detector.as_dict())
        if self.log is not None:
            await self._log_store.async_save(self.log.as_dict())

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
            self._handle(self.detector.update_dplus(self.settings.is_dplus_on(state.state), state.last_changed))
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
                    self._fire_started(start, resumed=False)
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
        self._exporting = True
        self.config_entry.async_create_task(
            self.hass, self._async_export_ended(trip_event, data, self.log.as_dict()), "reiseverlauftracker export"
        )

    async def _async_export_ended(self, trip_event: TripEnded, data: Any, raw: dict[str, Any]) -> None:
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

    def _fire_started(self, start: datetime, *, resumed: bool) -> None:
        self.hass.bus.async_fire(
            EVENT_TRIP_STARTED,
            {"entry_id": self.config_entry.entry_id, "start": start.isoformat(), "resumed": resumed},
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
        phase = self.detector.phase
        deadline = self.detector.next_deadline()
        if phase is TripPhase.IDLE:
            snapshot = TripSnapshot(status=TripStatus.READY, last_export=self.last_export)
        elif phase is TripPhase.ENDED:
            snapshot = TripSnapshot(status=TripStatus.MERGEABLE, merge_until=deadline, **self._running())
        elif deadline is None:
            snapshot = TripSnapshot(status=TripStatus.DRIVING, **self._running())
        else:
            snapshot = TripSnapshot(status=TripStatus.PAUSED, expected_end=deadline, **self._running())
        if self._exporting:
            return replace(snapshot, status=TripStatus.PROCESSING)
        if self._export_failed and phase is not TripPhase.ACTIVE:
            return replace(snapshot, status=TripStatus.ERROR)
        return snapshot

    def _running(self) -> dict[str, Any]:
        log = self.log
        return {
            "trip_start": self.detector.start,
            "distance_km": log.distance_km if log else None,
            "driving_time": log.driving_time if log else None,
            "last_export": self.last_export,
        }

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
