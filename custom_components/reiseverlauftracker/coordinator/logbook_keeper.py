"""
Keeps the logbook of one config entry: storage, measured distance, form, travel costs and CSV files.

An occasion (trip start, stop) pre-fills the form and fires the event
`reiseverlauftracker_fahrtenbuch`, on which the blueprint sends a push message
with a link to the form. Saving the form adds an entry for that occasion, or a
manual entry when there is none.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from custom_components.reiseverlauftracker.const import DOMAIN, EVENT_LOGBOOK, LOGGER
from custom_components.reiseverlauftracker.export import LogbookFigures
from custom_components.reiseverlauftracker.export.logbook_csv import logbook_csv, travel_costs_csv
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .late_entry import LatePoint, entry_for
from .logbook import (
    FULL_PERCENT,
    CostCategory,
    Draft,
    FormField,
    Logbook,
    LogbookEntry,
    Occasion,
    RecordedStop,
    Refill,
    Suggestion,
    TravelCost,
)

STORAGE_VERSION = 1
SAVE_DELAY_S = 30
CSV_NAME = "fahrtenbuch.csv"
TRAVEL_CSV_NAME = "reisekosten.csv"


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
        trip_titles: Callable[[], dict[datetime, str]] = dict,
    ) -> None:
        """Create an empty keeper; `async_load()` restores the stored logbook."""
        self.hass = hass
        self.entry_id = entry_id
        self.csv_folder = csv_folder
        self.logbook = Logbook(tank_litres=tank_litres)
        self.pending: PendingEntry | None = None
        self.announced_stop: datetime | None = None
        self.draft = Draft()
        # A late entry for an earlier time fills the form; the form of the current occasion waits meanwhile.
        self.late: LatePoint | None = None
        self._current_draft: Draft | None = None
        self._on_change = on_change
        self._trip_titles = trip_titles
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.logbook")

    @property
    def csv_path(self) -> Path:
        """Return where the CSV file of the logbook is written."""
        return self.csv_folder / CSV_NAME

    @property
    def travel_csv_path(self) -> Path:
        """Return where the CSV file of the travel costs is written."""
        return self.csv_folder / TRAVEL_CSV_NAME

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
            "draft": (self._current_draft or self.draft).as_dict(),
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
        """Store the place name of a remembered stop; the time selection shows it right away."""
        self.logbook.set_stop_place(start, place)
        self._changed()

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
        self._set_current_draft(Draft.from_suggestion(self.pending.suggestion))
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
        """
        Drop the pending occasion and reset the form to the current suggestion.

        While a late entry is chosen, only that is dropped and the form of the
        current occasion returns.
        """
        if self.late is not None:
            self.select_late(None)
            return
        self.pending = None
        self.draft = Draft.from_suggestion(self.logbook.suggestion())
        self._changed()

    def select_late(self, point: LatePoint | None) -> None:
        """
        Fill the form for a late entry at `point`, or return to the current occasion with None.

        The form shows the entry already made for the point, or the suggestion for its time.
        """
        if point is None:
            if self.late is not None:
                self.late = None
                self.draft = self._current_draft or Draft.from_suggestion(self.logbook.suggestion())
                self._current_draft = None
                self._changed()
            return
        if self.late is None:
            self._current_draft = self.draft
        self.late = point
        self.draft = self.late_draft(point)
        self._changed()

    def late_draft(self, point: LatePoint) -> Draft:
        """Return the form for `point`: its existing entry, or the suggestion for its time."""
        if (entry := entry_for(self.logbook, point)) is not None:
            return Draft(
                odometer_km=entry.odometer_km,
                fuel_percent=entry.fuel_percent,
                gas1_percent=entry.gas1_percent,
                gas2_percent=entry.gas2_percent,
                fuel_litres=entry.fuel.litres if entry.fuel else 0.0,
                fuel_amount=(entry.fuel.amount or 0.0) if entry.fuel else 0.0,
                gas_litres=entry.gas.litres if entry.gas else 0.0,
                gas_amount=(entry.gas.amount or 0.0) if entry.gas else 0.0,
            )
        return Draft.from_suggestion(self.logbook.suggestion(point.counters.distance_m, until=point.time))

    async def async_save_late(self) -> LogbookEntry:
        """
        Save the form for the chosen earlier time, then return to the current occasion.

        Returns:
            The new or completed entry.

        Raises:
            ValueError: No earlier time is chosen.

        """
        if self.late is None:
            raise ValueError("late")
        draft = self.draft
        entry = self._store_late(
            self.late,
            odometer_km=draft.odometer_km,
            fuel_percent=draft.fuel_percent,
            gas1_percent=draft.gas1_percent,
            gas2_percent=draft.gas2_percent,
            fuel=draft.fuel,
            gas=draft.gas,
        )
        self.select_late(None)
        self._refresh_draft_without_pending()
        await self._async_refresh_csv()
        return entry

    async def async_add_late(
        self,
        point: LatePoint,
        *,
        odometer_km: float | None = None,
        fuel: Refill | None = None,
        gas: Refill | None = None,
    ) -> LogbookEntry:
        """
        Add a refill at an earlier time from a service action, or complete the entry made for it.

        A refill fills its tank: fuel the fuel tank, gas both gas tanks. Without
        `odometer_km`, the entry keeps its odometer or gets the suggestion.

        Returns:
            The new or completed entry.

        """
        existing = entry_for(self.logbook, point)
        values: dict[str, Any] = {
            "odometer_km": odometer_km
            if odometer_km is not None
            else (
                existing.odometer_km
                if existing
                else self.logbook.suggest_odometer(point.counters.distance_m, until=point.time)
            ),
        }
        if fuel is not None:
            values["fuel"] = fuel
            values["fuel_percent"] = FULL_PERCENT
        if gas is not None:
            values["gas"] = gas
            values["gas1_percent"] = values["gas2_percent"] = FULL_PERCENT
        entry = self._store_late(point, **values)
        self._refresh_draft_without_pending()
        await self._async_refresh_csv()
        return entry

    def _store_late(self, point: LatePoint, **values: Any) -> LogbookEntry:
        """Complete the entry made for `point`, or add a late entry with the counters of that time."""
        if (existing := entry_for(self.logbook, point)) is not None:
            return self.logbook.update(existing.id, **values)
        return self.logbook.add(
            point.time,
            Occasion.LATE,
            trip_start=point.trip_start,
            stop_start=point.stop_start,
            lat=point.lat,
            lon=point.lon,
            place=point.place,
            distance_counter_m=point.counters.distance_m,
            ascent_counter_m=point.counters.ascent_m,
            descent_counter_m=point.counters.descent_m,
            **values,
        )

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

    async def async_add_travel_cost(
        self,
        day: date,
        category: CostCategory,
        amount: float,
        *,
        trip_start: datetime | None = None,
        country: str | None = None,
        note: str | None = None,
    ) -> TravelCost:
        """
        Add a travel cost, store it and rewrite its CSV file.

        Returns:
            The new cost.

        Raises:
            ValueError: The amount is not positive or the country is no two-letter code.

        """
        cost = self.logbook.add_travel_cost(
            day, category, amount, trip_start=trip_start, country=country, note=note, recorded=dt_util.utcnow()
        )
        await self._async_travel_costs_changed()
        return cost

    async def async_update_travel_cost(self, cost_id: str, changes: dict[str, Any]) -> TravelCost:
        """
        Change fields of a travel cost.

        Returns:
            The changed cost.

        Raises:
            KeyError: No cost has `cost_id`.
            ValueError: The changed amount or country is invalid.

        """
        cost = self.logbook.update_travel_cost(cost_id, **changes)
        await self._async_travel_costs_changed()
        return cost

    async def async_remove_travel_cost(self, cost_id: str) -> None:
        """
        Delete a travel cost.

        Raises:
            KeyError: No cost has `cost_id`.

        """
        self.logbook.remove_travel_cost(cost_id)
        await self._async_travel_costs_changed()

    async def async_set_no_toll(self, trip_start: datetime, no_toll: bool) -> None:
        """Mark a trip as having no toll, or remove the mark."""
        self.logbook.set_no_toll(trip_start, no_toll)
        self._changed()

    async def async_write_travel_csv(self) -> Path:
        """
        Write the CSV file of all travel costs into the output folder.

        Returns:
            The path of the file.

        """
        text = travel_costs_csv(
            list(self.logbook.travel_costs),
            self._trip_titles(),
            self.hass.config.language,
            dt_util.get_default_time_zone(),
        )
        path = self.travel_csv_path
        await self.hass.async_add_executor_job(_write_text, path, text)
        return path

    async def _async_travel_costs_changed(self) -> None:
        self._changed()
        try:
            await self.async_write_travel_csv()
        except OSError as err:
            LOGGER.warning("The travel costs CSV file could not be written: %s", err)

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
            self._set_current_draft(Draft.from_suggestion(self.logbook.suggestion()))
        self._changed()

    def _set_current_draft(self, draft: Draft) -> None:
        """Set the form of the current occasion; while a late entry is chosen, it waits until that is done."""
        if self.late is not None:
            self._current_draft = draft
        else:
            self.draft = draft

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
