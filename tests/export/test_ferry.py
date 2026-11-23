"""Tests for ferry crossings in the export: split off from the distance driven (Feat-12 5.10)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from custom_components.reiseverlauftracker.export import ExportOptions, Stop, TrackPoint, export_trip
from custom_components.reiseverlauftracker.export.ferry import split_track
from custom_components.reiseverlauftracker.export.model import StepSeries
from custom_components.reiseverlauftracker.export.stats import compute_stats, stats_rows, stop_lines
from custom_components.reiseverlauftracker.export.texts import texts_for

pytestmark = pytest.mark.unit

T0 = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
METRES_PER_DEGREE_LAT = 111195.0


def point(minute: int, metres: float, altitude: float | None = None) -> TrackPoint:
    return TrackPoint(T0 + timedelta(minutes=minute), 54.0 + metres / METRES_PER_DEGREE_LAT, 11.0, 10, None, altitude)


def at(minute: int) -> datetime:
    return T0 + timedelta(minutes=minute)


# 1 km driven to the port, a crossing from minute 10 to 40 with positions on board, 1 km driven after it.
TRACK = [
    point(0, 0, 10),
    point(5, 500, 20),
    point(9, 1000, 5),
    point(20, 4000, 0),
    point(30, 8000, 30),
    point(41, 10_000, 5),
    point(45, 10_500, 15),
    point(50, 11_000, 25),
]
FERRY = Stop(start=at(10), end=at(40), place="Puttgarden", ferry=True)


def test_without_ferry_the_track_stays_whole() -> None:
    split = split_track(TRACK, [Stop(start=at(10), end=at(40))])

    assert split.land == [TRACK]
    assert split.ferries == []
    assert split.legs == ()


def test_track_is_split_at_the_crossing() -> None:
    split = split_track(TRACK, [FERRY])

    assert split.land == [TRACK[:3], TRACK[5:]]
    assert split.ferries == [TRACK[2:6]]
    assert split.ferry_time == timedelta(minutes=30)
    assert split.legs[0].points[0] == (TRACK[2].lat, TRACK[2].lon)


def test_crossing_without_positions_on_board_joins_departure_and_arrival() -> None:
    track = [*TRACK[:3], *TRACK[5:]]

    split = split_track(track, [FERRY])

    assert split.ferries == [[TRACK[2], TRACK[5]]]
    assert split.land == [TRACK[:3], TRACK[5:]]


def test_ferry_counts_neither_as_distance_nor_as_climb_or_speed() -> None:
    speed = StepSeries([(at(0), 50.0), (at(12), 35.0), (at(41), 60.0)])
    options = ExportOptions(stops=(FERRY,))

    stats = compute_stats(TRACK, speed, options)

    assert stats.distance_km == pytest.approx(2.0, abs=0.01)
    assert stats.ferry_km == pytest.approx(9.0, abs=0.01)
    assert stats.ferry_time == timedelta(minutes=30)
    assert stats.moving_time == timedelta(minutes=18)
    # Uphill: 10 → 20 before, 5 → 25 after the crossing; the swell on board does not count.
    assert stats.ascent_m == pytest.approx(30)
    assert stats.descent_m == pytest.approx(15)
    assert stats.max_speed_kmh == 60
    assert stats.avg_moving_speed_kmh == pytest.approx(55)


def test_statistics_show_the_ferry_on_its_own_row_and_in_the_stops() -> None:
    texts = texts_for("de")
    stats = compute_stats(TRACK, None, ExportOptions(stops=(FERRY,)))

    rows = dict(stats_rows(stats, texts, UTC))
    lines = stop_lines([FERRY], texts, UTC)

    assert rows["Fähre"] == "9,0 km, 0 h 30 min"
    assert rows["Strecke"] == "2,0 km"
    assert lines[2].startswith("  Fähre: Puttgarden  08:10–08:40")


def test_trip_without_ferry_has_no_ferry_row() -> None:
    stats = compute_stats(TRACK, None, ExportOptions())

    assert "Fähre" not in dict(stats_rows(stats, texts_for("de"), UTC))
    assert stats.ferry_km == 0


def test_export_draws_the_crossing_and_lists_it_in_the_legend(
    tmp_path: Path, offline_fetcher: Callable[[str], bytes]
) -> None:
    options = ExportOptions(title="Fehmarnbelt", stops=(FERRY,), min_movement_m=50)

    result = export_trip(TRACK, None, None, tmp_path, options, offline_fetcher)

    assert result.stats.ferry_km == pytest.approx(9.0, abs=0.01)
    assert "Fähre:" in result.stats_text
    assert result.base_map is not None
    assert result.stats.distance_km == pytest.approx(2.0, abs=0.01)
