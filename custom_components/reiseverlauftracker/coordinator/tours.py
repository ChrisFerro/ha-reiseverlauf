"""
Tours: several trips and the stays between them, created afterwards (docs/features/feat-10-tour.md 6.2 to 6.5).

A tour reads the raw data of its trips, not the recorder, and keeps a copy of them in
its own raw data (5.8): renewing it after a logbook change, a new title or a renamed
night place needs no trip any more. A changed period reads only the trips it does not
have yet. Each new version fires `reiseverlauftracker_tour`.
"""

import asyncio
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from custom_components.reiseverlauftracker.const import DOMAIN, EVENT_TOUR, LOGGER
from custom_components.reiseverlauftracker.export import (
    ExportFile,
    ExportOptions,
    NoMovementError,
    NotEnoughPointsError,
)
from custom_components.reiseverlauftracker.export.stats import compute_stats
from custom_components.reiseverlauftracker.export.tour import (
    ConsumptionInputs,
    Night,
    TourCost,
    TourRefill,
    TourTrip,
    gas_used_percent,
    locate_nights,
    name_group,
    night_groups,
    rename_nights,
    summarize,
    unnamed_groups,
)
from custom_components.reiseverlauftracker.export.tour_export import export_tour, tour_title
from custom_components.reiseverlauftracker.export.track import prepare_track
from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.loader import async_get_loaded_integration
from homeassistant.util import dt as dt_util

from . import export_runner
from .export_runner import media_base, media_url, options_for
from .exports import ExportInfo, ExportKind, TourMeta, existing_files, read_raw, write_metadata
from .places import async_country, async_place_name, async_stay_name, user_agent
from .trip_log import RunningStatsSettings, TripLog

if TYPE_CHECKING:
    from .base import ReiseverlaufDataUpdateCoordinator

RAW_VERSION = 1
REFRESH_DELAY = timedelta(seconds=30)
OCCASION_CREATED = "erstellt"
OCCASION_UPDATED = "aktualisiert"


class TourError(Exception):
    """A tour cannot be made; `key` is the translation key of the reason."""

    def __init__(self, key: str, **placeholders: str) -> None:
        """Remember the reason and its placeholders."""
        super().__init__(key)
        self.key = key
        self.placeholders = placeholders


