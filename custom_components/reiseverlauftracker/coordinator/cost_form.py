"""
The travel costs form: category, country, amount, note and day for the trip chosen in the export selection.

With "all exports" chosen, a cost is saved without a trip on the chosen day
(docs/features/feat-09-nachtraege.md 6.3, feat-10-tour.md 5.4). The day follows
the start of the chosen trip until it is changed for that trip; the country
likewise starts at the trip's first toll country.
"""

from datetime import date
from typing import TYPE_CHECKING, Any

from custom_components.reiseverlauftracker.const import EXPORT_CHOICE_ALL
from homeassistant.util import dt as dt_util

from .logbook import CostCategory, TravelCost

if TYPE_CHECKING:
    from .base import ReiseverlaufDataUpdateCoordinator
    from .exports import ExportInfo

COUNTRY_NONE = "none"


class CostFormError(ValueError):
    """The form cannot be saved; `args[0]` is the translation key of the reason."""


class TravelCostForm:
    """Values of the travel costs form and saving them."""

    def __init__(self, coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
        """Start with toll, no amount and the day of the chosen trip."""
        self.coordinator = coordinator
        self.category = CostCategory.TOLL
        self._country: str | None = None
        self._country_trip: str | None = None
        self.amount: float | None = None
        self.note = ""
        self._day: date | None = None
        self._day_trip: str | None = None

    def trip(self) -> ExportInfo | None:
        """Return the trip chosen in the export selection, or None for "all exports" and for a tour."""
        choice = self.coordinator.current_export_choice()
        if choice is None or choice == EXPORT_CHOICE_ALL:
            return None
        exports = [info for info in self.coordinator.find_exports(choice) if not info.is_tour]
        return exports[0] if exports else None

    def _trip_key(self) -> str | None:
        trip = self.trip()
        return trip.folder if trip else None

    @property
    def day(self) -> date:
        """Return the chosen day; it starts at the trip's first day, without a trip at today."""
        trip = self.trip()
        if self._day is not None and self._day_trip == self._trip_key():
            return self._day
        moment = trip.start if trip else dt_util.utcnow()
        return dt_util.as_local(moment).date()

    def set_day(self, value: date) -> None:
        """Set the day for the chosen trip; choosing another trip starts again at its first day."""
        self._day, self._day_trip = value, self._trip_key()
        self.coordinator.async_update_listeners()

    def country_options(self) -> list[str]:
        """Return the trip's countries, then the other toll countries, then "no country"; lower-case codes."""
        trip = self.trip()
        if trip is not None:
            # Older exports learn their countries in the background; the options follow once they are known.
            self.coordinator.countries.ensure(trip)
        countries = trip.countries if trip is not None and trip.countries else ()
        codes = dict.fromkeys((*countries, *self.coordinator.settings.toll_countries))
        return [*(code.lower() for code in codes), COUNTRY_NONE]

    @property
    def country_option(self) -> str:
        """Return the chosen country; by default, and after choosing another trip, the trip's first toll country."""
        options = self.country_options()
        if self._country is not None and self._country in options and self._country_trip == self._trip_key():
            return self._country
        trip = self.trip()
        tolls = self.coordinator.settings.toll_countries
        first = next((c for c in (trip.countries or ()) if c in tolls), None) if trip else None
        return first.lower() if first else COUNTRY_NONE

    def set_country(self, option: str) -> None:
        """Choose a country, or "no country", for the chosen trip."""
        self._country, self._country_trip = option, self._trip_key()
        self.coordinator.async_update_listeners()

    def set_category(self, option: str) -> None:
        """Choose the category."""
        self.category = CostCategory(option)
        self.coordinator.async_update_listeners()

    def set_amount(self, value: float) -> None:
        """Set the amount in the currency of the instance."""
        self.amount = value or None
        self.coordinator.async_update_listeners()

    def set_note(self, value: str) -> None:
        """Set the note."""
        self.note = value.strip()
        self.coordinator.async_update_listeners()

    async def async_save(self) -> TravelCost:
        """
        Save the form as a travel cost; amount and note are cleared, category and country stay for the next one.

        Returns:
            The new cost.

        Raises:
            CostFormError: No amount is given.

        """
        if not self.amount or self.amount <= 0:
            raise CostFormError("travel_cost_without_amount")
        trip = self.trip()
        country = self.country_option
        cost = await self.coordinator.logbook.async_add_travel_cost(
            self.day,
            self.category,
            self.amount,
            trip_start=trip.start if trip else None,
            country=None if country == COUNTRY_NONE else country.upper(),
            note=self.note or None,
        )
        self.amount = None
        self.note = ""
        self.coordinator.async_update_listeners()
        return cost

    async def async_toggle_no_toll(self) -> bool:
        """
        Mark the chosen trip as having no toll, or remove the mark.

        Returns:
            Whether the trip is marked now.

        Raises:
            CostFormError: No trip is chosen.

        """
        trip = self.trip()
        if trip is None:
            raise CostFormError("travel_cost_without_trip")
        marked = trip.start not in self.coordinator.logbook.logbook.no_toll_trips
        await self.coordinator.logbook.async_set_no_toll(trip.start, marked)
        return marked


def trip_costs_data(coordinator: ReiseverlaufDataUpdateCoordinator, trip: ExportInfo) -> dict[str, Any]:
    """Return the travel costs of a trip as attribute data: entries, sums per category, countries, no-toll mark."""
    book = coordinator.logbook.logbook
    costs = book.travel_costs_of_trip(trip.start)
    sums: dict[str, float] = {}
    for cost in costs:
        sums[cost.category.value] = round(sums.get(cost.category.value, 0.0) + cost.amount, 2)
    return {
        "eintraege": [travel_cost_data(c) for c in costs],
        "summen": sums,
        "summe": round(sum(c.amount for c in costs), 2),
        "laender": list(trip.countries or ()),
        "keine_maut": trip.start in book.no_toll_trips,
    }


def travel_cost_data(cost: TravelCost) -> dict[str, Any]:
    """Return a travel cost as attribute or response data, keyed in German like the other attributes."""
    return {
        "id": cost.id,
        "datum": cost.day.isoformat(),
        "reise": cost.trip_start.isoformat() if cost.trip_start else None,
        "kategorie": cost.category.value,
        "land": cost.country,
        "betrag": cost.amount,
        "notiz": cost.note,
    }
