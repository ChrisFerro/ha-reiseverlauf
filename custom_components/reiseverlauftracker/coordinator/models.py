"""Data the coordinator hands to entities."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class TripStatus(StrEnum):
    """Values of the status sensor; the UI shows their translations."""

    READY = "bereit"
    DRIVING = "unterwegs"
    PAUSED = "pause"
    PROCESSING = "auswertung"
    MERGEABLE = "zusammenfuehrbar"
    ERROR = "fehler"


@dataclass(frozen=True, slots=True)
class TripSnapshot:
    """State of the current trip at one moment."""

    status: TripStatus
    trip_start: datetime | None = None
    expected_end: datetime | None = None
    merge_until: datetime | None = None
    distance_km: float | None = None
    driving_time: timedelta | None = None