@dataclass(frozen=True, slots=True)
class RawTrip:
    """A trip as a tour keeps it in its raw data: the trip's metadata and its recorded log."""

    folder: str
    title: str
    start: datetime
    end: datetime
    log: dict[str, Any]
    countries: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return the trip as stored in the raw data of the tour."""
        return {
            "folder": self.folder,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "countries": list(self.countries),
            "log": self.log,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RawTrip:
        """Rebuild a trip from `as_dict()` output."""
        return cls(
            folder=data["folder"],
            title=data["title"],
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]),
            log=data["log"],
            countries=tuple(data.get("countries") or ()),
        )


@dataclass(frozen=True, slots=True)
class _Request:
    """What a new version of a tour is built from."""

    folder: str
    start: datetime
    end: datetime
    title: str | None
    scale: float | None
    previous: ExportInfo | None = None
    names: dict[date, str] | None = None


class Tours:
    """Creates, changes and renews the tours of one config entry."""

    def __init__(self, coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
        """Start without pending renewals."""
        self.coordinator = coordinator
        self._pending: set[str] = set()
        self._unsub: CALLBACK_TYPE | None = None
        self._lock = asyncio.Lock()

    def all(self) -> list[ExportInfo]:
        """Return the tours, newest first."""
        return [info for info in self.coordinator.exports if info.is_tour]

    async def async_create(
        self, start: datetime, end: datetime, title: str | None = None, scale: float | None = None
    ) -> ExportInfo:
        """
        Create a tour of all trips that start from `start` to `end`.

        Returns:
            The new tour.

        Raises:
            TourError: No trip in the period, a trip without raw data, or no movement.
            OSError: The output folder cannot be written.

        """
        if end <= start:
            raise TourError("invalid_period")
        tz = dt_util.get_default_time_zone()
        base = media_base(self.coordinator.hass, self.coordinator.settings)
        stem = f"tour-{start.astimezone(tz):%Y-%m-%d}-{end.astimezone(tz):%Y-%m-%d}"
        taken = {info.folder for info in self.coordinator.exports}
        folder = stem
        number = 2
        while folder in taken or await self.coordinator.hass.async_add_executor_job((base / folder).exists):
            folder, number = f"{stem}-{number}", number + 1
        info = await self._async_build(_Request(folder, start, end, title or None, scale))
        self._fire(info, OCCASION_CREATED)
        return info

    async def async_change(
        self,
        info: ExportInfo,
        *,
        title: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        names: dict[date, str] | None = None,
    ) -> ExportInfo:
        """
        Change title, period or night place names of a tour and create it anew.

        An empty title returns to the suggested one.

        Returns:
            The new version of the tour.

        Raises:
            TourError: Not a tour, a bad period, or a new trip without raw data.
            OSError: The output folder cannot be written.

        """
        if not info.is_tour or info.tour is None:
            raise TourError("not_a_tour", export=info.title)
        start, end = start or info.start, end or info.end
        if end <= start:
            raise TourError("invalid_period")
        if title is None:
            title = info.title if info.tour.title_given else None
        changed = await self._async_build(
            _Request(info.folder, start, end, title or None, info.tour.scale, previous=info, names=names)
        )
        self._fire(changed, OCCASION_UPDATED)
        return changed

    def schedule(self, moment: datetime | date) -> None:
        """Renew every tour whose period holds `moment` (a time, or a day) once the changes have settled."""
        tz = dt_util.get_default_time_zone()
        for info in self.all():
            if isinstance(moment, datetime):
                inside = info.start <= moment <= info.end
            else:
                inside = info.start.astimezone(tz).date() <= moment <= info.end.astimezone(tz).date()
            if inside:
                self._pending.add(info.folder)
        if self._pending and self._unsub is None:
            self._unsub = async_call_later(self.coordinator.hass, REFRESH_DELAY, self._on_delay)

    def cancel(self) -> None:
        """Forget pending renewals, e.g. on unload."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        self._pending.clear()

    @callback
    def _on_delay(self, _now: datetime) -> None:
        self._unsub = None
        folders, self._pending = sorted(self._pending), set()
        coordinator = self.coordinator
        coordinator.config_entry.async_create_background_task(
            coordinator.hass, self._async_refresh_all(folders), "reiseverlauftracker tour refresh"
        )

    async def _async_refresh_all(self, folders: list[str]) -> None:
        for folder in folders:
            await self.async_refresh(folder)

    async def async_refresh(self, folder: str) -> ExportInfo | None:
        """
        Create a tour anew with the current logbook and costs, e.g. after toll was entered.

        Returns:
            The new version, or None if the tour is gone or cannot be made any more.

        """
        info = next((i for i in self.all() if i.folder == folder), None)
        if info is None or info.tour is None:
            return None
        try:
            changed = await self._async_build(
                _Request(
                    info.folder,
                    info.start,
                    info.end,
                    info.title if info.tour.title_given else None,
                    info.tour.scale,
                    previous=info,
                )
            )
        except (TourError, OSError) as err:
            LOGGER.warning("Tour %s could not be renewed: %s", folder, err)
            return None
        self._fire(changed, OCCASION_UPDATED)
        return changed

    async def _async_build(self, request: _Request) -> ExportInfo:
        async with self._lock:
            return await self._async_build_locked(request)

    async def _async_build_locked(self, request: _Request) -> ExportInfo:
        coordinator = self.coordinator
        hass, settings = coordinator.hass, coordinator.settings
        base = media_base(hass, settings)
        tz = dt_util.get_default_time_zone()
        previous = request.previous
        meta = previous.tour if previous is not None else None

        raw_trips = await self._async_raw_trips(request.start, request.end, previous)
        log_settings = coordinator.log_settings()
        version = async_get_loaded_integration(hass, DOMAIN).version
        scale = request.scale if request.scale is not None else settings.scale
        options = replace(
            options_for(hass, settings, request.title or "", user_agent(str(version) if version else None), (), None),
            scale=scale,
        )
        trips = await hass.async_add_executor_job(_prepare_trips, raw_trips, log_settings, options)
        if not trips:
            raise TourError("no_movement")

        nights = locate_nights(trips, request.start, request.end, tz, meta.nights if meta else ())
        if request.names:
            nights = rename_nights(nights, request.names)
        nights = await self._async_name_nights(nights)
        end_place = await self._async_end_place(trips, meta, previous)

        refills, refill_countries = await self._async_refills(request.start, request.end, meta)
        costs = self._costs(request.start, request.end)
        inputs = self._consumption_inputs(request.start, request.end, refills)
        odometer = self._odometer(raw_trips)
        summary = summarize(
            trips,
            nights,
            refills,
            costs,
            inputs,
            request.start,
            request.end,
            tz,
            end_place=end_place,
            odometer=odometer,
        )
        title = request.title or tour_title(hass.config.language, summary, nights, tz)
        same_trips = meta is not None and meta.trips == tuple(t.folder for t in raw_trips)
        raw = {
            "version": RAW_VERSION,
            "art": ExportKind.TOUR.value,
            "start": request.start.isoformat(),
            "end": request.end.isoformat(),
            "trips": [trip.as_dict() for trip in raw_trips],
            "nights": [night.as_dict() for night in nights],
            "end_place": end_place,
        }
        tour_meta = TourMeta(
            trips=tuple(t.folder for t in raw_trips),
            nights=tuple(nights),
            end_place=end_place,
            refill_countries=refill_countries,
            title_given=request.title is not None,
            scale=request.scale,
            costs=summary.costs.as_dict(),
            estimate=summary.estimate.as_dict() if summary.estimate else None,
        )
        async with coordinator.export_lock:
            info = await hass.async_add_executor_job(
                _write,
                base,
                request.folder,
                previous,
                summary,
                trips,
                nights,
                title,
                replace(options, title=title),
                raw,
                same_trips,
                tour_meta,
                dt_util.utcnow() if previous is not None else None,
            )
        await coordinator.async_refresh_exports()
        return info

    async def _async_raw_trips(self, start: datetime, end: datetime, previous: ExportInfo | None) -> list[RawTrip]:
        """
        Return the trips starting in the period: the tour's own copy if it has one, else the trip's raw data.

        Raises:
            TourError: No trip in the period, or one that has neither raw data nor a copy in the tour.

        """
        coordinator = self.coordinator
        base = media_base(coordinator.hass, coordinator.settings)
        known: dict[datetime, RawTrip] = {}
        if previous is not None and (stored := await coordinator.hass.async_add_executor_job(read_raw, base, previous)):
            try:
                known = {trip.start: trip for trip in map(RawTrip.from_dict, stored.get("trips", []))}
            except KeyError, ValueError, TypeError:
                LOGGER.warning("Raw data of the tour %s are unreadable, the trips are read again", previous.folder)
        trips = {start_: trip for start_, trip in known.items() if start <= start_ <= end}
        missing: list[str] = []
        tz = dt_util.get_default_time_zone()
        for info in coordinator.exports:
            if not info.automatic or info.is_tour or not start <= info.start <= end or info.start in trips:
                continue
            raw = await coordinator.hass.async_add_executor_job(read_raw, base, info)
            if raw is None:
                missing.append(info.label(tz))
                continue
            trips[info.start] = RawTrip(info.folder, info.title, info.start, info.end, raw, info.countries or ())
        if missing:
            raise TourError("tour_raw_missing", trips=", ".join(sorted(missing)))
        if not trips:
            raise TourError("tour_no_trips")
        return [trips[key] for key in sorted(trips)]

    async def _async_name_nights(self, nights: list[Night]) -> list[Night]:
        """Look up the camp site or place of every run of nights without a name, one request a second."""
        coordinator = self.coordinator
        if not coordinator.settings.place_names:
            return nights
        for group in unnamed_groups(nights):
            await asyncio.sleep(export_runner.NOMINATIM_INTERVAL_S)
            name = await async_stay_name(coordinator.hass, coordinator.settings, group[0].lat, group[0].lon)
            if name:
                nights = name_group(nights, group, name)
        return nights

    async def _async_end_place(
        self, trips: list[TourTrip], meta: TourMeta | None, previous: ExportInfo | None
    ) -> str | None:
        """Return the place where the last trip ended; an earlier version of the tour already knows it."""
        last = trips[-1].points[-1]
        if meta is not None and previous is not None and meta.trips and meta.trips[-1] == trips[-1].folder:
            return meta.end_place
        if not self.coordinator.settings.place_names:
            return None
        await asyncio.sleep(export_runner.NOMINATIM_INTERVAL_S)
        return await async_place_name(self.coordinator.hass, self.coordinator.settings, last.lat, last.lon)

    async def _async_refills(
        self, start: datetime, end: datetime, meta: TourMeta | None
    ) -> tuple[list[TourRefill], dict[str, str]]:
        """Return the refills of the period with their countries; new countries are looked up once."""
        coordinator = self.coordinator
        countries = dict(meta.refill_countries) if meta else {}
        refills: list[TourRefill] = []
        for entry in coordinator.logbook.logbook.entries:
            if not start <= entry.time <= end or (entry.fuel is None and entry.gas is None):
                continue
            if entry.id not in countries and entry.lat is not None and entry.lon is not None:
                if coordinator.settings.place_names:
                    await asyncio.sleep(export_runner.NOMINATIM_INTERVAL_S)
                    if code := await async_country(coordinator.hass, coordinator.settings, entry.lat, entry.lon):
                        countries[entry.id] = code
            refills.append(
                TourRefill(
                    time=entry.time,
                    fuel_litres=entry.fuel.litres if entry.fuel else 0.0,
                    fuel_amount=(entry.fuel.amount or 0.0) if entry.fuel else 0.0,
                    gas_litres=entry.gas.litres if entry.gas else 0.0,
                    gas_amount=(entry.gas.amount or 0.0) if entry.gas else 0.0,
                    country=countries.get(entry.id),
                )
            )
        return refills, countries

    def _costs(self, start: datetime, end: datetime) -> list[TourCost]:
        """Return the travel costs whose day lies in the period (5.4)."""
        tz = dt_util.get_default_time_zone()
        first, last = start.astimezone(tz).date(), end.astimezone(tz).date()
        return [
            TourCost(cost.day, cost.category.value, cost.amount, cost.country)
            for cost in self.coordinator.logbook.logbook.travel_costs
            if first <= cost.day <= last
        ]

    def _consumption_inputs(self, start: datetime, end: datetime, refills: list[TourRefill]) -> ConsumptionInputs:
        """Return what the logbook knows for the estimated consumption of the period (5.5)."""
        book = self.coordinator.logbook.logbook
        litres_per_percent = book.gas_litres_per_percent()
        refilled = sum(r.gas_litres for r in refills if start < r.time <= end)
        return ConsumptionInputs(
            consumption_l_100km=book.average_consumption(until=end),
            fuel_price=book.last_price("fuel", end),
            gas_used_percent=gas_used_percent(
                book.gas_level_at(start), book.gas_level_at(end), refilled, litres_per_percent
            ),
            gas_litres_per_percent=litres_per_percent,
            gas_price=book.last_price("gas", end),
        )

    def _odometer(self, trips: list[RawTrip]) -> tuple[float | None, float | None]:
        """Return the odometer at the start of the first and the end of the last trip, as their exports know it."""
        exports = {info.folder: info for info in self.coordinator.exports}
        first, last = exports.get(trips[0].folder), exports.get(trips[-1].folder)
        start = first.logbook.odometer_start_km if first and first.logbook else None
        if start is None and (counters := trips[0].log.get("counter_start")):
            start = self.coordinator.logbook.logbook.suggest_odometer(counters["distance_m"], until=trips[0].start)
        end = last.logbook.odometer_end_km if last and last.logbook else None
        return start, end

    def _fire(self, info: ExportInfo, occasion: str) -> None:
        coordinator = self.coordinator
        coordinator.hass.bus.async_fire(
            EVENT_TOUR,
            {"entry_id": coordinator.config_entry.entry_id, **event_data(coordinator, info, occasion)},
        )


