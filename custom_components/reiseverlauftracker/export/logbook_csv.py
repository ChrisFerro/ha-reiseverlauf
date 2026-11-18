"""CSV file of the whole logbook, one row per entry, in the instance language."""

import csv
from dataclasses import dataclass
from datetime import tzinfo
import io

from custom_components.reiseverlauftracker.coordinator.logbook import LogbookEntry, Occasion


@dataclass(frozen=True, slots=True)
class CsvTexts:
    """Column headers and formats of one language."""

    delimiter: str
    decimal_separator: str
    datetime_format: str
    yes: str
    no: str
    headers: tuple[str, ...]
    occasions: dict[Occasion, str]


CSV_TEXTS: dict[str, CsvTexts] = {
    "de": CsvTexts(
        delimiter=";",
        decimal_separator=",",
        datetime_format="%d.%m.%Y %H:%M",
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
        },
    ),
    "en": CsvTexts(
        delimiter=",",
        decimal_separator=".",
        datetime_format="%Y-%m-%d %H:%M",
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
        occasions={Occasion.TRIP_START: "Trip start", Occasion.STOP: "Stop", Occasion.MANUAL: "Manual"},
    ),
}


def csv_texts(language: str) -> CsvTexts:
    """Return the texts for `language`, falling back to English."""
    return CSV_TEXTS.get(language.split("-", maxsplit=1)[0], CSV_TEXTS["en"])


def logbook_csv(entries: list[LogbookEntry], language: str, timezone: tzinfo) -> str:
    """Return the entries as CSV text with a header row; times in `timezone`."""
    texts = csv_texts(language)

    def number(value: float | None, digits: int) -> str:
        if value is None:
            return ""
        return f"{value:.{digits}f}".replace(".", texts.decimal_separator)

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
