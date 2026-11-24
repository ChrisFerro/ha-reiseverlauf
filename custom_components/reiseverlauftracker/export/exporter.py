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

from PIL import Image

from .chart import BASE_WIDTH, render_profile
from .composite import render_composite
from .ferry import SplitTrack, ferry_spans, split_track
from .gpx import build_gpx
from .map import TileFetcher, draw_overlay, http_tile_fetcher, render_base_map
from .model import ExportOptions, FerryLeg, MapMarker, MapProjection, MarkerKind, StepSeries, TrackPoint
from .stats import TripStats, compute_stats, logbook_rows, stats_rows, stats_text, stop_lines
from .symbols import merge_markers, render_legend
from .texts import Texts, default_title, texts_for
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
    RAW = "raw"
    """Recorded points of the trip; written by the integration, not by `export_trip()`."""
    DAYS = "days"
    """One row per day of a tour (CSV); only tours have it."""


FILE_SUFFIXES: dict[ExportFile, str] = {
    ExportFile.COMPOSITE: "_gesamt.png",
    ExportFile.PROFILE: "_profil.png",
    ExportFile.STATS: "_statistik.txt",
    ExportFile.GPX: ".gpx",
    ExportFile.MAP: ".png",
    ExportFile.RAW: "_rohdaten.json",
    ExportFile.DAYS: "_tage.csv",
}
BASE_MAP_SUFFIX = "_karte_basis.png"
"""Map without symbols; kept so that symbols can be redrawn without tiles (Feat-12 6.5)."""


@dataclass(frozen=True, slots=True)
class ExportResult:
    """What an export produced."""

    title: str
    basename: str
    files: dict[ExportFile, Path]
    stats: TripStats
    stats_text: str
    base_map: Path | None = None
    projection: MapProjection | None = None


@dataclass(frozen=True, slots=True)
class BaseMapRef:
    """The stored base map of an export and where its coordinates lie."""

    name: str
    projection: MapProjection


@dataclass(frozen=True, slots=True)
class RefreshResult:
    """What renewing an export changed."""

    stats_text: str
    stats: TripStats
    files: dict[ExportFile, str]
    """All files of the export after renewing, by kind."""
    base_map: BaseMapRef | None
    map_redrawn: bool = False
    """The map was drawn anew with tiles (`redraw` asked for and the tiles loaded)."""


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
    split = split_track(track.points, options.stops)
    stats = compute_stats(track.points, track.speed, options, split)
    rows = stats_rows(stats, texts, tz)
    logbook = logbook_rows(options.logbook, texts, options.currency)
    text = _text(title, rows, options, texts)

    out_dir.mkdir(parents=True, exist_ok=True)
    files: dict[ExportFile, Path] = {}

    def path(kind: ExportFile) -> Path:
        files[kind] = out_dir / f"{basename}{FILE_SUFFIXES[kind]}"
        return files[kind]

    path(ExportFile.GPX).write_text(build_gpx(track.points, title), encoding="utf-8")
    path(ExportFile.STATS).write_text(text, encoding="utf-8")

    map_image = None
    base_path = projection = None
    markers = map_markers(track.points, options)
    if options.with_map:
        drawn = _render_map(out_dir, basename, split, markers, options, fetch_tile)
        if drawn is not None:
            map_image, base_ref = drawn
            base_path, projection = out_dir / base_ref.name, base_ref.projection
            map_image.save(path(ExportFile.MAP))

    window = (track.chart_start, track.chart_end)
    spans = ferry_spans(options.stops)
    profile = render_profile(track.points, track.chart_speed, window, texts, tz, scale, title, spans)
    if profile is not None:
        profile.save(path(ExportFile.PROFILE))
        profile.close()

    untitled_profile = render_profile(track.points, track.chart_speed, window, texts, tz, scale, ferries=spans)
    legend = legend_image(map_image, markers, split.legs, texts, scale)
    composite = render_composite([map_image, legend, untitled_profile], title, rows[0][1], rows[1:], scale, logbook)
    if composite is not None:
        composite.save(path(ExportFile.COMPOSITE))
        composite.close()
    for image in (map_image, legend, untitled_profile):
        if image is not None:
            image.close()

    return ExportResult(
        title=title,
        basename=basename,
        files=files,
        stats=stats,
        stats_text=text,
        base_map=base_path,
        projection=projection,
    )


