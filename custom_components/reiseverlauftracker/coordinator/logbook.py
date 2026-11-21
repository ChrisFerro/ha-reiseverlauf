"""
Logbook of odometer readings, tank levels and refills.

The logbook has no Home Assistant dependencies. The coordinator persists
`as_dict()` in its own `Store`, which outlives the per-trip log, and feeds the
distance measured during trips into it, so that the odometer can be carried
forward between readings (see docs/features/feat-06-fahrtenbuch.md).
"""

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any
import uuid

LOGBOOK_VERSION = 1
FULL_PERCENT = 100.0
# A parked period ends at the next trip start; more distance in between means a trip without entries.
MAX_PARKED_DISTANCE_M = 1000.0


class Occasion(StrEnum):
    """Why an entry was made; the UI shows their translations."""

    TRIP_START = "reisestart"
    STOP = "halt"
    MANUAL = "manuell"  # codespell:ignore manuell
    LATE = "nachtrag"


class CostCategory(StrEnum):
    """Kinds of travel costs (docs/features/feat-09-nachtraege.md 5.6)."""

    TOLL = "maut"
    VIGNETTE = "vignette"
    FERRY = "faehre"
    TUNNEL = "tunnel"
    PITCH = "stellplatz"
    OTHER = "sonstiges"


@dataclass(frozen=True, slots=True)
class TravelCost:
    """
    A travel cost such as toll, ferry or pitch fee, usually entered after the trip.

    Every cost has a day; it counts in that day's month. A cost may belong to a
    trip, referenced by the trip's start time, and then defaults to the trip's
    first day; costs during a stay between trips have no trip
    (docs/features/feat-10-tour.md 5.4). `country` is an ISO 3166-1 alpha-2 code.
    """

    id: str
    day: date
    category: CostCategory
    amount: float
    trip_start: datetime | None = None
    country: str | None = None
    note: str | None = None
    recorded: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the cost as a JSON-serialisable dict."""
        return {
            "id": self.id,
            "day": self.day.isoformat(),
            "category": self.category.value,
            "amount": self.amount,
            "trip_start": self.trip_start.isoformat() if self.trip_start else None,
            "country": self.country,
            "note": self.note,
            "recorded": self.recorded.isoformat() if self.recorded else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TravelCost:
        """Rebuild a cost from `as_dict()` output."""
        return cls(
            id=data["id"],
            day=date.fromisoformat(data["day"]),
            category=CostCategory(data["category"]),
            amount=data["amount"],
            trip_start=_optional_time(data.get("trip_start")),
            country=data.get("country"),
            note=data.get("note"),
            recorded=_optional_time(data.get("recorded")),
        )


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    """Costs of a period by kind."""

    fuel: float = 0.0
    gas: float = 0.0
    travel: dict[CostCategory, float] = field(default_factory=dict)

    @property
    def total(self) -> float:
        """Return all costs together."""
        return self.fuel + self.gas + sum(self.travel.values())


@dataclass(frozen=True, slots=True)
class Refill:
    """Fuel or gas bought at one stop; gas always fills both tanks."""

    litres: float
    amount: float | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the refill as a JSON-serialisable dict."""
        return {"litres": self.litres, "amount": self.amount}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Refill | None:
        """Rebuild a refill from `as_dict()` output."""
        return cls(litres=data["litres"], amount=data.get("amount")) if data else None


