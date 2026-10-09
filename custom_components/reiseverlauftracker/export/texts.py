"""Localised labels and value formatting for export files and images."""

from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo


@dataclass(frozen=True, slots=True)
class Texts:
    """All strings of one export language."""

    decimal_separator: str
    date_format: str
    chart_datetime_format: str
    default_title: str
    period_same_day: str
    period_multi_day: str
    period: str
    distance: str
    moving_time: str
    max_speed: str
    avg_moving_speed: str
    altitude_range: str
    elevation_gain: str
    elevation_profile: str
    speed: str
    altitude_axis: str
    distance_axis: str
    time_axis: str


TEXTS: dict[str, Texts] = {
    "de": Texts(
        decimal_separator=",",
        date_format="%d.%m.%Y",
        chart_datetime_format="%d.%m. %H:%M",
        default_title="Wohnmobil {}",
        period_same_day="{date} · Abfahrt {start} Uhr · Ankunft {end} Uhr",
        period_multi_day="Abfahrt {start_date} {start} Uhr · Ankunft {end_date} {end} Uhr",
        period="Zeitraum",
        distance="Strecke",
        moving_time="Fahrzeit",
        max_speed="Höchstgeschw.",
        avg_moving_speed="Ø in Bewegung",
        altitude_range="Höhe min/max",
        elevation_gain="Höhenmeter",
        elevation_profile="Höhenprofil",
        speed="Geschwindigkeit",
        altitude_axis="Höhe (m)",
        distance_axis="Strecke (km)",
        time_axis="Uhrzeit",
    ),
    "en": Texts(
        decimal_separator=".",
        date_format="%Y-%m-%d",
        chart_datetime_format="%m-%d %H:%M",
        default_title="Motorhome {}",
        period_same_day="{date} · Departure {start} · Arrival {end}",
        period_multi_day="Departure {start_date} {start} · Arrival {end_date} {end}",
        period="Period",
        distance="Distance",
        moving_time="Driving time",
        max_speed="Top speed",
        avg_moving_speed="Ø while moving",
        altitude_range="Altitude min/max",
        elevation_gain="Elevation gain",
        elevation_profile="Elevation profile",
        speed="Speed",
        altitude_axis="Altitude (m)",
        distance_axis="Distance (km)",
        time_axis="Time",
    ),
}


def texts_for(language: str) -> Texts:
    """Return the texts for a Home Assistant language code, falling back to English."""
    return TEXTS.get(language.split("-", maxsplit=1)[0].lower(), TEXTS["en"])


def format_number(texts: Texts, value: float, decimals: int = 0) -> str:
    """Format a number with the decimal separator of the language."""
    return f"{value:.{decimals}f}".replace(".", texts.decimal_separator)


def format_duration(value: timedelta) -> str:
    """Format a duration as hours and minutes."""
    seconds = int(value.total_seconds())
    return f"{seconds // 3600} h {seconds % 3600 // 60:02d} min"


def format_period(texts: Texts, start: datetime, end: datetime, tz: tzinfo) -> str:
    """Format departure and arrival in local time."""
    a, b = start.astimezone(tz), end.astimezone(tz)
    if a.date() == b.date():
        return texts.period_same_day.format(date=a.strftime(texts.date_format), start=f"{a:%H:%M}", end=f"{b:%H:%M}")
    return texts.period_multi_day.format(
        start_date=a.strftime(texts.date_format),
        start=f"{a:%H:%M}",
        end_date=b.strftime(texts.date_format),
        end=f"{b:%H:%M}",
    )


def format_dates(texts: Texts, start: datetime, end: datetime, tz: tzinfo) -> str:
    """Return the local date of a trip, or the first and last date when it spans several days."""
    a, b = start.astimezone(tz), end.astimezone(tz)
    if a.date() == b.date():
        return a.strftime(texts.date_format)
    return f"{a.strftime(texts.date_format)} – {b.strftime(texts.date_format)}"


def default_title(texts: Texts, start: datetime, end: datetime, tz: tzinfo) -> str:
    """Return the title used when the user gave none."""
    return texts.default_title.format(format_dates(texts, start, end, tz))


def format_places(start_place: str | None, end_place: str | None) -> str | None:
    """Return both names joined by a dash, a single name for a round trip, or None if a name is missing."""
    if not start_place or not end_place:
        return None
    return start_place if start_place == end_place else f"{start_place} – {end_place}"
