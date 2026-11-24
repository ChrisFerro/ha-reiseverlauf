"""
Tour: several trips and the stays between them (docs/features/feat-10-tour.md).

Everything here is plain Python without Home Assistant: the night places, the
overview by day and by place, the costs paid during the tour and the estimated
consumption. The integration collects the inputs from the trip exports and the
logbook and hands them in.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta, tzinfo
from itertools import pairwise
from typing import Any

from custom_components.reiseverlauftracker.utils.geo import Position, distance_m

from .model import TrackPoint

# The place of a night is where the vehicle stands at this hour, local time (5.7).
NIGHT_HOUR = 3
# Night places closer than this count as the same place (5.7, 6.3).
SAME_PLACE_M = 500.0
NO_COUNTRY = ""


@dataclass(frozen=True, slots=True)
class TourTrip:
    """One trip of the tour, prepared for export: filtered and trimmed points and its key figures."""

    folder: str
    title: str
    start: datetime
    end: datetime
    points: tuple[TrackPoint, ...]
    distance_km: float
    moving_time: timedelta
    ascent_m: float | None = None
    descent_m: float | None = None
    countries: tuple[str, ...] = ()
    ferry_spans: tuple[tuple[datetime, datetime], ...] = ()
    """Start and end of the ferry crossings; their distance is not part of `distance_km` (Feat-12 5.10)."""
    ferry_km: float = 0.0
    ferry_time: timedelta = timedelta()


@dataclass(frozen=True, slots=True)
class Night:
    """Where the vehicle stood in the night after the evening of `night`; `name_changed` marks a name set by hand."""

    night: date
    lat: float
    lon: float
    name: str | None = None
    name_changed: bool = False

    @property
    def position(self) -> Position:
        """Return the coordinate of the night place."""
        return Position(self.lat, self.lon)

    def as_dict(self) -> dict[str, Any]:
        """Return the night as stored in `export.json` and the raw data of the tour."""
        return {
            "night": self.night.isoformat(),
            "lat": self.lat,
            "lon": self.lon,
            "name": self.name,
            "name_changed": self.name_changed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Night:
        """Rebuild a night from `as_dict()` output."""
        return cls(
            night=date.fromisoformat(data["night"]),
            lat=data["lat"],
            lon=data["lon"],
            name=data.get("name"),
            name_changed=data.get("name_changed", False),
        )


@dataclass(frozen=True, slots=True)
class TourRefill:
    """Fuel and gas bought at one logbook entry; `country` is an ISO code or None."""

    time: datetime
    fuel_litres: float = 0.0
    fuel_amount: float = 0.0
    gas_litres: float = 0.0
    gas_amount: float = 0.0
    country: str | None = None

    @property
    def amount(self) -> float:
        """Return what fuel and gas cost together."""
        return self.fuel_amount + self.gas_amount


@dataclass(frozen=True, slots=True)
class TourCost:
    """A travel cost (toll, pitch …) on its day; the category is the value of `CostCategory`."""

    day: date
    category: str
    amount: float
    country: str | None = None


@dataclass(frozen=True, slots=True)
class ConsumptionInputs:
    """What the logbook knows for the estimated consumption (5.5); None where it knows nothing."""

    consumption_l_100km: float | None = None
    fuel_price: float | None = None
    """Price per litre of the last refill with an amount, for a tour without one."""
    gas_used_percent: float | None = None
    """Percentage points both gas tanks lost during the tour, refills included."""
    gas_litres_per_percent: float | None = None
    gas_price: float | None = None


@dataclass(frozen=True, slots=True)
class TourCosts:
    """What was paid during the tour (5.5): refills at their time, travel costs on their day."""

    fuel_litres: float = 0.0
    fuel_amount: float = 0.0
    gas_litres: float = 0.0
    gas_amount: float = 0.0
    travel: dict[str, float] = field(default_factory=dict)
    by_country: dict[str, float] = field(default_factory=dict)
    """Sums by ISO country code; `NO_COUNTRY` collects the costs without a country."""

    @property
    def total(self) -> float:
        """Return all costs together."""
        return self.fuel_amount + self.gas_amount + sum(self.travel.values())

    def as_dict(self) -> dict[str, Any]:
        """Return the costs as stored in `export.json` and sent with the event, keyed in German."""
        return {
            "diesel_liter": round(self.fuel_litres, 2),
            "diesel_kosten": round(self.fuel_amount, 2),
            "gas_liter": round(self.gas_litres, 2),
            "gas_kosten": round(self.gas_amount, 2),
            "reisekosten": {category: round(amount, 2) for category, amount in self.travel.items()},
            "je_land": {country or "-": round(amount, 2) for country, amount in self.by_country.items()},
            "kosten": round(self.total, 2),
        }


@dataclass(frozen=True, slots=True)
class Estimate:
    """Estimated consumption of the tour, shown as "approx." (5.5)."""

    fuel_litres: float
    fuel_cost: float | None = None
    gas_percent: float | None = None
    gas_litres: float | None = None
    gas_cost: float | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the estimate as stored in `export.json`, keyed in German."""
        return {
            "diesel_liter": round(self.fuel_litres, 1),
            "diesel_kosten": round(self.fuel_cost, 2) if self.fuel_cost is not None else None,
            "gas_prozent": round(self.gas_percent) if self.gas_percent is not None else None,
            "gas_liter": round(self.gas_litres, 1) if self.gas_litres is not None else None,
            "gas_kosten": round(self.gas_cost, 2) if self.gas_cost is not None else None,
        }


