"""Tests for statistics and their localised text."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.reiseverlauftracker.export import ExportOptions, LogbookFigures, StepSeries, Stop, TrackPoint
from custom_components.reiseverlauftracker.export.stats import (
    compute_stats,
    elevation_change,
    logbook_rows,
    moving_time,
    stats_rows,
    stats_text,
    stop_lines,
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


def test_stats_text_lists_stops() -> None:
    texts = texts_for("de")
    stops = [
        Stop(start=START, end=START + timedelta(minutes=20), place="Brenner"),
        Stop(start=START + timedelta(hours=2), end=START + timedelta(hours=3, minutes=10)),
    ]

    text = stats_text("Titel", [("Strecke", "1 km")], stop_lines(stops, texts, BERLIN))

    assert text.endswith("\nHalte:\n  Brenner  10:00–10:20 (0 h 20 min)\n  Unbekannter Ort  12:00–13:10 (1 h 10 min)\n")
    assert stop_lines([], texts, BERLIN) == []


def test_logbook_rows_german() -> None:
    figures = LogbookFigures(
        odometer_start_km=34299,
        odometer_end_km=34383,
        fuel_litres=55.3,
        fuel_cost=96.4,
        gas_litres=20,
        gas_cost=18.4,
        consumption_l_100km=11.96,
    )

    assert logbook_rows(figures, texts_for("de"), "EUR") == [
        ("Kilometerstand", "34299 – 34383 km"),
        ("Getankt", "55,3 l Diesel · 20,0 l Gas"),
        ("Kosten", "114,80 €"),
        ("Ø-Verbrauch", "12,0 l/100 km"),
    ]


def test_logbook_rows_leave_out_what_is_missing() -> None:
    texts = texts_for("en")

    assert logbook_rows(None, texts, "EUR") == []
    assert logbook_rows(LogbookFigures(odometer_end_km=1000), texts, "CHF") == [("Odometer", "1000 km")]
    assert logbook_rows(LogbookFigures(gas_litres=10, gas_cost=9.5), texts, "XYZ") == [
        ("Refuelled", "10.0 l gas"),
        ("Costs", "9.50 XYZ"),
    ]


def test_travel_costs_count_in_the_costs_and_are_listed_in_the_text() -> None:
    figures = LogbookFigures(fuel_litres=40, fuel_cost=70, travel_costs={"maut": 83.3, "faehre": 85})
    texts = texts_for("de")

    assert figures.cost == pytest.approx(238.3)
    assert figures.fuel_and_gas_cost == 70
    assert ("Kosten", "238,30 €") in logbook_rows(figures, texts, "EUR")
    assert logbook_rows(figures, texts, "EUR", travel_details=True)[-1] == (
        "Reisekosten",
        "Maut 83,30 € · Fähre 85,00 €",
    )
    assert all(label != "Reisekosten" for label, _ in logbook_rows(figures, texts, "EUR"))
    assert figures.as_dict()["reisekosten"] == {"maut": 83.3, "faehre": 85}


def test_logbook_figures_round_trip() -> None:
    figures = LogbookFigures(
        odometer_start_km=1, odometer_end_km=2, fuel_litres=3, fuel_cost=4.5, gas_cost=1, travel_costs={"maut": 9}
    )

    assert LogbookFigures.from_dict(figures.as_dict()) == figures
