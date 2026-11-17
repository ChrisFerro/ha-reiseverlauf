"""Tests for the logbook CSV file."""

import csv
from datetime import UTC, datetime
import io
from zoneinfo import ZoneInfo

import pytest

from custom_components.reiseverlauftracker.coordinator.logbook import Logbook, Occasion, Refill
from custom_components.reiseverlauftracker.export.logbook_csv import CSV_TEXTS, logbook_csv

pytestmark = pytest.mark.unit

BERLIN = ZoneInfo("Europe/Berlin")


def sample() -> Logbook:
    book = Logbook()
    book.add(datetime(2026, 10, 31, 7, 0, tzinfo=UTC), Occasion.TRIP_START, odometer_km=34299, fuel_percent=60)
    book.add(
        datetime(2026, 10, 31, 9, 30, tzinfo=UTC),
        Occasion.STOP,
        odometer_km=34340,
        fuel_percent=100,
        fuel=Refill(55.25, 96.4),
        gas=Refill(28.4),
        place="Tankstelle; Nord",
        lat=50.123456,
        lon=8.5,
    )
    return book


def test_german_csv_uses_semicolons_decimal_commas_and_local_time() -> None:
    rows = list(csv.reader(io.StringIO(logbook_csv(sample().entries, "de", BERLIN)), delimiter=";"))

    assert rows[0] == list(CSV_TEXTS["de"].headers)
    assert rows[1][:2] == ["31.10.2026 08:00", "Reisestart"]
    assert rows[1][10:] == ["", "", "", ""]
    assert rows[2] == [
        "31.10.2026 10:30",
        "Halt",
        "Tankstelle; Nord",
        "50,123456",
        "8,500000",
        "34340",
        "ja",
        "100",
        "",
        "",
        "55,25",
        "96,40",
        "28,40",
        "",
    ]


def test_english_csv_and_unknown_languages_use_commas_and_points() -> None:
    for language in ("en", "fr"):
        rows = list(csv.reader(io.StringIO(logbook_csv(sample().entries, language, UTC))))

        assert rows[0][0] == "Time"
        assert rows[2][:2] == ["2026-10-31 09:30", "Stop"]
        assert rows[2][10] == "55.25"


def test_empty_logbook_has_only_the_header() -> None:
    assert logbook_csv([], "de-DE", BERLIN).count("\r\n") == 1