@dataclass(frozen=True, slots=True)
class DayRow:
    """One calendar day of the tour: kilometres driven, the place of the following night and the costs."""

    day: date
    km: float
    night: Night | None
    cost: float


@dataclass(frozen=True, slots=True)
class PlaceRow:
    """Days at one place, summed up for statistics and composite (5.7); `nights` is 0 for the arrival day."""

    first: date
    last: date
    nights: int
    name: str | None
    km: float
    cost: float


@dataclass(frozen=True, slots=True)
class TourSummary:
    """Everything the export of a tour shows."""

    start: datetime
    end: datetime
    distance_km: float
    moving_time: timedelta
    ascent_m: float | None
    descent_m: float | None
    days: tuple[DayRow, ...]
    places: tuple[PlaceRow, ...]
    nights: int
    costs: TourCosts
    estimate: Estimate | None
    countries: tuple[str, ...]
    odometer_start_km: float | None = None
    odometer_end_km: float | None = None
    ferry_km: float = 0.0
    ferry_time: timedelta = timedelta()


def night_dates(start: datetime, end: datetime, tz: tzinfo) -> list[date]:
    """Return the evenings whose night place lies in the tour: the next morning's `NIGHT_HOUR` is within it."""
    first = start.astimezone(tz).date() - timedelta(days=1)
    nights: list[date] = []
    day = first
    while (moment := night_moment(day, tz)) <= end:
        if moment > start:
            nights.append(day)
        day += timedelta(days=1)
    return nights


def night_moment(night: date, tz: tzinfo) -> datetime:
    """Return the moment that decides the place of the night after the evening of `night`."""
    return datetime.combine(night + timedelta(days=1), time(NIGHT_HOUR), tz)


def position_at(points: Sequence[TrackPoint], moment: datetime) -> TrackPoint | None:
    """Return the last point at or before `moment`, else the first point; `points` sorted by time."""
    before = None
    for point in points:
        if point.time > moment:
            break
        before = point
    return before or (points[0] if points else None)


def locate_nights(
    trips: Sequence[TourTrip], start: datetime, end: datetime, tz: tzinfo, known: Iterable[Night] = ()
) -> list[Night]:
    """
    Return the place of every night of the tour.

    The vehicle stands where the last trip before the night ended. A name of
    `known` (an earlier version of the tour) is kept for a night at the same
    place, a name set by hand marked as such.
    """
    points = sorted((p for trip in trips for p in trip.points), key=lambda p: p.time)
    known_list = list(known)
    by_night = {night.night: night for night in known_list}
    nights: list[Night] = []
    for day in night_dates(start, end, tz):
        point = position_at(points, night_moment(day, tz))
        if point is None:
            continue
        night = Night(day, point.lat, point.lon)
        earlier = by_night.get(day)
        if earlier is not None and same_place(earlier, night):
            night = replace(night, name=earlier.name, name_changed=earlier.name_changed)
        elif (nearby := next((k for k in known_list if k.name and same_place(k, night)), None)) is not None:
            night = replace(night, name=nearby.name, name_changed=nearby.name_changed)
        nights.append(night)
    return nights


def same_place(a: Night, b: Night) -> bool:
    """Return whether two night places lie within `SAME_PLACE_M`."""
    return distance_m(a.position, b.position) <= SAME_PLACE_M


def night_groups(nights: Sequence[Night]) -> list[list[Night]]:
    """Return runs of consecutive nights at the same place (5.7); a name set by hand starts its own run."""
    groups: list[list[Night]] = []
    for night in nights:
        if groups:
            group = groups[-1]
            first, last = group[0], group[-1]
            consecutive = night.night == last.night + timedelta(days=1) and same_place(first, night)
            if consecutive and _hand_name(night) == _hand_name(last):
                group.append(night)
                continue
        groups.append([night])
    return groups


