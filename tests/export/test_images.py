"""Tests for the profile chart, the composite image and the bundled font."""

from datetime import UTC, datetime, timedelta

from PIL import Image
import pytest

from custom_components.reiseverlauftracker.export import ExportOptions, StepSeries, TrackPoint
from custom_components.reiseverlauftracker.export.chart import nice_step, render_profile, time_ticks
from custom_components.reiseverlauftracker.export.composite import render_composite
from custom_components.reiseverlauftracker.export.fonts import load_font
from custom_components.reiseverlauftracker.export.texts import texts_for
from custom_components.reiseverlauftracker.export.track import prepare_track

pytestmark = pytest.mark.unit

START = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
DEPARTURE = START + timedelta(minutes=15)
ARRIVAL = START + timedelta(minutes=55)


def minutes(n: float) -> datetime:
    return START + timedelta(minutes=n)


def north(metres: float) -> tuple[float, float]:
    return 47.0 + metres / 111195.0, 11.0


DE = texts_for("de")


@pytest.mark.parametrize(("span", "step"), [(0, 1.0), (30, 5), (300, 50), (7.3, 2), (1234, 500)])
def test_nice_step(span: float, step: float) -> None:
    assert nice_step(span) == step


def test_time_ticks_hourly_in_local_time(positions: list[TrackPoint], speed: StepSeries, altitude: StepSeries) -> None:
    ticks = time_ticks(DEPARTURE.timestamp(), DEPARTURE.timestamp() + 5 * 3600, UTC, DE)
    assert [label for _, label in ticks] == ["09:00", "10:00", "11:00", "12:00", "13:00"]


@pytest.mark.parametrize("glyph", ["ö", "Ø", "–", "ß"])
def test_bundled_font_has_german_glyphs(glyph: str) -> None:
    font = load_font(40)
    assert bytes(font.getmask(glyph)) != bytes(font.getmask("￿"))


def test_profile_has_two_panels_and_scales(
    positions: list[TrackPoint], speed: StepSeries, altitude: StepSeries
) -> None:
    track = prepare_track(positions, speed, altitude, ExportOptions())
    window = (track.chart_start, track.chart_end)

    image = render_profile(track.points, track.chart_speed, window, DE, UTC, 1.0, "Tour")
    assert image is not None
    assert image.size == (2400, 1800)

    half = render_profile(track.points, track.chart_speed, window, DE, UTC, 0.5)
    assert half is not None
    assert half.size == (1200, 900)


def test_profile_with_speed_only_and_without_data(
    positions: list[TrackPoint], speed: StepSeries, altitude: StepSeries
) -> None:
    track = prepare_track(positions, speed, None, ExportOptions())
    window = (track.chart_start, track.chart_end)

    image = render_profile(track.points, track.chart_speed, window, DE, UTC)
    assert image is not None
    assert image.size == (2400, 900)
    assert render_profile(track.points, None, window, DE, UTC) is None


def test_composite_stacks_parts_under_header() -> None:
    first = Image.new("RGB", (1200, 800), "red")
    second = Image.new("RGB", (2400, 900), "blue")
    figures = [("Strecke", "30,0 km"), ("Fahrzeit", "0 h 40 min")]

    image = render_composite([first, None, second], "Tour", "01.10.2026", figures)

    assert image is not None
    assert image.size == (2400, 380 + 1600 + 40 + 900 + 40)
    assert image.getpixel((10, 380 + 10)) == (255, 0, 0)
    assert render_composite([None], "Tour", "", figures) is None
