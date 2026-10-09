"""Tests for the title of automatically detected trips."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.reiseverlauftracker.coordinator.title import trip_title
from custom_components.reiseverlauftracker.export.texts import texts_for

pytestmark = pytest.mark.unit

BERLIN = ZoneInfo("Europe/Berlin")
START = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)
SAME_DAY = datetime(2026, 10, 12, 15, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
DE = texts_for("de")


@pytest.mark.parametrize(
    ("title_format", "end", "places", "expected"),
    [
        ("date_place", SAME_DAY, ("Hamburg", "Kiel"), "Hamburg – Kiel, 12.10.2026"),
        ("date_place", LATER, ("Hamburg", "Kiel"), "Hamburg – Kiel, 12.10.2026 – 14.10.2026"),
        ("date_place", SAME_DAY, ("Kiel", "Kiel"), "Kiel, 12.10.2026"),
        ("date_place", SAME_DAY, ("Hamburg", None), "Wohnmobil 12.10.2026"),
        ("place", SAME_DAY, ("Hamburg", "Kiel"), "Hamburg – Kiel"),
        ("place", SAME_DAY, (None, None), "Wohnmobil 12.10.2026"),
        ("date", SAME_DAY, ("Hamburg", "Kiel"), "Wohnmobil 12.10.2026"),
    ],
)
def test_trip_title(title_format: str, end: datetime, places: tuple[str | None, str | None], expected: str) -> None:
    assert trip_title(title_format, DE, START, end, BERLIN, *places) == expected
