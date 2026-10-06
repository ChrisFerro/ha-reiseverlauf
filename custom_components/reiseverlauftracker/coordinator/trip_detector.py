"""
Trip detection state machine driven by the D+ signal and vehicle positions.

The detector has no Home Assistant dependencies. The coordinator feeds it D+
changes, positions and clock ticks, persists `as_dict()` in a `Store`, and acts
on the returned events. Every input first processes deadlines that passed
before its timestamp, so a late timer never reorders events.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from custom_components.reiseverlauftracker.utils.geo import Position, distance_m

STATE_VERSION = 1


class TripPhase(StrEnum):
    """Lifecycle phase of the detector."""

    IDLE = "idle"
    ACTIVE = "active"
    ENDED = "ended"
    """The trip has ended but may still be resumed within the merge window."""


@dataclass(frozen=True, slots=True)
class DetectorSettings:
    """Tunable thresholds of the detector."""

    end_delay: timedelta = timedelta(minutes=60)
    merge_window: timedelta = timedelta(hours=6)
    min_movement_m: float = 100.0


@dataclass(frozen=True, slots=True)
class TripStarted:
    """D+ switched on while no trip was running."""

    start: datetime


@dataclass(frozen=True, slots=True)
class TripResumed:
    """An ended trip continues: D+ or movement resumed within the merge window."""

    start: datetime
    resumed_at: datetime


@dataclass(frozen=True, slots=True)
class TripEnded:
    """
    A trip ended and should be exported.

    `resumed` is true when the trip was ended before and merged afterwards;
    the new export then replaces the previous one.
    """

    start: datetime
    end: datetime
    max_distance_m: float
    resumed: bool


@dataclass(frozen=True, slots=True)
class TripDiscarded:
    """A trip ended without ever leaving the start radius; nothing to export."""

    start: datetime
    end: datetime
    max_distance_m: float


@dataclass(frozen=True, slots=True)
class TripClosed:
    """The merge window of an ended trip elapsed; the trip is final."""

    start: datetime
    end: datetime


type TripEvent = TripStarted | TripResumed | TripEnded | TripDiscarded | TripClosed


class TripDetector:
    """Detect trips from D+ and positions, including ferry and train sections."""

    def __init__(
        self,
        settings: DetectorSettings,
        stored: dict[str, Any] | None = None,
    ) -> None:
        """Create a detector, optionally from a dict returned by `as_dict()`."""
        self.settings = settings
        self._phase = TripPhase.IDLE
        self._dplus_on = False
        self._last_position: Position | None = None
        self._start: datetime | None = None
        self._start_position: Position | None = None
        self._max_distance_m = 0.0
        self._resumed = False
        self._dplus_off_at: datetime | None = None
        self._last_motion_at: datetime | None = None
        self._motion_anchor: Position | None = None
        self._end: datetime | None = None
        if stored is not None:
            self._load(stored)

    @property
    def phase(self) -> TripPhase:
        """Return the current phase."""
        return self._phase

    @property
    def start(self) -> datetime | None:
        """Return the start of the current or last ended trip."""
        return self._start

    @property
    def end(self) -> datetime | None:
        """Return the end of the trip while it is in the merge window."""
        return self._end

    @property
    def max_distance_m(self) -> float:
        """Return the largest distance from the start position seen so far."""
        return self._max_distance_m

    def next_deadline(self) -> datetime | None:
        """Return when `tick()` must be called next, or None if nothing is pending."""
        if self._phase is TripPhase.ACTIVE and not self._dplus_on:
            return self._end_candidate() + self.settings.end_delay
        if self._phase is TripPhase.ENDED and self._end is not None:
            return self._end + self.settings.merge_window
        return None

    def tick(self, now: datetime) -> list[TripEvent]:
        """Process all deadlines up to `now`."""
        return self._advance(now)

    def update_dplus(self, on: bool, at: datetime) -> list[TripEvent]:
        """Feed a D+ state change that happened at `at`."""
        events = self._advance(at)
        if on == self._dplus_on:
            return events
        self._dplus_on = on
        if on:
            if self._phase is TripPhase.IDLE:
                self._begin(at)
                events.append(TripStarted(start=at))
            elif self._phase is TripPhase.ENDED:
                events.append(self._resume(at))
            self._dplus_off_at = None
            self._last_motion_at = None
            self._motion_anchor = None
        elif self._phase is TripPhase.ACTIVE:
            self._dplus_off_at = at
            self._last_motion_at = None
            self._motion_anchor = self._last_position
        return events

    def update_position(self, position: Position, at: datetime) -> list[TripEvent]:
        """Feed a vehicle position observed at `at`."""
        events = self._advance(at)
        self._last_position = position
        if self._phase is not TripPhase.IDLE and not self._dplus_on:
            if self._motion_anchor is None:
                self._motion_anchor = position
            elif distance_m(self._motion_anchor, position) > self.settings.min_movement_m:
                self._motion_anchor = position
                self._last_motion_at = at
                if self._phase is TripPhase.ENDED:
                    events.append(self._resume(at))
        if self._phase is TripPhase.ACTIVE:
            if self._start_position is None:
                self._start_position = position
            self._max_distance_m = max(self._max_distance_m, distance_m(self._start_position, position))
        return events

    def restore(
        self,
        dplus_on: bool,
        dplus_changed_at: datetime,
        now: datetime,
    ) -> list[TripEvent]:
        """
        Reconcile the stored state with the D+ state found after a restart.

        A D+ change missed while Home Assistant was down is replayed at its
        `last_changed` time, so a countdown that expired in between ends the
        trip at the right moment. Without stored state and D+ on, the trip
        starts at `dplus_changed_at`.
        """
        events: list[TripEvent] = []
        if dplus_on != self._dplus_on:
            events += self.update_dplus(dplus_on, dplus_changed_at)
        events += self._advance(now)
        return events

    def as_dict(self) -> dict[str, Any]:
        """Return the state as a JSON-serialisable dict."""
        return {
            "version": STATE_VERSION,
            "phase": self._phase.value,
            "dplus_on": self._dplus_on,
            "last_position": _pos_out(self._last_position),
            "start": _dt_out(self._start),
            "start_position": _pos_out(self._start_position),
            "max_distance_m": self._max_distance_m,
            "resumed": self._resumed,
            "dplus_off_at": _dt_out(self._dplus_off_at),
            "last_motion_at": _dt_out(self._last_motion_at),
            "motion_anchor": _pos_out(self._motion_anchor),
            "end": _dt_out(self._end),
        }

    def _load(self, data: dict[str, Any]) -> None:
        self._phase = TripPhase(data["phase"])
        self._dplus_on = data["dplus_on"]
        self._last_position = _pos_in(data["last_position"])
        self._start = _dt_in(data["start"])
        self._start_position = _pos_in(data["start_position"])
        self._max_distance_m = data["max_distance_m"]
        self._resumed = data["resumed"]
        self._dplus_off_at = _dt_in(data["dplus_off_at"])
        self._last_motion_at = _dt_in(data["last_motion_at"])
        self._motion_anchor = _pos_in(data["motion_anchor"])
        self._end = _dt_in(data["end"])

    def _end_candidate(self) -> datetime:
        if self._dplus_off_at is None:
            msg = "No end candidate while D+ is on"
            raise RuntimeError(msg)
        if self._last_motion_at is not None and self._last_motion_at > self._dplus_off_at:
            return self._last_motion_at
        return self._dplus_off_at

    def _advance(self, now: datetime) -> list[TripEvent]:
        events: list[TripEvent] = []
        if self._phase is TripPhase.ACTIVE and not self._dplus_on:
            end = self._end_candidate()
            if now >= end + self.settings.end_delay:
                events.append(self._finish(end))
        if (
            self._phase is TripPhase.ENDED
            and self._start is not None
            and self._end is not None
            and now >= self._end + self.settings.merge_window
        ):
            events.append(TripClosed(start=self._start, end=self._end))
            self._reset()
        return events

    def _begin(self, at: datetime) -> None:
        self._phase = TripPhase.ACTIVE
        self._start = at
        self._start_position = self._last_position
        self._max_distance_m = 0.0
        self._resumed = False
        self._end = None

    def _resume(self, at: datetime) -> TripResumed:
        if self._start is None:
            msg = "Cannot resume a trip without a start"
            raise RuntimeError(msg)
        self._phase = TripPhase.ACTIVE
        self._resumed = True
        self._end = None
        return TripResumed(start=self._start, resumed_at=at)

    def _finish(self, end: datetime) -> TripEnded | TripDiscarded:
        if self._start is None:
            msg = "Cannot finish a trip without a start"
            raise RuntimeError(msg)
        start = self._start
        if self._max_distance_m <= self.settings.min_movement_m:
            discarded = TripDiscarded(start=start, end=end, max_distance_m=self._max_distance_m)
            self._reset()
            return discarded
        self._phase = TripPhase.ENDED
        self._end = end
        return TripEnded(
            start=start,
            end=end,
            max_distance_m=self._max_distance_m,
            resumed=self._resumed,
        )

    def _reset(self) -> None:
        self._phase = TripPhase.IDLE
        self._start = None
        self._start_position = None
        self._max_distance_m = 0.0
        self._resumed = False
        self._dplus_off_at = None
        self._last_motion_at = None
        self._motion_anchor = None
        self._end = None


def _dt_out(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _dt_in(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _pos_out(value: Position | None) -> list[float] | None:
    return [value.lat, value.lon] if value is not None else None


def _pos_in(value: list[float] | None) -> Position | None:
    return Position(value[0], value[1]) if value is not None else None
