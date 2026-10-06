"""
Run a complete export and write its files.

Everything here blocks (rendering takes over 100 MB at scale 2, tiles are
downloaded synchronously), so callers run it in an executor.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import re
import unicodedata

from .chart import render_profile
from .composite import render_composite
from .gpx import build_gpx
from .map import TileFetcher, http_tile_fetcher, render_map
from .model import ExportOptions, StepSeries, TrackPoint
from .stats import TripStats, compute_stats, stats_rows, stats_text
from .texts import default_title, texts_for
from .track import prepare_track

MIN_SCALE = 0.5
MAX_SCALE = 4.0
TRANSLITERATION = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"}  # codespell:ignore ue
)


class ExportFile(StrEnum):
    """Kinds of files one export produces."""

    COMPOSITE = "composite"
    MAP = "map"
    PROFILE = "profile"
    GPX = "gpx"
    STATS = "stats"


FILE_SUFFIXES: dict[ExportFile, str] = {
    ExportFile.COMPOSITE: "_gesamt.png",
    ExportFile.PROFILE: "_profil.png",
    ExportFile.STATS: "_statistik.txt",
    ExportFile.GPX: ".gpx",
    ExportFile.MAP: ".png",
}


@dataclass(frozen=True, slots=True)
class ExportResult:
    """What an export produced."""

    title: str
    basename: str
    files: dict[ExportFile, Path]
    stats: TripStats
    stats_text: str


def slugify(text: str) -> str:
    """Return a file-name-safe ASCII slug; German umlauts are transliterated (ä becomes ae)."""
    ascii_text = (
        unicodedata.normalize("NFKD", text.translate(TRANSLITERATION)).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")


def export_trip(
    positions: Sequence[TrackPoint],
    speed: StepSeries | None,
    altitude: StepSeries | None,
    out_dir: Path,
    options: ExportOptions,
    fetch_tile: TileFetcher | None = None,
) -> ExportResult:
    """
    Export a trip as GPX, statistics, map, profile and composite image.

    A map that cannot be rendered is left out instead of failing the export.

    Raises:
        NotEnoughPointsError: Fewer than two usable positions.
        NoMovementError: The vehicle never left the minimum movement radius.

    """
    texts = texts_for(options.language)
    tz = options.timezone
    scale = min(max(options.scale, MIN_SCALE), MAX_SCALE)
    track = prepare_track(positions, speed, altitude, options)
    title = options.title or default_title(texts, track.departure, track.arrival, tz)
    basename = (
        slugify(options.title)
        if options.title and slugify(options.title)
        else f"track_{track.departure.astimezone(tz):%Y%m%d}_{track.arrival.astimezone(tz):%Y%m%d}"
    )
    stats = compute_stats(track.points, track.speed, options)
    rows = stats_rows(stats, texts, tz)
    text = stats_text(title, rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    files: dict[ExportFile, Path] = {}

    def path(kind: ExportFile) -> Path:
        files[kind] = out_dir / f"{basename}{FILE_SUFFIXES[kind]}"
        return files[kind]

    path(ExportFile.GPX).write_text(build_gpx(track.points, title), encoding="utf-8")
    path(ExportFile.STATS).write_text(text, encoding="utf-8")

    map_image = None
    if options.with_map:
        width, height = options.map_size
        map_image = render_map(
            track.points,
            (round(width * scale), round(height * scale)),
            round(options.map_line_width * scale),
            fetch_tile or http_tile_fetcher(options.user_agent),
        )
        if map_image is not None:
            map_image.save(path(ExportFile.MAP))

    window = (track.chart_start, track.chart_end)
    profile = render_profile(track.points, track.chart_speed, window, texts, tz, scale, title)
    if profile is not None:
        profile.save(path(ExportFile.PROFILE))
        profile.close()

    untitled_profile = render_profile(track.points, track.chart_speed, window, texts, tz, scale)
    composite = render_composite([map_image, untitled_profile], title, rows[0][1], rows[1:], scale)
    if composite is not None:
        composite.save(path(ExportFile.COMPOSITE))
        composite.close()
    for image in (map_image, untitled_profile):
        if image is not None:
            image.close()

    return ExportResult(title=title, basename=basename, files=files, stats=stats, stats_text=text)