@dataclass(frozen=True, slots=True)
class LogbookEntry:
    """
    One logbook entry.

    `distance_counter_m` is the total distance the integration had measured when
    the entry was made; the difference to a later counter is the distance driven
    in between. `ascent_counter_m` and `descent_counter_m` do the same for the
    metres uphill and downhill; entries from before they were counted have None. Trip and stop are referenced by their start times, because the
    per-trip log is discarded once the trip is closed.
    """

    id: str
    time: datetime
    occasion: Occasion
    distance_counter_m: float
    ascent_counter_m: float | None = None
    descent_counter_m: float | None = None
    odometer_km: float | None = None
    odometer_corrected: bool = False
    fuel_percent: float | None = None
    gas1_percent: float | None = None
    gas2_percent: float | None = None
    fuel: Refill | None = None
    gas: Refill | None = None
    trip_start: datetime | None = None
    stop_start: datetime | None = None
    lat: float | None = None
    lon: float | None = None
    place: str | None = None

    @property
    def cost(self) -> float:
        """Return what fuel and gas cost at this entry."""
        return sum(r.amount or 0.0 for r in (self.fuel, self.gas) if r is not None)

    def as_dict(self) -> dict[str, Any]:
        """Return the entry as a JSON-serialisable dict."""
        return {
            "id": self.id,
            "time": self.time.isoformat(),
            "occasion": self.occasion.value,
            "distance_counter_m": self.distance_counter_m,
            "ascent_counter_m": self.ascent_counter_m,
            "descent_counter_m": self.descent_counter_m,
            "odometer_km": self.odometer_km,
            "odometer_corrected": self.odometer_corrected,
            "fuel_percent": self.fuel_percent,
            "gas1_percent": self.gas1_percent,
            "gas2_percent": self.gas2_percent,
            "fuel": self.fuel.as_dict() if self.fuel else None,
            "gas": self.gas.as_dict() if self.gas else None,
            "trip_start": self.trip_start.isoformat() if self.trip_start else None,
            "stop_start": self.stop_start.isoformat() if self.stop_start else None,
            "lat": self.lat,
            "lon": self.lon,
            "place": self.place,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LogbookEntry:
        """Rebuild an entry from `as_dict()` output."""
        return cls(
            id=data["id"],
            time=datetime.fromisoformat(data["time"]),
            occasion=Occasion(data["occasion"]),
            distance_counter_m=data["distance_counter_m"],
            ascent_counter_m=data.get("ascent_counter_m"),
            descent_counter_m=data.get("descent_counter_m"),
            odometer_km=data.get("odometer_km"),
            odometer_corrected=data.get("odometer_corrected", False),
            fuel_percent=data.get("fuel_percent"),
            gas1_percent=data.get("gas1_percent"),
            gas2_percent=data.get("gas2_percent"),
            fuel=Refill.from_dict(data.get("fuel")),
            gas=Refill.from_dict(data.get("gas")),
            trip_start=_optional_time(data.get("trip_start")),
            stop_start=_optional_time(data.get("stop_start")),
            lat=data.get("lat"),
            lon=data.get("lon"),
            place=data.get("place"),
        )


@dataclass(frozen=True, slots=True)
class Suggestion:
    """Values the form is pre-filled with."""

    odometer_km: float | None = None
    fuel_percent: float | None = None
    gas1_percent: float | None = None
    gas2_percent: float | None = None


class FormField(StrEnum):
    """Fields of the logbook form; the values are the attribute names of `Draft`."""

    ODOMETER = "odometer_km"
    FUEL = "fuel_percent"
    GAS1 = "gas1_percent"
    GAS2 = "gas2_percent"
    FUEL_LITRES = "fuel_litres"
    FUEL_AMOUNT = "fuel_amount"
    GAS_LITRES = "gas_litres"
    GAS_AMOUNT = "gas_amount"


@dataclass(frozen=True, slots=True)
class Draft:
    """
    Values in the logbook form; litres and amounts of 0 mean no refill.

    Entering litres sets the matching level to 100 %, since a refill fills up:
    fuel the fuel tank, gas both gas tanks.
    """

    odometer_km: float | None = None
    fuel_percent: float | None = None
    gas1_percent: float | None = None
    gas2_percent: float | None = None
    fuel_litres: float = 0.0
    fuel_amount: float = 0.0
    gas_litres: float = 0.0
    gas_amount: float = 0.0

    @classmethod
    def from_suggestion(cls, suggestion: Suggestion) -> Draft:
        """Return a form pre-filled with the suggestion and no refills."""
        return cls(
            odometer_km=suggestion.odometer_km,
            fuel_percent=suggestion.fuel_percent,
            gas1_percent=suggestion.gas1_percent,
            gas2_percent=suggestion.gas2_percent,
        )

    def value(self, form_field: FormField) -> float | None:
        """Return the value of one field."""
        return getattr(self, form_field.value)

    def with_value(self, form_field: FormField, value: float) -> Draft:
        """Return the form with one field changed, filling the tank on a new refill."""
        changed = replace(self, **{form_field.value: value})
        if form_field is FormField.FUEL_LITRES and value > 0 and self.fuel_litres <= 0:
            changed = replace(changed, fuel_percent=FULL_PERCENT)
        if form_field is FormField.GAS_LITRES and value > 0 and self.gas_litres <= 0:
            changed = replace(changed, gas1_percent=FULL_PERCENT, gas2_percent=FULL_PERCENT)
        return changed

    @property
    def fuel(self) -> Refill | None:
        """Return the fuel refill, or None without litres."""
        return Refill(self.fuel_litres, self.fuel_amount or None) if self.fuel_litres > 0 else None

    @property
    def gas(self) -> Refill | None:
        """Return the gas refill, or None without litres."""
        return Refill(self.gas_litres, self.gas_amount or None) if self.gas_litres > 0 else None

    def as_dict(self) -> dict[str, Any]:
        """Return the form as a JSON-serialisable dict."""
        return {f.value: self.value(f) for f in FormField}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Draft:
        """Rebuild a form from `as_dict()` output; unknown keys are ignored."""
        return cls(**{f.value: data[f.value] for f in FormField if f.value in data})


@dataclass(frozen=True, slots=True)
class TripSummary:
    """Logbook figures of one trip for its export."""

    odometer_start_km: float | None = None
    odometer_end_km: float | None = None
    fuel_litres: float = 0.0
    fuel_cost: float = 0.0
    gas_litres: float = 0.0
    gas_cost: float = 0.0

    @property
    def cost(self) -> float:
        """Return fuel and gas costs together."""
        return self.fuel_cost + self.gas_cost


@dataclass(frozen=True, slots=True)
class ParkedConsumption:
    """
    Fuel the heating used while parked, from the levels read off the gauge.

    Sums over all parked periods; the levels are coarse, so single periods mostly
    lie below the reading accuracy (docs/features/feat-08-verbrauchsmodell.md 5.3).
    """

    periods: int
    days: float
    litres: float

    @property
    def litres_per_day(self) -> float | None:
        """Return the litres used per parked day, or None without parked time."""
        return max(self.litres, 0.0) / self.days if self.days > 0 else None


@dataclass(slots=True)
class Logbook:
    """
    All entries of one vehicle, plus the distance, ascent and descent measured so far.

    Both are split into closed trips and the running trip: the running trip's
    distance may still shrink (merged GPS fixes) and is only added for good when
    the trip's log is discarded.
    """

    tank_litres: float = 90.0
    entries: list[LogbookEntry] = field(default_factory=list)
    closed_trips_m: float = 0.0
    running_trip_m: float = 0.0
    closed_trips_ascent_m: float = 0.0
    running_trip_ascent_m: float = 0.0
    closed_trips_descent_m: float = 0.0
    running_trip_descent_m: float = 0.0
    travel_costs: list[TravelCost] = field(default_factory=list)
    no_toll_trips: set[datetime] = field(default_factory=set)

    @property
    def distance_counter_m(self) -> float:
        """Return the total distance measured by the integration."""
        return self.closed_trips_m + self.running_trip_m

    @property
    def ascent_counter_m(self) -> float:
        """Return the total climb uphill measured by the integration."""
        return self.closed_trips_ascent_m + self.running_trip_ascent_m

    @property
    def descent_counter_m(self) -> float:
        """Return the total metres downhill measured by the integration."""
        return self.closed_trips_descent_m + self.running_trip_descent_m

    def set_running_trip(self, metres: float, ascent_m: float = 0.0, descent_m: float = 0.0) -> None:
        """Set distance, ascent and descent of the running trip so far."""
        self.running_trip_m = max(metres, 0.0)
        self.running_trip_ascent_m = max(ascent_m, 0.0)
        self.running_trip_descent_m = max(descent_m, 0.0)

    def close_trip(self) -> None:
        """Add the running trip's distance, ascent and descent to the closed trips."""
        self.closed_trips_m += self.running_trip_m
        self.closed_trips_ascent_m += self.running_trip_ascent_m
        self.closed_trips_descent_m += self.running_trip_descent_m
        self.running_trip_m = self.running_trip_ascent_m = self.running_trip_descent_m = 0.0

    def get(self, entry_id: str) -> LogbookEntry | None:
        """Return the entry with `entry_id`."""
        return next((e for e in self.entries if e.id == entry_id), None)

    def last(self, *, having: str | None = None, until: datetime | None = None) -> LogbookEntry | None:
        """
        Return the latest entry, or the latest one where the field `having` is set.

        With `until`, only entries up to that time count, so that an entry added
        later for an earlier time builds on the entries before it.
        """
        for entry in reversed(self.entries):
            if until is not None and entry.time > until:
                continue
            if having is None or getattr(entry, having) is not None:
                return entry
        return None

    def add(
        self,
        time: datetime,
        occasion: Occasion,
        *,
        odometer_km: float | None = None,
        fuel_percent: float | None = None,
        gas1_percent: float | None = None,
        gas2_percent: float | None = None,
        fuel: Refill | None = None,
        gas: Refill | None = None,
        trip_start: datetime | None = None,
        stop_start: datetime | None = None,
        lat: float | None = None,
        lon: float | None = None,
        place: str | None = None,
        distance_counter_m: float | None = None,
        ascent_counter_m: float | None = None,
        descent_counter_m: float | None = None,
    ) -> LogbookEntry:
        """
        Add an entry and return it.

        The entry belongs to `distance_counter_m`, by default the current one; an
        entry saved after its occasion passes the counter of the occasion, so that
        the distance driven since is not lost; `ascent_counter_m` and `descent_counter_m` likewise. The odometer counts as corrected
        when it differs from the carried-forward value at that counter; the
        difference then shows how far off the measured distance was.
        """
        counter = self.distance_counter_m if distance_counter_m is None else distance_counter_m
        suggested = self.suggest_odometer(counter, until=time)
        entry = LogbookEntry(
            id=uuid.uuid4().hex,
            time=time,
            occasion=occasion,
            distance_counter_m=counter,
            ascent_counter_m=self.ascent_counter_m if ascent_counter_m is None else ascent_counter_m,
            descent_counter_m=self.descent_counter_m if descent_counter_m is None else descent_counter_m,
            odometer_km=odometer_km,
            odometer_corrected=odometer_km is not None and suggested is not None and odometer_km != suggested,
            fuel_percent=fuel_percent,
            gas1_percent=gas1_percent,
            gas2_percent=gas2_percent,
            fuel=fuel,
            gas=gas,
            trip_start=trip_start,
            stop_start=stop_start,
            lat=lat,
            lon=lon,
            place=place,
        )
        self.entries.append(entry)
        self.entries.sort(key=lambda e: e.time)
        return entry

    def update(self, entry_id: str, **changes: Any) -> LogbookEntry:
        """
        Change fields of an entry and return the new entry.

        Raises:
            KeyError: No entry has `entry_id`.

        """
        entry = self.get(entry_id)
        if entry is None:
            raise KeyError(entry_id)
        if "odometer_km" in changes and changes["odometer_km"] != entry.odometer_km:
            changes.setdefault("odometer_corrected", True)
        changed = replace(entry, **changes)
        self.entries = sorted((changed if e is entry else e for e in self.entries), key=lambda e: e.time)
        return changed

    def remove(self, entry_id: str) -> None:
        """
        Delete an entry.

        Raises:
            KeyError: No entry has `entry_id`.

        """
        if self.get(entry_id) is None:
            raise KeyError(entry_id)
        self.entries = [e for e in self.entries if e.id != entry_id]

    def km_since(self, entry: LogbookEntry, counter_m: float | None = None) -> float:
        """Return the distance measured since `entry` until `counter_m` (default: now) in kilometres."""
        counter = self.distance_counter_m if counter_m is None else counter_m
        return max(counter - entry.distance_counter_m, 0.0) / 1000

    def suggest_odometer(self, counter_m: float | None = None, *, until: datetime | None = None) -> float | None:
        """
        Return the last odometer reading plus the distance measured since, in whole kilometres.

        `counter_m` and `until` give an earlier point than now: the distance
        counter then, and the time up to which readings count.
        """
        last = self.last(having="odometer_km", until=until)
        if last is None or last.odometer_km is None:
            return None
        return float(round(last.odometer_km + self.km_since(last, counter_m)))

    def average_consumption(self) -> float | None:
        """
        Return the fuel consumption in l/100 km by the full-tank method.

        Every refill to 100 % closes an interval: the litres bought since the
        previous full refill, partial refills included, divided by the odometer
        distance in between. The first full refill only marks the start.

        Returns:
            Total litres ÷ total distance of all closed intervals, or None
            before there are two full refills with odometer readings.

        """
        litres_total = km_total = litres_open = 0.0
        previous_full: LogbookEntry | None = None
        for entry in self.entries:
            if entry.fuel is None:
                continue
            litres_open += entry.fuel.litres
            if entry.odometer_km is None or (entry.fuel_percent or 0.0) < FULL_PERCENT:
                continue
            if previous_full is not None and previous_full.odometer_km is not None:
                km = entry.odometer_km - previous_full.odometer_km
                if km > 0:
                    litres_total += litres_open
                    km_total += km
            previous_full, litres_open = entry, 0.0
        return litres_total / km_total * 100 if km_total > 0 else None

    def parked_consumption(self) -> ParkedConsumption | None:
        """
        Return what the levels read off the gauge say the heating used while parked.

        A parked period runs from the last entry with a fuel level before a trip
        start to the trip start, if that has a level too, no fuel was bought in
        between or at the start, and the vehicle did not move. Differences are
        summed with their sign, so that readings too high and too low cancel out.

        Returns:
            The sums over all parked periods, or None before there is one.

        """
        periods, days, percent = 0, 0.0, 0.0
        previous: LogbookEntry | None = None
        refilled = False
        for entry in self.entries:
            refilled = refilled or entry.fuel is not None
            if entry.fuel_percent is None:
                continue
            if (
                entry.occasion is Occasion.TRIP_START
                and previous is not None
                and previous.fuel_percent is not None
                and not refilled
                and entry.distance_counter_m - previous.distance_counter_m <= MAX_PARKED_DISTANCE_M
                and entry.time > previous.time
            ):
                periods += 1
                days += (entry.time - previous.time) / timedelta(days=1)
                percent += previous.fuel_percent - entry.fuel_percent
            # A refill at this entry is part of its level, which starts the next period.
            previous, refilled = entry, False
        if periods == 0:
            return None
        return ParkedConsumption(periods=periods, days=days, litres=percent / 100 * self.tank_litres)

    def suggest_fuel_percent(self, counter_m: float | None = None, *, until: datetime | None = None) -> float | None:
        """
        Return the last fuel level minus what the distance since has used, in whole percent.

        `counter_m` and `until` give an earlier point than now, as for `suggest_odometer`.
        """
        last = self.last(having="fuel_percent", until=until)
        if last is None or last.fuel_percent is None:
            return None
        consumption = self.average_consumption()
        if consumption is None or self.tank_litres <= 0:
            return last.fuel_percent
        used_percent = self.km_since(last, counter_m) * consumption / 100 / self.tank_litres * 100
        return float(round(min(max(last.fuel_percent - used_percent, 0.0), FULL_PERCENT)))

    def suggestion(self, counter_m: float | None = None, *, until: datetime | None = None) -> Suggestion:
        """Return the values to pre-fill the form with, by default for now."""
        gas1 = self.last(having="gas1_percent", until=until)
        gas2 = self.last(having="gas2_percent", until=until)
        return Suggestion(
            odometer_km=self.suggest_odometer(counter_m, until=until),
            fuel_percent=self.suggest_fuel_percent(counter_m, until=until),
            gas1_percent=gas1.gas1_percent if gas1 else None,
            gas2_percent=gas2.gas2_percent if gas2 else None,
        )

    def cost_between(self, start: datetime, end: datetime) -> float:
        """Return fuel and gas costs of the entries from `start` until before `end`."""
        return sum(e.cost for e in self.entries if start <= e.time < end)

    def costs_between(self, start: datetime, end: datetime) -> CostBreakdown:
        """
        Return fuel, gas and travel costs from `start` until before `end`, by kind.

        Refills count at their entry's time, travel costs on their day, taken as
        midnight in the time zone of `start`.
        """
        entries = [e for e in self.entries if start <= e.time < end]
        travel: dict[CostCategory, float] = {}
        for cost in self.travel_costs:
            if start <= datetime.combine(cost.day, datetime.min.time(), start.tzinfo) < end:
                travel[cost.category] = travel.get(cost.category, 0.0) + cost.amount
        return CostBreakdown(
            fuel=sum(e.fuel.amount or 0.0 for e in entries if e.fuel is not None),
            gas=sum(e.gas.amount or 0.0 for e in entries if e.gas is not None),
            travel=travel,
        )

    def get_travel_cost(self, cost_id: str) -> TravelCost | None:
        """Return the travel cost with `cost_id`."""
        return next((c for c in self.travel_costs if c.id == cost_id), None)

    def add_travel_cost(
        self,
        day: date,
        category: CostCategory,
        amount: float,
        *,
        trip_start: datetime | None = None,
        country: str | None = None,
        note: str | None = None,
        recorded: datetime | None = None,
    ) -> TravelCost:
        """
        Add a travel cost and return it.

        Raises:
            ValueError: The amount is not positive or the country is no two-letter code.

        """
        cost = _checked_cost(
            TravelCost(
                id=uuid.uuid4().hex,
                day=day,
                category=category,
                amount=amount,
                trip_start=trip_start,
                country=country,
                note=note or None,
                recorded=recorded,
            )
        )
        self.travel_costs.append(cost)
        self.travel_costs.sort(key=lambda c: c.day)
        return cost

    def update_travel_cost(self, cost_id: str, **changes: Any) -> TravelCost:
        """
        Change fields of a travel cost and return the new cost.

        Raises:
            KeyError: No cost has `cost_id`.
            ValueError: The changed amount or country is invalid.

        """
        cost = self.get_travel_cost(cost_id)
        if cost is None:
            raise KeyError(cost_id)
        changed = _checked_cost(replace(cost, **changes))
        self.travel_costs = sorted((changed if c is cost else c for c in self.travel_costs), key=lambda c: c.day)
        return changed

    def remove_travel_cost(self, cost_id: str) -> None:
        """
        Delete a travel cost.

        Raises:
            KeyError: No cost has `cost_id`.

        """
        if self.get_travel_cost(cost_id) is None:
            raise KeyError(cost_id)
        self.travel_costs = [c for c in self.travel_costs if c.id != cost_id]

    def travel_costs_of_trip(self, trip_start: datetime) -> list[TravelCost]:
        """Return the travel costs that belong to the trip that started at `trip_start`."""
        return [c for c in self.travel_costs if c.trip_start == trip_start]

    def set_no_toll(self, trip_start: datetime, no_toll: bool) -> None:
        """Mark a trip as having no toll, or remove the mark (docs/features/feat-09-nachtraege.md 5.9)."""
        if no_toll:
            self.no_toll_trips.add(trip_start)
        else:
            self.no_toll_trips.discard(trip_start)

    def toll_settled(self, trip_start: datetime) -> bool:
        """Return whether the trip has a toll cost or is marked as having none."""
        return trip_start in self.no_toll_trips or any(
            c.category is CostCategory.TOLL for c in self.travel_costs_of_trip(trip_start)
        )

    def trip_summary(self, trip_start: datetime) -> TripSummary:
        """
        Return the logbook figures of the trip that started at `trip_start`.

        Call it when the trip has ended, before `close_trip()`. The entries of the
        trip include its arrival, which begins after the trip's end time. Without a
        reading at the trip start there is no start odometer; the end odometer is
        carried forward from the latest reading to the current distance counter.
        """
        entries = [e for e in self.entries if e.trip_start == trip_start]
        readings = [e for e in entries if e.odometer_km is not None and e.occasion is Occasion.TRIP_START]
        fuel = [e.fuel for e in entries if e.fuel is not None]
        gas = [e.gas for e in entries if e.gas is not None]
        return TripSummary(
            odometer_start_km=readings[0].odometer_km if readings else None,
            odometer_end_km=self.suggest_odometer(),
            fuel_litres=sum(r.litres for r in fuel),
            fuel_cost=sum(r.amount or 0.0 for r in fuel),
            gas_litres=sum(r.litres for r in gas),
            gas_cost=sum(r.amount or 0.0 for r in gas),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the logbook as a JSON-serialisable dict; the tank size is a setting and not stored."""
        return {
            "version": LOGBOOK_VERSION,
            "closed_trips_m": self.closed_trips_m,
            "running_trip_m": self.running_trip_m,
            "closed_trips_ascent_m": self.closed_trips_ascent_m,
            "running_trip_ascent_m": self.running_trip_ascent_m,
            "closed_trips_descent_m": self.closed_trips_descent_m,
            "running_trip_descent_m": self.running_trip_descent_m,
            "entries": [e.as_dict() for e in self.entries],
            "travel_costs": [c.as_dict() for c in self.travel_costs],
            "no_toll_trips": sorted(t.isoformat() for t in self.no_toll_trips),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], tank_litres: float) -> Logbook:
        """Rebuild a logbook from `as_dict()` output."""
        return cls(
            tank_litres=tank_litres,
            entries=sorted((LogbookEntry.from_dict(e) for e in data.get("entries", [])), key=lambda e: e.time),
            closed_trips_m=data.get("closed_trips_m", 0.0),
            running_trip_m=data.get("running_trip_m", 0.0),
            closed_trips_ascent_m=data.get("closed_trips_ascent_m", 0.0),
            running_trip_ascent_m=data.get("running_trip_ascent_m", 0.0),
            closed_trips_descent_m=data.get("closed_trips_descent_m", 0.0),
            running_trip_descent_m=data.get("running_trip_descent_m", 0.0),
            travel_costs=sorted((TravelCost.from_dict(c) for c in data.get("travel_costs", [])), key=lambda c: c.day),
            no_toll_trips={datetime.fromisoformat(t) for t in data.get("no_toll_trips", [])},
        )


def _optional_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _checked_cost(cost: TravelCost) -> TravelCost:
    """Return the cost with the country in upper case, after checking amount and country."""
    if cost.amount <= 0:
        raise ValueError("amount")
    country = cost.country.strip().upper() if cost.country else None
    if country is not None and (len(country) != 2 or not country.isalpha()):
        raise ValueError("country")
    return replace(cost, country=country or None)
