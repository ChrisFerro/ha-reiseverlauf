"""Tests for a complete export run."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from PIL import Image
import pytest

from custom_components.reiseverlauftracker.export import (
    BaseMapRef,
    ExportFile,
    ExportOptions,
    LogbookFigures,
    MapMarker,
    MarkerKind,
    NoMovementError,
    StepSeries,
    TrackPoint,
    export_trip,
    refresh_export,
    slugify,
)
from custom_components.reiseverlauftracker.export.exporter import map_markers
from custom_components.reiseverlauftracker.export.symbols import COLORS

pytestmark = pytest.mark.unit

START = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
DEPARTURE = START + timedelta(minutes=15)
ARRIVAL = START + timedelta(minutes=55)


def minutes(n: float) -> datetime:
    return START + timedelta(minutes=n)


def north(metres: float) -> tuple[float, float]:
    return 47.0 + metres / 111195.0, 11.0


@pytest.mark.parametrize(
    ("title", "slug"),
    [
        ("Dolomiten-Tour 2026", "dolomiten_tour_2026"),
        ("Über den Großglockner", "ueber_den_grossglockner"),
        ("Côte d'Azur", "cote_d_azur"),
        ("Fehmarn – Rødby", "fehmarn_roedby"),
        ("Ærø und Åbenrå", "aeroe_und_aabenraa"),
        ("../../etc", "etc"),
        ("???", ""),
    ],
)
def test_slugify(title: str, slug: str) -> None:
    assert slugify(title) == slug


def test_full_export_writes_all_files(
    positions: list[TrackPoint],
    speed: StepSeries,
    altitude: StepSeries,
    tmp_path: Path,
    offline_fetcher: Callable[[str], bytes],
) -> None:
    options = ExportOptions(title="Über den Pass", timezone=ZoneInfo("Europe/Berlin"), map_size=(1200, 800))
    result = export_trip(positions, speed, altitude, tmp_path, options, offline_fetcher)

    assert result.title == "Über den Pass"
    assert result.basename == "ueber_den_pass"
    assert {kind: path.name for kind, path in result.files.items()} == {
        ExportFile.GPX: "ueber_den_pass.gpx",
        ExportFile.STATS: "ueber_den_pass_statistik.txt",
        ExportFile.MAP: "ueber_den_pass.png",
        ExportFile.PROFILE: "ueber_den_pass_profil.png",
        ExportFile.COMPOSITE: "ueber_den_pass_gesamt.png",
    }
    assert all(path.is_file() for path in result.files.values())
    assert (tmp_path / "ueber_den_pass_statistik.txt").read_text(encoding="utf-8") == result.stats_text
    assert "Strecke:         30,0 km" in result.stats_text
    with Image.open(result.files[ExportFile.COMPOSITE]) as composite:
        assert composite.width == 2400
        # Header, map, legend (start and end), profile; each part with its gap.
        assert composite.height == 380 + (1600 + 40) + (80 + 40) + (1800 + 40)
    # The base map is kept beside the files, but it is not one of them.
    assert result.base_map == tmp_path / "ueber_den_pass_karte_basis.png"
    assert result.base_map.is_file()
    assert result.projection is not None
    assert (result.projection.width, result.projection.height) == (1200, 800)


def test_export_without_title_or_map(
    positions: list[TrackPoint], speed: StepSeries, altitude: StepSeries, tmp_path: Path
) -> None:
    options = ExportOptions(language="en", with_map=False, scale=0.5)
    result = export_trip(positions, speed, altitude, tmp_path / "new", options)

    assert result.title == "Motorhome 2026-10-01"
    assert result.basename == "track_20261001_20261001"
    assert ExportFile.MAP not in result.files
    assert set(result.files) == {ExportFile.GPX, ExportFile.STATS, ExportFile.PROFILE, ExportFile.COMPOSITE}
    with Image.open(result.files[ExportFile.PROFILE]) as profile:
        assert profile.size == (1200, 900)


def test_export_continues_when_map_fails(
    positions: list[TrackPoint], speed: StepSeries, altitude: StepSeries, tmp_path: Path
) -> None:
    options = ExportOptions(map_size=(800, 600))
    with patch(
        "custom_components.reiseverlauftracker.export.map.StaticMap.render",
        side_effect=RuntimeError("cannot render"),
    ):
        result = export_trip(positions, speed, None, tmp_path, options, lambda _url: None)

    assert ExportFile.MAP not in result.files
    assert result.files[ExportFile.COMPOSITE].is_file()


def test_export_without_movement_writes_nothing(tmp_path: Path) -> None:
    points = [TrackPoint(START, *north(0)), TrackPoint(START + timedelta(minutes=1), *north(20))]
    with pytest.raises(NoMovementError):
        export_trip(points, None, None, tmp_path / "out", ExportOptions(with_map=False))
    assert not (tmp_path / "out").exists()


def test_refresh_rewrites_statistics_and_composite_but_keeps_the_map(
    positions: list[TrackPoint],
    speed: StepSeries,
    altitude: StepSeries,
    tmp_path: Path,
    offline_fetcher: Callable[[str], bytes],
) -> None:
    options = ExportOptions(title="Pass", timezone=ZoneInfo("Europe/Berlin"), map_size=(1200, 800), scale=0.5)
    result = export_trip(positions, speed, altitude, tmp_path, options, offline_fetcher)
    files = {kind: path.name for kind, path in result.files.items()}
    map_bytes = result.files[ExportFile.MAP].read_bytes()
    composite_bytes = result.files[ExportFile.COMPOSITE].read_bytes()
    figures = LogbookFigures(fuel_litres=40, fuel_cost=70, travel_costs={"maut": 23.4})

    with patch("custom_components.reiseverlauftracker.export.exporter.render_base_map") as render_base_map:
        text = refresh_export(positions, speed, altitude, tmp_path, replace(options, logbook=figures), files).stats_text

    render_base_map.assert_not_called()
    assert text == (tmp_path / files[ExportFile.STATS]).read_text(encoding="utf-8")
    assert "Reisekosten:     Maut 23,40 €" in text
    assert "Kosten:          93,40 €" in text
    assert result.files[ExportFile.MAP].read_bytes() == map_bytes
    assert result.files[ExportFile.COMPOSITE].read_bytes() != composite_bytes
    with Image.open(result.files[ExportFile.COMPOSITE]) as composite:
        # Scale 0.5: header with the extra logbook row, then map and profile, each with its gap;
        # no legend, because without a base map the map keeps its old symbols.
        assert composite.height == (380 + 150 + 40 + 40) // 2 + 800 + 900


def test_refresh_creates_no_missing_files(
    positions: list[TrackPoint], speed: StepSeries, altitude: StepSeries, tmp_path: Path
) -> None:
    options = ExportOptions(title="Pass", with_map=False, scale=0.5)
    result = export_trip(positions, speed, altitude, tmp_path, options)
    result.files[ExportFile.STATS].unlink()
    files = {kind: path.name for kind, path in result.files.items() if kind is not ExportFile.STATS}

    refresh_export(positions, speed, altitude, tmp_path, options, files)

    assert not result.files[ExportFile.STATS].exists()
    assert result.files[ExportFile.COMPOSITE].is_file()


def test_refresh_draws_new_symbols_on_the_base_map_without_tiles(
    positions: list[TrackPoint],
    speed: StepSeries,
    altitude: StepSeries,
    tmp_path: Path,
    offline_fetcher: Callable[[str], bytes],
) -> None:
    options = ExportOptions(title="Pass", map_size=(1200, 800), scale=0.5)
    result = export_trip(positions, speed, altitude, tmp_path, options, offline_fetcher)
    assert result.base_map is not None
    assert result.projection is not None
    files = {kind: path.name for kind, path in result.files.items()}
    base_bytes = result.base_map.read_bytes()
    fuel = MapMarker(MarkerKind.FUEL, *north(15000))

    with patch("custom_components.reiseverlauftracker.export.exporter.render_base_map") as render_base_map:
        refresh_export(
            positions,
            speed,
            altitude,
            tmp_path,
            replace(options, scale=2, markers=(fuel,)),
            files,
            BaseMapRef(result.base_map.name, result.projection),
        )

    render_base_map.assert_not_called()
    assert result.base_map.read_bytes() == base_bytes
    x, y = result.projection.to_px(fuel.lat, fuel.lon)
    with Image.open(result.files[ExportFile.MAP]) as image:
        assert image.size == (600, 400)
        assert _close(image.getpixel((round(x) - 6, round(y))), COLORS[MarkerKind.FUEL])
    with Image.open(result.files[ExportFile.COMPOSITE]) as composite:
        # The composite follows the scale setting (2); the legend lists start, end and diesel.
        assert composite.height == 380 * 2 + 3200 + 80 + 160 + 80 + 3600 + 80


def test_redraw_loads_tiles_and_gives_an_old_export_map_base_map_and_legend(
    positions: list[TrackPoint],
    speed: StepSeries,
    altitude: StepSeries,
    tmp_path: Path,
    offline_fetcher: Callable[[str], bytes],
) -> None:
    # An export from before the base map, whose map could not be drawn at all.
    options = ExportOptions(title="Pass", map_size=(1200, 800), scale=0.5)
    result = export_trip(positions, speed, altitude, tmp_path, replace(options, with_map=False))
    files = {kind: path.name for kind, path in result.files.items()}
    assert ExportFile.MAP not in files
    with Image.open(result.files[ExportFile.COMPOSITE]) as composite:
        old_height = composite.height
    fuel = MapMarker(MarkerKind.FUEL, *north(15000))

    renewed = refresh_export(
        positions,
        speed,
        altitude,
        tmp_path,
        replace(options, markers=(fuel,)),
        files,
        None,
        offline_fetcher,
        redraw=True,
    )

    assert renewed.map_redrawn
    assert renewed.files[ExportFile.MAP] == "pass.png"
    assert renewed.base_map is not None
    assert renewed.base_map.name == "pass_karte_basis.png"
    assert (tmp_path / renewed.base_map.name).is_file()
    x, y = renewed.base_map.projection.to_px(fuel.lat, fuel.lon)
    with Image.open(tmp_path / "pass.png") as image:
        assert image.size == (600, 400)
        assert _close(image.getpixel((round(x) - 6, round(y))), COLORS[MarkerKind.FUEL])
    with Image.open(result.files[ExportFile.COMPOSITE]) as composite:
        # Map and legend, each with its gap, are new.
        assert composite.height == old_height + 800 + 20 + 40 + 20


def test_redraw_with_a_missing_tile_keeps_the_map(
    positions: list[TrackPoint],
    speed: StepSeries,
    altitude: StepSeries,
    tmp_path: Path,
    offline_fetcher: Callable[[str], bytes],
) -> None:
    options = ExportOptions(title="Pass", map_size=(1200, 800), scale=0.5)
    result = export_trip(positions, speed, altitude, tmp_path, options, offline_fetcher)
    files = {kind: path.name for kind, path in result.files.items()}
    map_bytes = result.files[ExportFile.MAP].read_bytes()

    # One tile is missing: the old map is better than one with a gap.
    tiles = iter([None])

    def fetch(url: str) -> bytes | None:
        return next(tiles, offline_fetcher(url))

    renewed = refresh_export(positions, speed, altitude, tmp_path, options, files, None, fetch, redraw=True)

    assert not renewed.map_redrawn
    assert renewed.base_map is None
    assert result.files[ExportFile.MAP].read_bytes() == map_bytes


def test_arrival_on_a_pitch_shows_the_pitch_symbol_and_its_name(
    positions: list[TrackPoint],
    speed: StepSeries,
    altitude: StepSeries,
    tmp_path: Path,
    offline_fetcher: Callable[[str], bytes],
) -> None:
    options = ExportOptions(title="Pass", map_size=(1200, 800), scale=0.5, arrival_stay="Camping Seeblick")

    result = export_trip(positions, speed, altitude, tmp_path, options, offline_fetcher)

    assert "Stellplatz:      Camping Seeblick" in result.stats_text
    assert result.projection is not None
    last = max((p for p in positions if p.accuracy == 10), key=lambda p: p.time)
    x, y = result.projection.to_px(last.lat, last.lon)
    with Image.open(result.files[ExportFile.MAP]) as image:
        around = image.crop((round(x) - 12, round(y) - 12, round(x) + 12, round(y) + 12))
        pixels = around.get_flattened_data()
        assert sum(_close(p, COLORS[MarkerKind.PITCH]) for p in pixels) > len(pixels) // 5
        assert not any(_close(p, COLORS[MarkerKind.END], 15) for p in pixels)


def test_map_markers_put_start_and_end_last_and_drop_stops_at_refills() -> None:
    points = [TrackPoint(START, *north(0)), TrackPoint(minutes(30), *north(20000))]
    stop = MapMarker(MarkerKind.STOP, *north(10000))
    fuel = MapMarker(MarkerKind.FUEL, *north(10050))
    other = MapMarker(MarkerKind.STOP, *north(15000))

    markers = map_markers(points, ExportOptions(markers=(stop, fuel, other)))

    assert [m.kind for m in markers] == [MarkerKind.FUEL, MarkerKind.STOP, MarkerKind.START, MarkerKind.END]
    assert map_markers([], ExportOptions()) == []


def _close(pixel: tuple[int, ...], color: str, tolerance: int = 40) -> bool:
    rgb = tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))
    return all(abs(a - b) <= tolerance for a, b in zip(pixel[:3], rgb, strict=True))