def _hand_name(night: Night) -> str | None:
    return night.name if night.name_changed else None


def rename_nights(nights: Sequence[Night], names: dict[date, str]) -> list[Night]:
    """Set the names given for some nights, each for all nights of its run at that place; marked as set by hand."""
    renamed = list(nights)
    for group in night_groups(nights):
        name = next((names[n.night] for n in group if n.night in names), None)
        if name is None:
            continue
        for night in group:
            index = renamed.index(night)
            renamed[index] = replace(night, name=name.strip() or None, name_changed=bool(name.strip()))
    return renamed


def unnamed_groups(nights: Sequence[Night]) -> list[list[Night]]:
    """Return the runs of nights at one place that have no name yet; one lookup names a whole run."""
    return [group for group in night_groups(nights) if not any(n.name for n in group)]


def name_group(nights: Sequence[Night], group: Sequence[Night], name: str) -> list[Night]:
    """Return `nights` with the nights of `group` named `name`."""
    members = {n.night for n in group}
    return [replace(n, name=name) if n.night in members else n for n in nights]


def tour_costs(
    refills: Iterable[TourRefill], costs: Iterable[TourCost], start: datetime, end: datetime, tz: tzinfo
) -> TourCosts:
    """Return what was paid from `start` to `end`: refills by time, travel costs by their local day (5.4)."""
    first_day, last_day = start.astimezone(tz).date(), end.astimezone(tz).date()
    fuel_litres = fuel_amount = gas_litres = gas_amount = 0.0
    travel: dict[str, float] = {}
    by_country: dict[str, float] = {}
    for refill in refills:
        if not start <= refill.time <= end:
            continue
        fuel_litres += refill.fuel_litres
        fuel_amount += refill.fuel_amount
        gas_litres += refill.gas_litres
        gas_amount += refill.gas_amount
        if refill.amount > 0:
            key = refill.country or NO_COUNTRY
            by_country[key] = by_country.get(key, 0.0) + refill.amount
    for cost in costs:
        if not first_day <= cost.day <= last_day:
            continue
        travel[cost.category] = travel.get(cost.category, 0.0) + cost.amount
        key = cost.country or NO_COUNTRY
        by_country[key] = by_country.get(key, 0.0) + cost.amount
    return TourCosts(fuel_litres, fuel_amount, gas_litres, gas_amount, travel, by_country)


def gas_used_percent(
    start_level: float | None, end_level: float | None, refilled_litres: float, litres_per_percent: float | None
) -> float | None:
    """
    Return the percentage points both gas tanks lost: levels at start and end plus what the gas stops filled.

    None without both levels, or with gas stops but without knowing how many litres a percentage point holds.
    """
    if start_level is None or end_level is None:
        return None
    if refilled_litres <= 0:
        return start_level - end_level
    if not litres_per_percent:
        return None
    return start_level - end_level + refilled_litres / litres_per_percent


def estimate(distance_km: float, costs: TourCosts, inputs: ConsumptionInputs) -> Estimate | None:
    """
    Return the estimated consumption: distance times average consumption, gas from the tank levels (5.5).

    Without an average consumption there is no estimate. Diesel is priced at the
    average litre price of the tour's refills, else at the last known price.
    """
    if inputs.consumption_l_100km is None:
        return None
    litres = distance_km * inputs.consumption_l_100km / 100
    price = costs.fuel_amount / costs.fuel_litres if costs.fuel_litres > 0 and costs.fuel_amount > 0 else None
    price = price if price is not None else inputs.fuel_price
    gas_percent = inputs.gas_used_percent if inputs.gas_used_percent is not None else None
    gas_litres = gas_cost = None
    if gas_percent is not None and inputs.gas_litres_per_percent is not None:
        gas_litres = max(gas_percent, 0.0) * inputs.gas_litres_per_percent
        gas_price = costs.gas_amount / costs.gas_litres if costs.gas_litres > 0 and costs.gas_amount > 0 else None
        gas_price = gas_price if gas_price is not None else inputs.gas_price
        gas_cost = gas_litres * gas_price if gas_price is not None else None
    return Estimate(
        fuel_litres=litres,
        fuel_cost=litres * price if price is not None else None,
        gas_percent=max(gas_percent, 0.0) if gas_percent is not None else None,
        gas_litres=gas_litres,
        gas_cost=gas_cost,
    )


