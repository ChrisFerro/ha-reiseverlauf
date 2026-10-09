"""Build the snapshot the entities read from the detector and the trip log."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from .exports import ExportInfo
from .models import TripSnapshot, TripStatus
from .trip_detector import TripDetector, TripPhase
from .trip_log import TripLog


@dataclass(frozen=True, slots=True)
class ExportState:
    """What the coordinator knows about exports when it builds a snapshot."""

    last_export: ExportInfo | None
    exports: tuple[ExportInfo, ...]
    exporting: bool
    failed: bool


def build_snapshot(
    detector: TripDetector, log: TripLog | None, exports: ExportState, now: datetime, min_stop: timedelta
) -> TripSnapshot:
    """Return the status and the running values of the trip at `now`."""
    phase = detector.phase
    deadline = detector.next_deadline()
    if phase is TripPhase.IDLE:
        snapshot = TripSnapshot(status=TripStatus.READY)
    elif phase is TripPhase.ENDED:
        snapshot = TripSnapshot(status=TripStatus.MERGEABLE, merge_until=deadline, **_running(detector, log, now))
    elif deadline is None:
        snapshot = TripSnapshot(status=TripStatus.DRIVING, **_running(detector, log, now))
    else:
        snapshot = TripSnapshot(status=TripStatus.PAUSED, expected_end=deadline, **_running(detector, log, now))
    if log is not None and phase is not TripPhase.IDLE:
        snapshot = replace(snapshot, stops=tuple(log.confirmed_stops(now, min_stop)))
    snapshot = replace(
        snapshot, active=phase is TripPhase.ACTIVE, exports=exports.exports, last_export=exports.last_export
    )
    if exports.exporting:
        return replace(snapshot, status=TripStatus.PROCESSING)
    if exports.failed and phase is not TripPhase.ACTIVE:
        return replace(snapshot, status=TripStatus.ERROR)
    return snapshot


def _running(detector: TripDetector, log: TripLog | None, now: datetime) -> dict[str, Any]:
    start = detector.start
    if log is None or start is None:
        return {"trip_start": start}
    elapsed = (detector.end or now) - start
    return {
        "trip_start": start,
        "start_place": log.start_place,
        "distance_km": log.distance_km,
        "driving_time": log.driving_time,
        "pause_time": max(elapsed - log.driving_time, timedelta()),
        "average_kmh": log.average_moving_kmh,
    }