def event_data(coordinator: ReiseverlaufDataUpdateCoordinator, info: ExportInfo, occasion: str) -> dict[str, Any]:
    """Return the payload of the tour event, also the response of the tour actions."""
    settings = coordinator.settings
    base = media_base(coordinator.hass, settings)
    composite = info.files.get(ExportFile.COMPOSITE)
    tz = dt_util.get_default_time_zone()
    meta = info.tour or TourMeta()
    return {
        "anlass": occasion,
        "titel": info.title,
        "start": info.start.isoformat(),
        "ende": info.end.isoformat(),
        "tage": (info.end.astimezone(tz).date() - info.start.astimezone(tz).date()).days + 1,
        "naechte": len(meta.nights),
        "strecke_km": round(info.distance_km, 1),
        "fahrzeit_min": round(info.driving_time.total_seconds() / 60),
        "kosten": round(meta.total_cost, 2),
        "kostenaufstellung": meta.costs,
        "verbrauch": meta.estimate,
        "reisen": list(meta.trips),
        "ordner": info.folder,
        "dateien": [
            {"typ": kind.value, "name": name, "url": media_url(settings, info.folder, name)}
            for kind, name in info.files.items()
        ],
        "statistik": info.stats_text,
        "gesamtbild": str(base / info.folder / composite) if composite else None,
        "gesamtbild_url": media_url(settings, info.folder, composite) if composite else None,
    }


