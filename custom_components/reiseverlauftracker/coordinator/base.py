"""Coordinator that feeds sensor changes into trip detection and records the trip."""

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from custom_components.reiseverlauftracker.const import DOMAIN, EVENT_TRIP_STARTED, LOGGER
from custom_components.reiseverlauftracker.utils.geo import Position
from homeassistant.const import ATTR_GPS_ACCURACY, ATTR_LATITUDE, ATTR_LONGITUDE, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_point_in_utc_time, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

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
                    self._begin_log(start)
                    self._fire_started(start, resumed=False)
                case TripResumed(start=start):
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
        if phase is TripPhase.IDLE:
            return TripSnapshot(status=TripStatus.READY)
        log = self.log
        running = {
            "trip_start": self.detector.start,
            "distance_km": log.distance_km if log else None,
            "driving_time": log.driving_time if log else None,
        }
        if phase is TripPhase.ENDED:
            return TripSnapshot(status=TripStatus.MERGEABLE, merge_until=self.detector.next_deadline(), **running)
        deadline = self.detector.next_deadline()
        if deadline is None:
            return TripSnapshot(status=TripStatus.DRIVING, **running)
        return TripSnapshot(status=TripStatus.PAUSED, expected_end=deadline, **running)

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
