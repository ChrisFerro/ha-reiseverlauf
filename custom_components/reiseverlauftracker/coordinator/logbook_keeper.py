"""
Keeps the logbook of one config entry: storage, measured distance and occasions.

An occasion (trip start, stop) pre-fills a pending entry and fires the event
`reiseverlauftracker_fahrtenbuch`, on which the blueprint sends a push message
with a link to the form.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from custom_components.reiseverlauftracker.const import DOMAIN, EVENT_LOGBOOK, LOGGER
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .logbook import Logbook, Occasion, Suggestion

STORAGE_VERSION = 1
SAVE_DELAY_S = 30


@dataclass(frozen=True, slots=True)
class PendingEntry:
    """An occasion waiting for the user to fill in the form."""

    occasion: Occasion
    time: datetime
    suggestion: Suggestion
    trip_start: datetime | None = None
    stop_start: datetime | None = None
    lat: float | None = None
    lon: float | None = None
    place: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the pending entry as a JSON-serialisable dict."""
        return {
            "occasion": self.occasion.value,
            "time": self.time.isoformat(),
            "suggestion": asdict(self.suggestion),
            "trip_start": self.trip_start.isoformat() if self.trip_start else None,
            "stop_start": self.stop_start.isoformat() if self.stop_start else None,
            "lat": self.lat,
            "lon": self.lon,
            "place": self.place,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PendingEntry:
        """Rebuild a pending entry from `as_dict()` output."""
        return cls(
            occasion=Occasion(data["occasion"]),
            time=datetime.fromisoformat(data["time"]),
            suggestion=Suggestion(**data["suggestion"]),
            trip_start=datetime.fromisoformat(data["trip_start"]) if data.get("trip_start") else None,
            stop_start=datetime.fromisoformat(data["stop_start"]) if data.get("stop_start") else None,
            lat=data.get("lat"),
            lon=data.get("lon"),
            place=data.get("place"),
        )


class LogbookKeeper:
    """Logbook, pending entry and their storage for one config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str, tank_litres: float) -> None:
        """Create an empty keeper; `async_load()` restores the stored logbook."""
        self.hass = hass
        self.entry_id = entry_id
        self.logbook = Logbook(tank_litres=tank_litres)
        self.pending: PendingEntry | None = None
        self.announced_stop: datetime | None = None
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.logbook")

    async def async_load(self) -> None:
        """Restore logbook and pending entry; an unreadable store starts empty."""
        if (stored := await self._store.async_load()) is None:
            return
        try:
            self.logbook = Logbook.from_dict(stored, self.logbook.tank_litres)
            self.pending = PendingEntry.from_dict(stored["pending"]) if stored.get("pending") else None
            announced = stored.get("announced_stop")
            self.announced_stop = datetime.fromisoformat(announced) if announced else None
        except KeyError, ValueError, TypeError:
            LOGGER.warning("Stored logbook is unreadable, starting with an empty one")

    async def async_save_now(self) -> None:
        """Write the logbook immediately, for example on unload."""
        await self._store.async_save(self._data())

    def save(self) -> None:
        """Write the logbook after a short delay, batching frequent changes."""
        self._store.async_delay_save(self._data, SAVE_DELAY_S)

    def _data(self) -> dict[str, Any]:
        return {
            **self.logbook.as_dict(),
            "pending": self.pending.as_dict() if self.pending else None,
            "announced_stop": self.announced_stop.isoformat() if self.announced_stop else None,
        }

    def set_running_trip_distance(self, metres: float) -> None:
        """Track the distance of the running trip."""
        if metres != self.logbook.running_trip_m:
            self.logbook.set_running_trip_distance(metres)
            self.save()

    def close_trip(self) -> None:
        """Add the running trip's distance for good."""
        self.logbook.close_trip()
        self.save()

    def announce(
        self,
        occasion: Occasion,
        time: datetime,
        *,
        trip_start: datetime | None = None,
        stop_start: datetime | None = None,
        lat: float | None = None,
        lon: float | None = None,
        place: str | None = None,
    ) -> bool:
        """
        Pre-fill a pending entry for the occasion and fire the logbook event.

        A pending entry replaces an unsaved one. A stop is announced only once,
        also when it continues after D+ was briefly on; stops are identified by
        their start time.

        Returns:
            Whether the occasion was announced.

        """
        if occasion is Occasion.STOP:
            if stop_start is not None and stop_start == self.announced_stop:
                return False
            self.announced_stop = stop_start
        self.pending = PendingEntry(
            occasion=occasion,
            time=time,
            suggestion=self.logbook.suggestion(),
            trip_start=trip_start,
            stop_start=stop_start,
            lat=lat,
            lon=lon,
            place=place,
        )
        self.save()
        self.hass.bus.async_fire(EVENT_LOGBOOK, self.event_data(self.pending))
        return True

    def event_data(self, pending: PendingEntry) -> dict[str, Any]:
        """Return the payload of the logbook event."""
        suggestion = pending.suggestion
        return {
            "entry_id": self.entry_id,
            "anlass": pending.occasion.value,
            "zeit": pending.time.isoformat(),
            "ort": pending.place,
            "reise_start": pending.trip_start.isoformat() if pending.trip_start else None,
            "halt_start": pending.stop_start.isoformat() if pending.stop_start else None,
            "vorschlag": {
                "kilometerstand": suggestion.odometer_km,
                "kraftstoff": suggestion.fuel_percent,
                "gas_1": suggestion.gas1_percent,
                "gas_2": suggestion.gas2_percent,
            },
        }
