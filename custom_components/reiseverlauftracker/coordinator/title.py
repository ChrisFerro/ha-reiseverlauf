"""Title of an automatically detected trip."""

from datetime import datetime, tzinfo

from custom_components.reiseverlauftracker.const import TITLE_FORMAT_DATE, TITLE_FORMAT_PLACE
from custom_components.reiseverlauftracker.export.texts import Texts, default_title, format_dates, format_places


def trip_title(
    title_format: str,
    texts: Texts,
    start: datetime,
    end: datetime,
    tz: tzinfo,
    start_place: str | None,
    end_place: str | None,
) -> str:
    """Return the title in the configured format; without both place names it falls back to the date."""
    places = format_places(start_place, end_place)
    if places is None or title_format == TITLE_FORMAT_DATE:
        return default_title(texts, start, end, tz)
    if title_format == TITLE_FORMAT_PLACE:
        return places
    return f"{places}, {format_dates(texts, start, end, tz)}"