def _render_map(
    out_dir: Path,
    basename: str,
    split: SplitTrack,
    markers: Sequence[MapMarker],
    options: ExportOptions,
    fetch_tile: TileFetcher | None,
    *,
    complete: bool = False,
) -> tuple[Image.Image, BaseMapRef] | None:
    """
    Load the tiles, store the base map and return the map with route and symbols drawn on it.

    Returns:
        The map and its stored base map, or None if the tiles cannot be loaded, with
        `complete` also if a single tile is missing.

    """
    scale = min(max(options.scale, MIN_SCALE), MAX_SCALE)
    width, height = options.map_size
    line_width = round(options.map_line_width * scale)
    base = render_base_map(
        split.land,
        (round(width * scale), round(height * scale)),
        line_width,
        fetch_tile or http_tile_fetcher(options.user_agent),
        markers,
        split.legs,
    )
    if base is None:
        return None
    if complete and base.missing_tiles:
        base.image.close()
        return None
    ref = BaseMapRef(f"{basename}{BASE_MAP_SUFFIX}", base.projection)
    base.image.save(out_dir / ref.name)
    map_image = draw_overlay(base.image, ref.projection, split.land, markers, split.legs, line_width)
    base.image.close()
    return map_image, ref


def map_markers(points: Sequence[TrackPoint], options: ExportOptions) -> list[MapMarker]:
    """
    Return the symbols of a trip map: the given ones, then start and end.

    The end shows a pitch when the arrival is on a camp site (Feat-12 5.7); a stop
    where fuel or gas was bought shows only the refill (5.4).
    """
    markers = merge_markers(options.markers, options.min_movement_m)
    if points:
        first, last = points[0], points[-1]
        end = MarkerKind.PITCH if options.arrival_stay else MarkerKind.END
        markers += [MapMarker(MarkerKind.START, first.lat, first.lon), MapMarker(end, last.lat, last.lon)]
    return markers


def _text(title: str, rows: list[tuple[str, str]], options: ExportOptions, texts: Texts) -> str:
    details = logbook_rows(options.logbook, texts, options.currency, travel_details=True)
    stay = [(texts.pitch, options.arrival_stay)] if options.arrival_stay else []
    return stats_text(title, rows + stay + details, stop_lines(options.stops, texts, options.timezone))


def legend_image(
    map_image: Image.Image | None,
    markers: Sequence[MapMarker],
    ferries: Sequence[FerryLeg],
    texts: Texts,
    scale: float,
) -> Image.Image | None:
    """Return the legend under the map, only for symbols on it (Feat-12 5.5)."""
    if map_image is None:
        return None
    kinds = {m.kind for m in markers} | ({MarkerKind.FERRY} if ferries else set())
    return render_legend(kinds, {MarkerKind(k): v for k, v in texts.markers.items()}, round(BASE_WIDTH * scale), scale)


