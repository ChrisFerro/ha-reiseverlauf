"""Tests for the logbook CSV file."""

import csv
from datetime import UTC, date, datetime
import io
from zoneinfo import ZoneInfo

import pytest

from custom_components.reiseverlauftracker.coordinator.logbook import CostCategory, Logbook, Occasion, Refill
from custom_components.reiseverlauftracker.export.logbook_csv import CSV_TEXTS, logbook_csv, travel_costs_csv

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


def test_every_occasion_and_category_has_a_text_in_every_language() -> None:
    for texts in CSV_TEXTS.values():
        assert set(texts.occasions) == set(Occasion)
        assert set(texts.categories) == set(CostCategory)


def test_late_entries_are_named_in_the_csv() -> None:
    book = Logbook()
    book.add(datetime(2026, 10, 31, 9, 30, tzinfo=UTC), Occasion.LATE, fuel=Refill(40, 70))

    rows = list(csv.reader(io.StringIO(logbook_csv(book.entries, "de", BERLIN)), delimiter=";"))

    assert rows[1][1] == "Nachtrag"


def test_travel_costs_csv_names_trip_category_and_country() -> None:
    book = Logbook()
    trip = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)
    book.add_travel_cost(date(2026, 10, 14), CostCategory.TOLL, 23.4, trip_start=trip, country="AT")
    book.add_travel_cost(date(2026, 10, 20), CostCategory.PITCH, 150, note="Camping Seeblick; 5 Nächte")

    text = travel_costs_csv(book.travel_costs, {trip: "Südtirol"}, "de", BERLIN)
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))

    assert rows == [
        list(CSV_TEXTS["de"].travel_headers),
        ["14.10.2026", "14.10.2026 08:00", "Südtirol", "Maut", "AT", "23,40", ""],
        ["20.10.2026", "", "", "Stellplatz", "", "150,00", "Camping Seeblick; 5 Nächte"],
    ]
    english = list(csv.reader(io.StringIO(travel_costs_csv(book.travel_costs, {}, "en", UTC))))
    assert english[1] == ["2026-10-14", "2026-10-14 06:00", "", "Toll", "AT", "23.40", ""]