def day_rows(
    trips: Sequence[TourTrip],
    nights: Sequence[Night],
    refills: Iterable[TourRefill],
    costs: Iterable[TourCost],
    start: datetime,
    end: datetime,
    tz: tzinfo,
) -> list[DayRow]:
    """Return one row per local calendar day from `start` to `end`, days without a drive included (5.6)."""
    km: dict[date, float] = {}
    for trip in trips:
        for a, b in pairwise(trip.points):
            if any(a.time < end_ and b.time > start_ for start_, end_ in trip.ferry_spans):
                continue  # Not driven: on a ferry (Feat-12 5.10).
            day = b.time.astimezone(tz).date()
            km[day] = km.get(day, 0.0) + distance_m(a.position, b.position) / 1000
    paid: dict[date, float] = {}
    for refill in refills:
        if start <= refill.time <= end:
            day = refill.time.astimezone(tz).date()
            paid[day] = paid.get(day, 0.0) + refill.amount
    for cost in costs:
        paid[cost.day] = paid.get(cost.day, 0.0) + cost.amount
    by_night = {night.night: night for night in nights}
    rows: list[DayRow] = []
    day, last = start.astimezone(tz).date(), end.astimezone(tz).date()
    while day <= last:
        rows.append(DayRow(day, km.get(day, 0.0), by_night.get(day), paid.get(day, 0.0)))
        day += timedelta(days=1)
    return rows


def place_rows(days: Sequence[DayRow], nights: Sequence[Night], end_place: str | None = None) -> list[PlaceRow]:
    """
    Sum up the days by the place of their night (5.7).

    A row runs from the first day to the morning after its last night, e.g.
    10.-15.10. for five nights; excursions back to the same place stay in the
    row. Days without a night in the tour (the arrival day) get a row of their
    own with the arrival place.
    """
    group_of: dict[date, int] = {}
    for index, group in enumerate(night_groups(nights)):
        for night in group:
            group_of[night.night] = index
    rows: list[PlaceRow] = []
    current: int | None = None
    for day in days:
        key = group_of.get(day.day) if day.night is not None else None
        if rows and key is not None and key == current:
            row = rows[-1]
            rows[-1] = replace(
                row,
                last=day.day + timedelta(days=1),
                nights=row.nights + 1,
                km=row.km + day.km,
                cost=row.cost + day.cost,
            )
            continue
        if rows and key is None and current is None:
            row = rows[-1]
            rows[-1] = replace(row, last=day.day, km=row.km + day.km, cost=row.cost + day.cost)
            continue
        current = key
        if day.night is None:
            rows.append(PlaceRow(day.day, day.day, 0, end_place, day.km, day.cost))
        else:
            rows.append(PlaceRow(day.day, day.day + timedelta(days=1), 1, day.night.name, day.km, day.cost))
    return rows


def summarize(
    trips: Sequence[TourTrip],
    nights: Sequence[Night],
    refills: Sequence[TourRefill],
    costs: Sequence[TourCost],
    inputs: ConsumptionInputs,
    start: datetime,
    end: datetime,
    tz: tzinfo,
    *,
    end_place: str | None = None,
    odometer: tuple[float | None, float | None] = (None, None),
) -> TourSummary:
    """Return the key figures, the overview by day and place, the costs and the estimate of a tour."""
    first_day, last_day = start.astimezone(tz).date(), end.astimezone(tz).date()
    costs_in = [c for c in costs if first_day <= c.day <= last_day]
    paid = tour_costs(refills, costs_in, start, end, tz)
    distance = sum(trip.distance_km for trip in trips)
    days = day_rows(trips, nights, refills, costs_in, start, end, tz)
    ascents = [t.ascent_m for t in trips if t.ascent_m is not None]
    descents = [t.descent_m for t in trips if t.descent_m is not None]
    countries = dict.fromkeys(
        [
            *(c for trip in trips for c in trip.countries),
            *(r.country for r in refills if r.country and start <= r.time <= end),
            *(c.country for c in costs_in if c.country),
        ]
    )
    return TourSummary(
        start=start,
        end=end,
        distance_km=distance,
        moving_time=sum((trip.moving_time for trip in trips), timedelta()),
        ascent_m=sum(ascents) if ascents else None,
        descent_m=sum(descents) if descents else None,
        days=tuple(days),
        places=tuple(place_rows(days, nights, end_place)),
        nights=len(nights),
        costs=paid,
        estimate=estimate(distance, paid, inputs),
        countries=tuple(c for c in countries if c),
        odometer_start_km=odometer[0],
        odometer_end_km=odometer[1],
        ferry_km=sum(trip.ferry_km for trip in trips),
        ferry_time=sum((trip.ferry_time for trip in trips), timedelta()),
    )


def main_place(nights: Sequence[Night]) -> str | None:
    """Return the name of the place with the most nights, for the suggested title (6.2)."""
    counts: dict[str, int] = {}
    for night in nights:
        if night.name:
            counts[night.name] = counts.get(night.name, 0) + 1
    return max(counts, key=lambda name: counts[name]) if counts else None
