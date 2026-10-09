"""Tests for export folders and their metadata."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.reiseverlauftracker.coordinator.exports import (
    ExportInfo,
    list_exports,
    read_export,
    remove_files,
    write_metadata,
)
from custom_components.reiseverlauftracker.export import ExportFile

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
