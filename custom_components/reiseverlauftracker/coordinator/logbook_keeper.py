"""
Keeps the logbook of one config entry: storage, measured distance, form and CSV file.

An occasion (trip start, stop) pre-fills the form and fires the event
`reiseverlauftracker_fahrtenbuch`, on which the blueprint sends a push message
with a link to the form. Saving the form adds an entry for that occasion, or a
manual entry when there is none.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from custom_components.reiseverlauftracker.const import DOMAIN, EVENT_LOGBOOK, LOGGER
from custom_components.reiseverlauftracker.export import LogbookFigures
from custom_components.reiseverlauftracker.export.logbook_csv import logbook_csv
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .logbook import Draft, FormField, Logbook, LogbookEntry, Occasion, RecordedStop, Suggestion

STORAGE_VERSION = 1
SAVE_DELAY_S = 30
CSV_NAME = "fahrtenbuch.csv"


@dataclass(frozen=True, slots=True)
class PendingEntry:
    """An occasion waiting for the user to fill in the form."""

    occasion: Occasion
    time: datetime
    suggestion: Suggestion
    distance_counter_m: float = 0.0
    ascent_counter_m: float | None = None
    descent_counter_m: float | None = None
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
            "distance_counter_m": self.distance_counter_m,
            "ascent_counter_m": self.ascent_counter_m,
            "descent_counter_m": self.descent_counter_m,
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
            distance_counter_m=data.get("distance_counter_m", 0.0),
            ascent_counter_m=data.get("ascent_counter_m"),
            descent_counter_m=data.get("descent_counter_m"),
            trip_start=datetime.fromisoformat(data["trip_start"]) if data.get("trip_start") else None,
            stop_start=datetime.fromisoformat(data["stop_start"]) if data.get("stop_start") else None,
            lat=data.get("lat"),
            lon=data.get("lon"),
            place=data.get("place"),
        )


@dataclass(frozen=True, slots=True)
class EntryContext:
    """Where and during which trip a manual entry is made."""

    trip_start: datetime | None = None
    lat: float | None = None
    lon: float | None = None
    place: str | None = None


class LogbookKeeper:
    """Logbook, pending entry, form and their storage for one config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        tank_litres: float,
        csv_folder: Path,
        on_change: Callable[[], None] = lambda: None,
    ) -> None:
        """Create an empty keeper; `async_load()` restores the stored logbook."""
        self.hass = hass
        self.entry_id = entry_id
        self.csv_folder = csv_folder
        self.logbook = Logbook(tank_litres=tank_litres)
        self.pending: PendingEntry | None = None
        self.announced_stop: datetime | None = None
        self.draft = Draft()
        self._on_change = on_change
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.logbook")

    @property
    def csv_path(self) -> Path:
        """Return where the CSV file of the logbook is written."""
        return self.csv_folder / CSV_NAME

    async def async_load(self) -> None:
        """Restore logbook, pending entry and form; an unreadable store starts empty."""
        if (stored := await self._store.async_load()) is None:
            self.draft = Draft.from_suggestion(self.logbook.suggestion())
            return
        try:
            self.logbook = Logbook.from_dict(stored, self.logbook.tank_litres)
            self.pending = PendingEntry.from_dict(stored["pending"]) if stored.get("pending") else None
            announced = stored.get("announced_stop")
            self.announced_stop = datetime.fromisoformat(announced) if announced else None
            draft = stored.get("draft")
            self.draft = Draft.from_dict(draft) if draft else Draft.from_suggestion(self.logbook.suggestion())
        except KeyError, ValueError, TypeError:
            LOGGER.warning("Stored logbook is unreadable, starting with an empty one")
            self.logbook = Logbook(tank_litres=self.logbook.tank_litres)
            self.pending = None
            self.announced_stop = None
            self.draft = Draft()

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
            "draft": self.draft.as_dict(),
        }

    def set_running_trip(self, metres: float, ascent_m: float = 0.0, descent_m: float = 0.0) -> None:
        """Track distance, ascent and descent of the running trip."""
        book = self.logbook
        if (metres, ascent_m, descent_m) != (
            book.running_trip_m,
            book.running_trip_ascent_m,
            book.running_trip_descent_m,
        ):
            book.set_running_trip(metres, ascent_m, descent_m)
            self.save()

    def close_trip(self) -> None:
        """Add the running trip's distance for good."""
        self.logbook.close_trip()
        self.save()

    def record_stop(
        self,
        trip_start: datetime,
        start: datetime,
        end: datetime | None,
        *,
        lat: float | None = None,
        lon: float | None = None,
        place: str | None = None,
    ) -> RecordedStop:
        """
        Remember a stop of the running trip, with the counters now if it is new.

        Returns:
            The stored stop.

        """
        stored = self.logbook.record_stop(
            RecordedStop(
                trip_start=trip_start,
                start=start,
                end=end,
                distance_counter_m=self.logbook.distance_counter_m,
                ascent_counter_m=self.logbook.ascent_counter_m,
                descent_counter_m=self.logbook.descent_counter_m,
                lat=lat,
                lon=lon,
                place=place,
            )
        )
        self.save()
        return stored

    def set_stop_place(self, start: datetime, place: str) -> None:
        """Store the place name of a remembered stop."""
        self.logbook.set_stop_place(start, place)
        self.save()

    def prune_stops(self, now: datetime) -> None:
        """Forget stops older than the retention period."""
        if self.logbook.prune_stops(now):
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
        Pre-fill the form for the occasion and fire the logbook event.

        The occasion replaces an unsaved one, and its suggestion replaces the form.
        A stop is announced only once, also when it continues after D+ was
        briefly on; stops are identified by their start time.

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
            distance_counter_m=self.logbook.distance_counter_m,
            ascent_counter_m=self.logbook.ascent_counter_m,
            descent_counter_m=self.logbook.descent_counter_m,
            trip_start=trip_start,
            stop_start=stop_start,
            lat=lat,
            lon=lon,
            place=place,
        )
        self.draft = Draft.from_suggestion(self.pending.suggestion)
        self._changed()
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

    def trip_figures(self, trip_start: datetime) -> LogbookFigures | None:
        """Return the logbook figures for the export of a trip, or None while the logbook is empty."""
        if not self.logbook.entries:
            return None
        summary = self.logbook.trip_summary(trip_start)
        return LogbookFigures(
            odometer_start_km=summary.odometer_start_km,
            odometer_end_km=summary.odometer_end_km,
            fuel_litres=summary.fuel_litres,
            fuel_cost=summary.fuel_cost,
            gas_litres=summary.gas_litres,
            gas_cost=summary.gas_cost,
            consumption_l_100km=self.logbook.average_consumption(),
        )

    def set_field(self, form_field: FormField, value: float) -> None:
        """Change one value of the form."""
        self.draft = self.draft.with_value(form_field, value)
        self._changed()

    def discard(self) -> None:
        """Drop the pending occasion and reset the form to the current suggestion."""
        self.pending = None
        self.draft = Draft.from_suggestion(self.logbook.suggestion())
        self._changed()

    async def async_save_draft(self, context: EntryContext) -> LogbookEntry:
        """
        Add the form as an entry for the pending occasion, or as a manual entry.

        `context` describes a manual entry; a pending occasion brings its own.

        Returns:
            The new entry.

        """
        pending, draft = self.pending, self.draft
        entry = self.logbook.add(
            pending.time if pending else dt_util.utcnow(),
            pending.occasion if pending else Occasion.MANUAL,
            odometer_km=draft.odometer_km,
            fuel_percent=draft.fuel_percent,
            gas1_percent=draft.gas1_percent,
            gas2_percent=draft.gas2_percent,
            fuel=draft.fuel,
            gas=draft.gas,
            trip_start=pending.trip_start if pending else context.trip_start,
            stop_start=pending.stop_start if pending else None,
            lat=pending.lat if pending else context.lat,
            lon=pending.lon if pending else context.lon,
            place=pending.place if pending else context.place,
            distance_counter_m=pending.distance_counter_m if pending else None,
            ascent_counter_m=pending.ascent_counter_m if pending else None,
            descent_counter_m=pending.descent_counter_m if pending else None,
        )
        self.discard()
        await self._async_refresh_csv()
        return entry

    async def async_add(self, entry_kwargs: dict[str, Any], context: EntryContext) -> LogbookEntry:
        """
        Add a manual entry from a service action; the odometer defaults to the carried-forward value.

        Returns:
            The new entry.

        """
        values = {"odometer_km": self.logbook.suggest_odometer(), **entry_kwargs}
        entry = self.logbook.add(
            values.pop("time", None) or dt_util.utcnow(),
            Occasion.MANUAL,
            trip_start=context.trip_start,
            lat=context.lat,
            lon=context.lon,
            place=context.place,
            **values,
        )
        self._refresh_draft_without_pending()
        await self._async_refresh_csv()
        return entry

    async def async_update(self, entry_id: str, changes: dict[str, Any]) -> LogbookEntry:
        """
        Change an entry.

        Returns:
            The changed entry.

        Raises:
            KeyError: No entry has `entry_id`.

        """
        entry = self.logbook.update(entry_id, **changes)
        self._refresh_draft_without_pending()
        await self._async_refresh_csv()
        return entry

    async def async_remove(self, entry_id: str) -> None:
        """
        Delete an entry.

        Raises:
            KeyError: No entry has `entry_id`.

        """
        self.logbook.remove(entry_id)
        self._refresh_draft_without_pending()
        await self._async_refresh_csv()

    async def async_write_csv(self) -> Path:
        """
        Write the CSV file of the whole logbook into the output folder.

        Returns:
            The path of the file.

        """
        text = logbook_csv(list(self.logbook.entries), self.hass.config.language, dt_util.get_default_time_zone())
        path = self.csv_path
        await self.hass.async_add_executor_job(_write_text, path, text)
        return path

    async def _async_refresh_csv(self) -> None:
        """Rewrite the CSV file after a change; a failure must not lose the entry, which is already stored."""
        try:
            await self.async_write_csv()
        except OSError as err:
            LOGGER.warning("The logbook CSV file could not be written: %s", err)

    def _refresh_draft_without_pending(self) -> None:
        """Follow changed entries in the form, unless the user is filling it in for an occasion."""
        if self.pending is None:
            self.draft = Draft.from_suggestion(self.logbook.suggestion())
        self._changed()

    def _changed(self) -> None:
        self.save()
        self._on_change()


def entry_data(entry: LogbookEntry) -> dict[str, Any]:
    """Return an entry as attribute or response data, keyed in German like the other attributes."""
    return {
        "id": entry.id,
        "zeit": entry.time.isoformat(),
        "anlass": entry.occasion.value,
        "ort": entry.place,
        "kilometerstand": entry.odometer_km,
        "kraftstoff": entry.fuel_percent,
        "gas_1": entry.gas1_percent,
        "gas_2": entry.gas2_percent,
        "diesel_liter": entry.fuel.litres if entry.fuel else None,
        "diesel_betrag": entry.fuel.amount if entry.fuel else None,
        "gas_liter": entry.gas.litres if entry.gas else None,
        "gas_betrag": entry.gas.amount if entry.gas else None,
    }


def _write_text(path: Path, text: str) -> None:
    """Write `text` with a byte order mark, so that spreadsheet programs detect UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8-sig", newline="")
    tmp.replace(path)