def nights_data(info: ExportInfo) -> list[dict[str, Any]]:
    """Return the night places of a tour by run, as the export selection lists them for renaming."""
    nights = info.tour.nights if info.tour else ()
    return [
        {
            "nacht": group[0].night.isoformat(),
            "bis": (group[-1].night + timedelta(days=1)).isoformat(),
            "naechte": len(group),
            "name": group[0].name,
            "geaendert": group[0].name_changed,
        }
        for group in night_groups(nights)
    ]


def _prepare_trips(raw_trips: list[RawTrip], settings: RunningStatsSettings, options: ExportOptions) -> list[TourTrip]:
    """Turn the raw data of the trips into prepared tracks with their key figures; trips without movement drop out."""
    trips: list[TourTrip] = []
    for raw in raw_trips:
        try:
            log = TripLog.from_dict(raw.log, settings)
        except KeyError, ValueError, TypeError:
            LOGGER.warning("Raw data of the trip %s are unreadable and left out of the tour", raw.folder)
            continue
        positions, speed, altitude = log.export_inputs()
        try:
            track = prepare_track([p for p in positions if p.time <= raw.end], speed, altitude, options)
        except NotEnoughPointsError, NoMovementError:
            continue
        stats = compute_stats(track.points, track.speed, options)
        trips.append(
            TourTrip(
                folder=raw.folder,
                title=raw.title,
                start=raw.start,
                end=raw.end,
                points=tuple(track.points),
                distance_km=stats.distance_km,
                moving_time=stats.moving_time,
                ascent_m=stats.ascent_m,
                descent_m=stats.descent_m,
                countries=raw.countries,
            )
        )
    return trips


def _write(
    base: Path,
    folder: str,
    previous: ExportInfo | None,
    summary: Any,
    trips: list[TourTrip],
    nights: list[Night],
    title: str,
    options: ExportOptions,
    raw: dict[str, Any],
    reuse_map: bool,
    meta: TourMeta,
    updated: datetime | None,
) -> ExportInfo:
    """Write the files and `export.json` of a tour; blocking."""
    previous_files = existing_files(base, previous) if previous is not None else {}
    result = export_tour(
        summary,
        trips,
        nights,
        title,
        base / folder,
        options,
        previous=previous_files,
        raw=raw,
        reuse_map=reuse_map,
    )
    info = ExportInfo(
        folder=folder,
        title=result.title,
        start=summary.start,
        end=summary.end,
        distance_km=summary.distance_km,
        driving_time=summary.moving_time,
        files=result.files,
        stats_text=result.stats_text,
        automatic=False,
        countries=summary.countries,
        updated=updated,
        kind=ExportKind.TOUR,
        tour=meta,
    )
    write_metadata(base, info)
    return info
