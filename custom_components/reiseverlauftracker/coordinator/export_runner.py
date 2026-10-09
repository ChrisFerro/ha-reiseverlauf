"""Run an export of recorded trip data into its own folder below the media directory."""

import asyncio
from datetime import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from custom_components.reiseverlauftracker.const import TITLE_FORMAT_DATE
from custom_components.reiseverlauftracker.export import (
    FILE_SUFFIXES,
    ExportFile,
    ExportOptions,
    StepSeries,
    TrackPoint,
    export_trip,
)
from custom_components.reiseverlauftracker.export.texts import texts_for
from custom_components.reiseverlauftracker.utils.geocode import async_reverse_geocode
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .exports import ExportInfo, remove_files, write_metadata
from .title import trip_title

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.settings import ReiseverlaufSettings
    from homeassistant.core import HomeAssistant

MEDIA_SOURCE_DIR = "local"
NOMINATIM_INTERVAL_S = 1.1
PROJECT_URL = "https://github.com/ChrisFerro/ha-reiseverlauf"


def media_base(hass: HomeAssistant, settings: ReiseverlaufSettings) -> Path:
    """Return the absolute output folder inside the local media directory."""
    return Path(hass.config.media_dirs.get(MEDIA_SOURCE_DIR, hass.config.path("media"))) / settings.output_dir


def media_url(settings: ReiseverlaufSettings, folder: str, name: str) -> str:
    """Return the authenticated media URL of an export file, as the companion app expects it."""
    return f"/media/{MEDIA_SOURCE_DIR}/{settings.output_dir}/{folder}/{name}"


def user_agent(version: str | None) -> str:
    """Return the User-Agent sent to OpenStreetMap services."""
    return f"reiseverlauftracker/{version or 'dev'} (+{PROJECT_URL})"


async def async_export(
    hass: HomeAssistant,
    settings: ReiseverlaufSettings,
    data: tuple[list[TrackPoint], StepSeries | None, StepSeries | None],
    start: datetime,
    end: datetime,
    *,
    version: str | None,
    raw: dict[str, Any] | None = None,
    title: str | None = None,
    automatic: bool = True,
    folder: str | None = None,
) -> ExportInfo:
    """
    Export one trip; an earlier export in the same folder is replaced.

    Without `title`, the title follows the configured format and place names.
    Without `folder`, the folder is named after the local start time.

    Raises:
        NotEnoughPointsError: Fewer than two usable positions.
        NoMovementError: The vehicle never left the minimum movement radius.
        OSError: The output folder cannot be written.

    """
    positions = data[0]
    tz = dt_util.get_default_time_zone()
    agent = user_agent(version)
    if title is None:
        start_place, end_place = await _async_places(hass, settings, positions, agent)
        texts = texts_for(hass.config.language)
        title = trip_title(settings.title_format, texts, start, end, tz, start_place, end_place)
    options = ExportOptions(
        title=title,
        scale=settings.scale,
        margin=settings.margin,
        language=hass.config.language,
        timezone=tz,
        standstill_kmh=settings.standstill_kmh,
        max_accuracy_m=settings.max_accuracy_m,
        min_point_distance_m=settings.min_point_distance_m,
        min_movement_m=settings.min_movement_m,
        elevation_hysteresis_m=settings.elevation_hysteresis_m,
        user_agent=agent,
    )
    folder = folder or f"{start.astimezone(tz):%Y-%m-%d_%H%M}"
    return await hass.async_add_executor_job(
        _export_sync, media_base(hass, settings), folder, data, options, raw, start, end, automatic
    )


def event_data(settings: ReiseverlaufSettings, info: ExportInfo, base: Path) -> dict[str, Any]:
    """Return the payload of the "ended" and "exported" events."""
    composite = info.files.get(ExportFile.COMPOSITE)
    return {
        "titel": info.title,  # codespell:ignore titel
        "start": info.start.isoformat(),
        "ende": info.end.isoformat(),  # codespell:ignore ende
        "strecke_km": round(info.distance_km, 1),
        "fahrzeit_min": round(info.driving_time.total_seconds() / 60),
        "ordner": info.folder,  # codespell:ignore ordner
        "dateien": [
            {"typ": kind.value, "name": name, "url": media_url(settings, info.folder, name)}
            for kind, name in info.files.items()
        ],
        "statistik": info.stats_text,
        "gesamtbild": str(base / info.folder / composite) if composite else None,
        "gesamtbild_url": media_url(settings, info.folder, composite) if composite else None,
    }


async def _async_places(
    hass: HomeAssistant,
    settings: ReiseverlaufSettings,
    positions: list[TrackPoint],
    agent: str,
) -> tuple[str | None, str | None]:
    usable = [p for p in positions if p.accuracy is None or p.accuracy <= settings.max_accuracy_m]
    if not settings.place_names or settings.title_format == TITLE_FORMAT_DATE or not usable:
        return None, None
    session = async_get_clientsession(hass)
    first, last = usable[0], usable[-1]
    start_place = await async_reverse_geocode(session, first.lat, first.lon, hass.config.language, agent)
    await asyncio.sleep(NOMINATIM_INTERVAL_S)
    end_place = await async_reverse_geocode(session, last.lat, last.lon, hass.config.language, agent)
    return start_place, end_place


def _export_sync(
    base: Path,
    folder: str,
    data: tuple[list[TrackPoint], StepSeries | None, StepSeries | None],
    options: ExportOptions,
    raw: dict[str, Any] | None,
    start: datetime,
    end: datetime,
    automatic: bool,
) -> ExportInfo:
    remove_files(base, folder, set(ExportFile))
    path = base / folder
    result = export_trip(*data, path, options)
    files = {kind: file.name for kind, file in result.files.items()}
    if raw is not None:
        raw_name = f"{result.basename}{FILE_SUFFIXES[ExportFile.RAW]}"
        (path / raw_name).write_text(json.dumps(raw), encoding="utf-8")
        files[ExportFile.RAW] = raw_name
    info = ExportInfo(
        folder=folder,
        title=result.title,
        start=start,
        end=end,
        distance_km=result.stats.distance_km,
        driving_time=result.stats.moving_time,
        files=files,
        stats_text=result.stats_text,
        automatic=automatic,
    )
    write_metadata(base, info)
    return info
