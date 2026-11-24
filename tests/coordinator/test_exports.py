"""Tests for export folders and their metadata."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.reiseverlauftracker.coordinator.exports import (
    ExportInfo,
    existing_files,
    list_exports,
    read_export,
    remove_files,
    set_countries,
    write_metadata,
)
from custom_components.reiseverlauftracker.coordinator.trip_log import TrackCounters
from custom_components.reiseverlauftracker.export import BaseMapRef, ExportFile, LogbookFigures, MapProjection, Stop

pytestmark = pytest.mark.unit


def make_export(base: Path, folder: str, start: datetime) -> ExportInfo:
    """Create an export folder with one file per kind."""
    files = {
        kind: f"trip{suffix}"
        for kind, suffix in {
            ExportFile.COMPOSITE: "_gesamt.png",
            ExportFile.MAP: ".png",
            ExportFile.GPX: ".gpx",
        }.items()
    }
    (base / folder).mkdir(parents=True)
    for name in files.values():
        (base / folder / name).write_text("x")
    info = ExportInfo(
        folder=folder,
        title="Trip",
        start=start,
        end=start + timedelta(hours=2),
        distance_km=12.5,
        driving_time=timedelta(minutes=80),
        files=files,
        stats_text="Trip\n",
        automatic=True,
    )
    write_metadata(base, info)
    return info


def test_metadata_round_trip(tmp_path: Path) -> None:
    info = make_export(tmp_path, "a", datetime(2026, 10, 1, tzinfo=UTC))

    assert read_export(tmp_path, "a") == info


def test_metadata_round_trip_with_logbook(tmp_path: Path) -> None:
    info = replace(
        make_export(tmp_path, "a", datetime(2026, 10, 1, tzinfo=UTC)),
        logbook=LogbookFigures(odometer_start_km=34299, odometer_end_km=34383, fuel_litres=55, fuel_cost=96.4),
    )
    write_metadata(tmp_path, info)

    assert read_export(tmp_path, "a") == info


def test_metadata_round_trip_with_start_counters(tmp_path: Path) -> None:
    info = replace(
        make_export(tmp_path, "a", datetime(2026, 10, 1, tzinfo=UTC)), counter_start=TrackCounters(5000, 12, 34)
    )
    write_metadata(tmp_path, info)

    assert read_export(tmp_path, "a") == info


def test_metadata_round_trip_with_map_symbols(tmp_path: Path) -> None:
    start = datetime(2026, 10, 1, tzinfo=UTC)
    info = replace(
        make_export(tmp_path, "a", start),
        stops=(Stop(start + timedelta(minutes=30), start + timedelta(minutes=50), "Kiel", 54.32, 10.13),),
        base_map=BaseMapRef("trip_karte_basis.png", MapProjection(12, 2161.5, 1310.25, 2400, 1600)),
        arrival_stay="Camping Seeblick",
    )
    write_metadata(tmp_path, info)

    assert read_export(tmp_path, "a") == info


def test_old_metadata_without_map_symbols_is_still_read(tmp_path: Path) -> None:
    start = datetime(2026, 10, 1, tzinfo=UTC)
    info = replace(make_export(tmp_path, "a", start), stops=(Stop(start, start + timedelta(minutes=9), "Kiel"),))
    write_metadata(tmp_path, info)
    path = tmp_path / "a" / "export.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("base_map", "arrival_stay"):
        del data[key]
    for stop in data["stops"]:
        del stop["lat"], stop["lon"]
    path.write_text(json.dumps(data), encoding="utf-8")

    assert read_export(tmp_path, "a") == info


def test_removing_the_map_removes_its_base_map(tmp_path: Path) -> None:
    info = replace(
        make_export(tmp_path, "a", datetime(2026, 10, 1, tzinfo=UTC)),
        base_map=BaseMapRef("trip_karte_basis.png", MapProjection(12, 1.0, 2.0, 800, 600)),
    )
    write_metadata(tmp_path, info)
    (tmp_path / "a" / "trip_karte_basis.png").write_text("x")

    kept = remove_files(tmp_path, "a", {ExportFile.GPX})
    assert kept is not None
    assert kept.base_map == info.base_map
    assert (tmp_path / "a" / "trip_karte_basis.png").is_file()

    remaining = remove_files(tmp_path, "a", {ExportFile.MAP})

    assert remaining is not None
    assert remaining.base_map is None
    assert not (tmp_path / "a" / "trip_karte_basis.png").exists()
    assert read_export(tmp_path, "a") == remaining


def test_removing_everything_removes_the_base_map_and_the_folder(tmp_path: Path) -> None:
    info = replace(
        make_export(tmp_path, "a", datetime(2026, 10, 1, tzinfo=UTC)),
        base_map=BaseMapRef("trip_karte_basis.png", MapProjection(12, 1.0, 2.0, 800, 600)),
    )
    write_metadata(tmp_path, info)
    (tmp_path / "a" / "trip_karte_basis.png").write_text("x")

    assert remove_files(tmp_path, "a", set(ExportFile)) is None
    assert not (tmp_path / "a").exists()


def test_countries_are_stored_in_the_metadata(tmp_path: Path) -> None:
    info = make_export(tmp_path, "a", datetime(2026, 10, 1, tzinfo=UTC))
    assert info.countries is None

    changed = set_countries(tmp_path, "a", ("DE", "AT"))

    assert changed == replace(info, countries=("DE", "AT"))
    assert read_export(tmp_path, "a") == changed
    assert set_countries(tmp_path, "missing", ("DE",)) is None


def test_update_time_round_trip_and_existing_files(tmp_path: Path) -> None:
    info = replace(
        make_export(tmp_path, "a", datetime(2026, 10, 1, tzinfo=UTC)), updated=datetime(2026, 11, 1, tzinfo=UTC)
    )
    write_metadata(tmp_path, info)
    (tmp_path / "a" / info.files[ExportFile.MAP]).unlink()

    assert read_export(tmp_path, "a") == info
    assert set(existing_files(tmp_path, info)) == {ExportFile.COMPOSITE, ExportFile.GPX}


def test_list_exports_newest_first_and_skips_foreign_folders(tmp_path: Path) -> None:
    make_export(tmp_path, "old", datetime(2026, 9, 1, tzinfo=UTC))
    make_export(tmp_path, "new", datetime(2026, 10, 1, tzinfo=UTC))
    (tmp_path / "foreign").mkdir()

    assert [info.folder for info in list_exports(tmp_path)] == ["new", "old"]
    assert list_exports(tmp_path / "missing") == []


def test_remove_some_kinds_keeps_the_rest(tmp_path: Path) -> None:
    make_export(tmp_path, "a", datetime(2026, 10, 1, tzinfo=UTC))
    (tmp_path / "a" / "notes.txt").write_text("mine")

    remaining = remove_files(tmp_path, "a", {ExportFile.MAP, ExportFile.STATS})

    assert remaining is not None
    assert set(remaining.files) == {ExportFile.COMPOSITE, ExportFile.GPX}
    assert sorted(p.name for p in (tmp_path / "a").iterdir()) == [
        "export.json",
        "notes.txt",
        "trip.gpx",
        "trip_gesamt.png",
    ]
    assert read_export(tmp_path, "a") == remaining


def test_removing_everything_deletes_the_folder(tmp_path: Path) -> None:
    make_export(tmp_path, "a", datetime(2026, 10, 1, tzinfo=UTC))

    assert remove_files(tmp_path, "a", set(ExportFile)) is None
    assert not (tmp_path / "a").exists()


def test_folder_with_foreign_files_survives_full_removal(tmp_path: Path) -> None:
    make_export(tmp_path, "a", datetime(2026, 10, 1, tzinfo=UTC))
    (tmp_path / "a" / "notes.txt").write_text("mine")

    assert remove_files(tmp_path, "a", set(ExportFile)) is None
    assert [p.name for p in (tmp_path / "a").iterdir()] == ["notes.txt"]


def test_label_is_short_and_starts_with_local_time(tmp_path: Path) -> None:
    info = make_export(tmp_path, "a", datetime(2026, 10, 9, 8, 40, tzinfo=UTC))
    long_title = replace(info, title="Frankfurt am Main – Assenheim, 09.10.2026")

    assert info.label(ZoneInfo("Europe/Berlin")) == "09.10.26 10:40 · Trip"
    assert long_title.label(ZoneInfo("Europe/Berlin")) == "09.10.26 10:40 · Frankfurt am Main…"


def test_label_marks_manual_exports_in_the_language_of_the_instance(tmp_path: Path) -> None:
    info = replace(make_export(tmp_path, "a", datetime(2026, 10, 9, 8, 40, tzinfo=UTC)), automatic=False)
    tz = ZoneInfo("Europe/Berlin")

    assert info.label(tz, "de") == "09.10.26 10:40 · Manuell · Trip"
    assert info.label(tz, "en-GB") == "09.10.26 10:40 · Manual · Trip"
    assert info.label(tz, "fr") == "09.10.26 10:40 · Manual · Trip"
