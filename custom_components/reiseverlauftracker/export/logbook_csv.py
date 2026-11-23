"""CSV files of the whole logbook and of the travel costs, one row per entry, in the instance language."""

import csv
from dataclasses import dataclass
from datetime import datetime, tzinfo
import io

from custom_components.reiseverlauftracker.coordinator.logbook import CostCategory, LogbookEntry, Occasion, TravelCost


@dataclass(frozen=True, slots=True)
class CsvTexts:
    """Column headers and formats of one language."""

    delimiter: str
    decimal_separator: str
    datetime_format: str
    date_format: str
    yes: str
    no: str
    headers: tuple[str, ...]
    occasions: dict[Occasion, str]
    travel_headers: tuple[str, ...]
    categories: dict[CostCategory, str]


CSV_TEXTS: dict[str, CsvTexts] = {
    "de": CsvTexts(
        delimiter=";",
        decimal_separator=",",
        datetime_format="%d.%m.%Y %H:%M",
        date_format="%d.%m.%Y",
        yes="ja",
        no="nein",
        headers=(
            "Zeit",
            "Anlass",
            "Ort",
            "Breite",
            "Länge",
            "Kilometerstand",
            "Kilometerstand korrigiert",
            "Kraftstoff %",
            "Gas 1 %",
            "Gas 2 %",
            "Diesel l",
            "Diesel €",
            "Gas l",
            "Gas €",
        ),
        occasions={
            Occasion.TRIP_START: "Reisestart",
            Occasion.STOP: "Halt",
            Occasion.MANUAL: "Manuell",  # codespell:ignore manuell
            Occasion.LATE: "Nachtrag",
        },
        travel_headers=("Datum", "Reise", "Titel", "Kategorie", "Land", "Betrag €", "Notiz"),
        categories={
            CostCategory.TOLL: "Maut",
            CostCategory.VIGNETTE: "Vignette",
            CostCategory.FERRY: "Fähre",
            CostCategory.TUNNEL: "Tunnel",
            CostCategory.PITCH: "Stellplatz",
            CostCategory.OTHER: "Sonstiges",
        },
    ),
    "en": CsvTexts(
        delimiter=",",
        decimal_separator=".",
        datetime_format="%Y-%m-%d %H:%M",
        date_format="%Y-%m-%d",
        yes="yes",
        no="no",
        headers=(
            "Time",
            "Occasion",
            "Place",
            "Latitude",
            "Longitude",
            "Odometer",
            "Odometer corrected",
            "Fuel %",
            "Gas 1 %",
            "Gas 2 %",
            "Diesel l",
            "Diesel €",
            "Gas l",
            "Gas €",
        ),
        occasions={
            Occasion.TRIP_START: "Trip start",
            Occasion.STOP: "Stop",
            Occasion.MANUAL: "Manual",
            Occasion.LATE: "Late entry",
        },
        travel_headers=("Date", "Trip", "Title", "Category", "Country", "Amount €", "Note"),
        categories={
            CostCategory.TOLL: "Toll",
            CostCategory.VIGNETTE: "Vignette",
            CostCategory.FERRY: "Ferry",
            CostCategory.TUNNEL: "Tunnel",
            CostCategory.PITCH: "Pitch",
            CostCategory.OTHER: "Other",
        },
    ),
}


def csv_texts(language: str) -> CsvTexts:
    """Return the texts for `language`, falling back to English."""
    return CSV_TEXTS.get(language.split("-", maxsplit=1)[0], CSV_TEXTS["en"])


def _number(texts: CsvTexts, value: float | None, digits: int) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}".replace(".", texts.decimal_separator)


def logbook_csv(entries: list[LogbookEntry], language: str, timezone: tzinfo) -> str:
    """Return the entries as CSV text with a header row; times in `timezone`."""
    texts = csv_texts(language)

    def number(value: float | None, digits: int) -> str:
        return _number(texts, value, digits)

    out = io.StringIO()
    writer = csv.writer(out, delimiter=texts.delimiter, lineterminator="\r\n")
    writer.writerow(texts.headers)
    for e in entries:
        writer.writerow(
            (
                e.time.astimezone(timezone).strftime(texts.datetime_format),
                texts.occasions[e.occasion],
                e.place or "",
                number(e.lat, 6),
                number(e.lon, 6),
                number(e.odometer_km, 0),
                texts.yes if e.odometer_corrected else texts.no,
                number(e.fuel_percent, 0),
                number(e.gas1_percent, 0),
                number(e.gas2_percent, 0),
                number(e.fuel.litres if e.fuel else None, 2),
                number(e.fuel.amount if e.fuel else None, 2),
                number(e.gas.litres if e.gas else None, 2),
                number(e.gas.amount if e.gas else None, 2),
            )
        )
    return out.getvalue()


def travel_costs_csv(costs: list[TravelCost], trip_titles: dict[datetime, str], language: str, timezone: tzinfo) -> str:
    """Return the travel costs as CSV text with a header row; trips by start time in `timezone` and title."""
    texts = csv_texts(language)
    out = io.StringIO()
    writer = csv.writer(out, delimiter=texts.delimiter, lineterminator="\r\n")
    writer.writerow(texts.travel_headers)
    for c in costs:
        writer.writerow(
            (
                c.day.strftime(texts.date_format),
                c.trip_start.astimezone(timezone).strftime(texts.datetime_format) if c.trip_start else "",
                trip_titles.get(c.trip_start, "") if c.trip_start else "",
                texts.categories[c.category],
                c.country or "",
                _number(texts, c.amount, 2),
                c.note or "",
            )
        )
    return out.getvalue()
