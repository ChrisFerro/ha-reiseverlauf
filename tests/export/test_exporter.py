"""Tests for a complete export run."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from PIL import Image
import pytest

from custom_components.reiseverlauftracker.export import (
    ExportFile,
    ExportOptions,
    NoMovementError,
    StepSeries,
    TrackPoint,
    export_trip,
    slugify,
)

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
        assert composite.height == 380 + (1600 + 40) + (1800 + 40)


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
    points = [TrackPoint(START, *north(0)), TrackPoint(START, *north(20))]
    with pytest.raises(NoMovementError):
        export_trip(points, None, None, tmp_path / "out", ExportOptions(with_map=False))
    assert not (tmp_path / "out").exists()
