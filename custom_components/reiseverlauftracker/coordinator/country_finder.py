"""
Countries of exported trips, looked up in the background and stored in `export.json`.

New trips get them after their export; older exports when they are chosen in a
form (docs/features/feat-09-nachtraege.md 6.3). Nominatim is asked at most once
a second, and only when place names are switched on.
"""

import asyncio
from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.const import LOGGER

from . import export_runner
from .places import async_country
from .trip_countries import country_sample_points, ordered_countries

if TYPE_CHECKING:
    from .base import ReiseverlaufDataUpdateCoordinator
    from .exports import ExportInfo
    from .trip_log import TripLog


class CountryFinder:
    """Looks up and stores the countries of exports."""

    def __init__(self, coordinator: ReiseverlaufDataUpdateCoordinator) -> None:
        """Remember the coordinator; nothing has been looked up yet."""
        self.coordinator = coordinator
        self._tried: set[str] = set()

    def expect(self, folder: str) -> None:
        """Note that the countries of `folder` are about to be looked up, so `ensure` does not ask twice."""
        self._tried.add(folder)

    def ensure(self, info: ExportInfo) -> None:
        """Start looking up the countries of an export that has none yet, once per export and run."""
        coordinator = self.coordinator
        if info.countries is not None or info.folder in self._tried or not coordinator.settings.place_names:
            return
        self._tried.add(info.folder)
        coordinator.config_entry.async_create_background_task(
            coordinator.hass, self._async_find_for(info), "reiseverlauftracker trip countries"
        )

    async def _async_find_for(self, info: ExportInfo) -> None:
        if (log := await self.coordinator.async_raw_log(info)) is not None:
            await self.async_find(info.folder, log)

    async def async_find(self, folder: str, log: TripLog) -> tuple[str, ...] | None:
        """
        Look up the countries along `log` and store them in the export in `folder`.

        Returns:
            The countries, or None when no lookup succeeded (they are tried again on the next run).

        """
        coordinator = self.coordinator
        points = country_sample_points(log)
        codes: list[str | None] = []
        for index, point in enumerate(points):
            if index:
                await asyncio.sleep(export_runner.NOMINATIM_INTERVAL_S)
            codes.append(await async_country(coordinator.hass, coordinator.settings, point.lat, point.lon))
        countries = ordered_countries(codes)
        if points and not countries:
            LOGGER.debug("No country found for the export %s", folder)
            return None
        await coordinator.async_store_countries(folder, countries)
        return countries