def refresh_export(
    positions: Sequence[TrackPoint],
    speed: StepSeries | None,
    altitude: StepSeries | None,
    out_dir: Path,
    options: ExportOptions,
    files: dict[ExportFile, str],
    base_map: BaseMapRef | None = None,
    fetch_tile: TileFetcher | None = None,
    *,
    redraw: bool = False,
) -> RefreshResult:
    """
    Rewrite statistics, map symbols and composite image of an existing export, e.g. with new logbook figures.

    The title comes from `options.title`. With a stored `base_map`, the map gets its
    symbols drawn anew on it; otherwise the map file stays as it is. No tiles are
    downloaded then. With `redraw`, the map and its base map are drawn anew with
    tiles from `fetch_tile` (default: OpenStreetMap) instead, also for an export
    that had no map (Feat-12 6.8); if a tile cannot be loaded, the map stays and
    it goes on as without, so a good map is never replaced by one with gaps. Profile, GPX and raw data stay; other files missing from `files` are
    not created.

    Returns:
        The new statistics text, figures and files; distance and driving time change when a ferry was marked.

    Raises:
        NotEnoughPointsError: Fewer than two usable positions.
        NoMovementError: The vehicle never left the minimum movement radius.

    """
    texts = texts_for(options.language)
    tz = options.timezone
    scale = min(max(options.scale, MIN_SCALE), MAX_SCALE)
    title = options.title or ""
    track = prepare_track(positions, speed, altitude, options)
    split = split_track(track.points, options.stops)
    stats = compute_stats(track.points, track.speed, options, split)
    rows = stats_rows(stats, texts, tz)
    logbook = logbook_rows(options.logbook, texts, options.currency)
    text = _text(title, rows, options, texts)
    if (name := files.get(ExportFile.STATS)) is not None:
        (out_dir / name).write_text(text, encoding="utf-8")

    markers = map_markers(track.points, options)
    files = dict(files)
    map_image = None
    redrawn = False
    if redraw:
        drawn = _render_map(out_dir, _basename(files), split, markers, options, fetch_tile, complete=True)
        if drawn is not None:
            map_image, new_base = drawn
            if base_map is not None and base_map.name != new_base.name:
                (out_dir / base_map.name).unlink(missing_ok=True)
            base_map, redrawn = new_base, True
            map_name = files.setdefault(ExportFile.MAP, f"{_basename(files)}{FILE_SUFFIXES[ExportFile.MAP]}")
            map_image.save(out_dir / map_name)
    if not redrawn and (map_name := files.get(ExportFile.MAP)) is not None:
        map_image = _redraw_map(out_dir, base_map, split.land, markers, split.legs, options)
        if map_image is not None:
            map_image.save(out_dir / map_name)
        else:
            map_image = _open_image(out_dir / map_name)

    window = (track.chart_start, track.chart_end)
    spans = ferry_spans(options.stops)
    if (name := files.get(ExportFile.PROFILE)) is not None:
        # A ferry marked later changes the profile too.
        titled = render_profile(track.points, track.chart_speed, window, texts, tz, scale, title, spans)
        if titled is not None:
            titled.save(out_dir / name)
            titled.close()
    if (name := files.get(ExportFile.COMPOSITE)) is not None:
        profile = render_profile(track.points, track.chart_speed, window, texts, tz, scale, ferries=spans)
        legend = legend_image(map_image, markers, split.legs, texts, scale) if base_map is not None else None
        composite = render_composite([map_image, legend, profile], title, rows[0][1], rows[1:], scale, logbook)
        if composite is not None:
            composite.save(out_dir / name)
            composite.close()
        for image in (legend, profile):
            if image is not None:
                image.close()
    if map_image is not None:
        map_image.close()
    return RefreshResult(text, stats, files, base_map, map_redrawn=redrawn)


def _basename(files: dict[ExportFile, str]) -> str:
    """Return the common start of the export's file names, taken from the first file with a known suffix."""
    for kind in (ExportFile.STATS, ExportFile.GPX, ExportFile.COMPOSITE, ExportFile.PROFILE, ExportFile.RAW):
        name = files.get(kind)
        if name is not None and name.endswith(FILE_SUFFIXES[kind]):
            return name.removesuffix(FILE_SUFFIXES[kind])
    return "karte"


def _redraw_map(
    out_dir: Path,
    base_map: BaseMapRef | None,
    segments: Sequence[Sequence[TrackPoint]],
    markers: Sequence[MapMarker],
    ferries: Sequence[FerryLeg],
    options: ExportOptions,
) -> Image.Image | None:
    """Return the map with its symbols drawn on the stored base map, or None without a usable one."""
    if base_map is None:
        return None
    base = _open_image(out_dir / base_map.name)
    if base is None:
        return None
    # The line width the base map was drawn with, whatever the scale setting is now.
    line_width = round(options.map_line_width * base_map.projection.width / options.map_size[0])
    image = draw_overlay(base, base_map.projection, segments, markers, ferries, line_width)
    base.close()
    return image


def _open_image(path: Path) -> Image.Image | None:
    """Return the image at `path` loaded into memory, or None if it is missing or unreadable."""
    try:
        with Image.open(path) as image:
            image.load()
            return image.copy()
    except OSError:
        return None
