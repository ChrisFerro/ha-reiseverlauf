"""
Choosing a stored logbook entry in the form, to change or delete it.

The selection offers "new" and the entries of the trip chosen in the export
selection plus the parked time after it; with "all exports" the newest ones
(docs/features/feat-11-eintraege-bearbeiten.md 5.3, 6.2).
"""

from datetime import datetime, tzinfo
from typing import TYPE_CHECKING, Any

from custom_components.reiseverlauftracker.const import EDIT_CHOICE_NEW, EXPORT_CHOICE_ALL
from homeassistant.util import dt as dt_util

from .logbook import FormField, Logbook, LogbookEntry, Occasion

if TYPE_CHECKING:
    from .base import ReiseverlaufDataUpdateCoordinator

# Entries offered with "all exports".
NEWEST_ENTRIES = 30

OCCASION_WORDS = {
    "de": {
        Occasion.TRIP_START: "Reisebeginn",
        Occasion.STOP: "Halt",
        Occasion.MANUAL: "Manuell",  # codespell:ignore manuell
        Occasion.LATE: "Nachtrag",
    },
    "en": {
        Occasion.TRIP_START: "Trip start",
        Occasion.STOP: "Stop",
        Occasion.MANUAL: "Manual",
        Occasion.LATE: "Late entry",
    },
}

FIELD_WORDS = {
    "de": {
        FormField.ODOMETER: "Kilometerstand",
        FormField.FUEL: "Kraftstoff",
        FormField.GAS1: "Gas 1",
        FormField.GAS2: "Gas 2",
    },
    "en": {
        FormField.ODOMETER: "Odometer",
        FormField.FUEL: "Fuel",
        FormField.GAS1: "Gas 1",
        FormField.GAS2: "Gas 2",
    },
}


def _words[T](table: dict[str, T], language: str) -> T:
    return table.get(language.split("-", maxsplit=1)[0], table["en"])


def field_names(fields: list[FormField], language: str) -> list[str]:
    """Return the names of form fields in the language of the instance."""
    words = _words(FIELD_WORDS, language)
    return [words[f] for f in fields]


def entry_label(entry: LogbookEntry, tz: tzinfo, language: str, now: datetime) -> str:
    """Return how an entry appears in the selection, such as `27.09. 17:30 · Nachtrag · Irschenberg · 33768 km`."""
    local = entry.time.astimezone(tz)
    parts = [f"{local:%d.%m.} {local:%H:%M}" if local.year == now.astimezone(tz).year else f"{local:%d.%m.%y %H:%M}"]
    parts.append(_words(OCCASION_WORDS, language)[entry.occasion])
    if entry.place:
        parts.append(entry.place)
    if entry.odometer_km is not None:
        parts.append(f"{entry.odometer_km:.0f} km")
    return " · ".join(parts)


def entries_between(
    logbook: Logbook, start: datetime, until: datetime | None, trip_start: datetime
) -> list[LogbookEntry]:
    """Return the entries of a trip and of the parked time after it until `until`, newest first."""
    return sorted(
        (
            e
            for e in logbook.entries
            if e.trip_start == trip_start or (start <= e.time and (until is None or e.time < until))
        ),
        key=lambda e: e.time,
        reverse=True,
    )


class EntryEditForm:
    """Selection of a stored logbook entry, and changing or deleting it."""

    def __init__(self, coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
        """Start with "new" chosen."""
        self.coordinator = coordinator

    def options(self) -> list[str]:
        """Return "new" and the selectable entries, newest first."""
        return [EDIT_CHOICE_NEW, *self._entries_by_label()]

    def current_option(self) -> str:
        """Return the label of the entry being edited, or "new"."""
        entry = self.entry()
        if entry is None:
            return EDIT_CHOICE_NEW
        return next((label for label, e in self._entries_by_label().items() if e.id == entry.id), EDIT_CHOICE_NEW)

    def entry(self) -> LogbookEntry | None:
        """Return the entry being edited."""
        keeper = self.coordinator.logbook
        return keeper.logbook.get(keeper.editing) if keeper.editing else None

    def select(self, option: str) -> None:
        """Fill the form with the chosen entry and its time, or return to the current occasion with "new"."""
        entry = self._entries_by_label().get(option)
        if entry is not None:
            self.coordinator.late_form.show_time(entry.time)
        self.coordinator.logbook.select_edit(entry)

    async def async_save(self) -> LogbookEntry:
        """
        Store the form in the entry being edited and return to "new".

        A new time in the time field brings the counters and place of that time (6.1).

        Returns:
            The changed entry.

        Raises:
            ValueError: No entry is chosen.

        """
        coordinator = self.coordinator
        keeper = coordinator.logbook
        if (entry := self.entry()) is None:
            raise ValueError("no_entry")
        draft = keeper.draft
        changes: dict[str, Any] = {
            "odometer_km": draft.odometer_km,
            "fuel_percent": draft.fuel_percent,
            "gas1_percent": draft.gas1_percent,
            "gas2_percent": draft.gas2_percent,
            "fuel": draft.fuel,
            "gas": draft.gas,
        }
        if (time := coordinator.late_form.time) is not None and time != entry.time:
            changes["time"] = time
            changes |= await coordinator.late_form.async_moved(entry, time)
        keeper.select_edit(None)
        return await keeper.async_update(entry.id, changes)

    async def async_remove(self) -> LogbookEntry:
        """
        Delete the entry being edited and return to "new".

        Returns:
            The deleted entry.

        Raises:
            ValueError: No entry is chosen.

        """
        if (entry := self.entry()) is None:
            raise ValueError("no_entry")
        await self.coordinator.logbook.async_remove(entry.id)
        return entry

    def _entries_by_label(self) -> dict[str, LogbookEntry]:
        coordinator = self.coordinator
        tz = dt_util.get_default_time_zone()
        now = dt_util.utcnow()
        language = coordinator.hass.config.language
        entries = self._selectable()
        if (editing := self.entry()) is not None and editing not in entries:
            entries = sorted([*entries, editing], key=lambda e: e.time, reverse=True)
        labels: dict[str, LogbookEntry] = {}
        for entry in entries:
            label = entry_label(entry, tz, language, now)
            number = 2
            unique = label
            while unique in labels:
                unique = f"{label} ({number})"
                number += 1
            labels[unique] = entry
        return labels

    def _selectable(self) -> list[LogbookEntry]:
        """Return the entries of the chosen trip and the parked time after it, or the newest ones."""
        coordinator = self.coordinator
        logbook = coordinator.logbook.logbook
        choice = coordinator.current_export_choice()
        exports = coordinator.find_exports(choice) if choice and choice != EXPORT_CHOICE_ALL else []
        if not exports:
            return list(reversed(logbook.entries[-NEWEST_ENTRIES:]))
        info = exports[0]
        following = [i.start for i in coordinator.exports if i.automatic and i.start >= info.end]
        if (log := coordinator.log) is not None and log.start >= info.end:
            following.append(log.start)
        return entries_between(logbook, info.start, min(following, default=None), info.start)
