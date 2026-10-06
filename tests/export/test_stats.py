"""Tests for statistics and their localised text."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.reiseverlauftracker.export import ExportOptions, StepSeries, TrackPoint
from custom_components.reiseverlauftracker.export.stats import (
    compute_stats,
    elevation_change,
    moving_time,
    stats_rows,
    stats_text,
)
from custom_components.reiseverlauftracker.export.texts import default_title, format_period, texts_for
from custom_components.reiseverlauftracker.export.track import prepare_track

pytestmark = pytest.mark.unit

START = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
DEPARTURE = START + timedelta(minutes=15)
ARRIVAL = START + timedelta(minutes=55)


def minutes(n: float) -> datetime:
    return START + timedelta(minutes=n)


def north(metres: float) -> tuple[float, float]:
    return 47.0 + metres / 111195.0, 11.0


BERLIN = ZoneInfo("Europe/Berlin")


def test_stats_of_synthetic_trip(positions: list[TrackPoint], speed: StepSeries, altitude: StepSeries) -> None:
    options = ExportOptions()
    track = prepare_track(positions, speed, altitude, options)
    stats = compute_stats(track.points, track.speed, options)

    assert stats.departure == DEPARTURE
    assert stats.arrival == ARRIVAL
    assert stats.distance_km == pytest.approx(30.0, abs=0.01)
    assert stats.moving_time == timedelta(minutes=40)
    assert stats.max_speed_kmh == 45.0
    assert stats.avg_moving_speed_kmh == 45.0
    assert (stats.altitude_min_m, stats.altitude_max_m) == (pytest.approx(600), pytest.approx(900))
    assert stats.ascent_m == pytest.approx(300, abs=0.01)
    assert stats.descent_m == pytest.approx(200, abs=5)


def test_stationary_altitude_drift_is_ignored() -> None:
    drift = [598.5, 597.5, 597.3, 598.0, 599.6, 597.9, 598.3, 596.0, 595.7, 596.7]
    assert elevation_change(drift, 5.0) == (0.0, 0.0)
    assert elevation_change(drift, 1.0) != (0.0, 0.0)


def test_moving_time_skips_long_gaps() -> None:
    points = [
        TrackPoint(START, *north(0)),
        TrackPoint(minutes(1), *north(1000)),
        TrackPoint(minutes(30), *north(9000)),
        TrackPoint(minutes(31), *north(9001)),
    ]
    assert moving_time(points, 3.0, timedelta(minutes=5)) == timedelta(minutes=1)


def test_stats_rows_german(positions: list[TrackPoint], speed: StepSeries, altitude: StepSeries) -> None:
    options = ExportOptions()
    track = prepare_track(positions, speed, altitude, options)
    rows = dict(stats_rows(compute_stats(track.points, track.speed, options), texts_for("de"), BERLIN))

    assert rows["Zeitraum"] == "01.10.2026 · Abfahrt 10:15 Uhr · Ankunft 10:55 Uhr"
    assert rows["Strecke"] == "30,0 km"
    assert rows["Fahrzeit"] == "0 h 40 min"
    assert rows["Höchstgeschw."] == "45 km/h"
    assert rows["Ø in Bewegung"] == "45 km/h"
    assert rows["Höhe min/max"] == "600 / 900 m"
    assert rows["Höhenmeter"].startswith("+300 / -")


def test_stats_rows_english_without_sensors(
    positions: list[TrackPoint], speed: StepSeries, altitude: StepSeries
) -> None:
    options = ExportOptions(language="en-GB")
    track = prepare_track(positions, None, None, options)
    rows = stats_rows(compute_stats(track.points, None, options), texts_for(options.language), UTC)

    assert [label for label, _ in rows] == ["Period", "Distance", "Driving time"]
    assert rows[1][1] == "30.0 km"


def test_stats_text_layout() -> None:
    text = stats_text("Tour", [("Strecke", "1,0 km")])
    assert text == "Tour\n====\nStrecke:         1,0 km\n"


def test_unknown_language_falls_back_to_english() -> None:
    assert texts_for("fr") is texts_for("en")


def test_period_and_title_across_days() -> None:
    texts = texts_for("de")
    end = START + timedelta(days=2)
    assert format_period(texts, START, end, BERLIN) == "Abfahrt 01.10.2026 10:00 Uhr · Ankunft 03.10.2026 10:00 Uhr"
    assert default_title(texts, START, end, BERLIN) == "Wohnmobil 01.10.2026 – 03.10.2026"
    assert default_title(texts_for("en"), START, START, BERLIN) == "Motorhome 2026-10-01"
