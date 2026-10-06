"""Tests for the GPX output."""

from datetime import UTC, datetime, timedelta
import xml.etree.ElementTree as ET

import pytest

from custom_components.reiseverlauftracker.export import TrackPoint
from custom_components.reiseverlauftracker.export.gpx import build_gpx

pytestmark = pytest.mark.unit

START = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
DEPARTURE = START + timedelta(minutes=15)
ARRIVAL = START + timedelta(minutes=55)


def minutes(n: float) -> datetime:
    return START + timedelta(minutes=n)


def north(metres: float) -> tuple[float, float]:
    return 47.0 + metres / 111195.0, 11.0


NS = {"g": "http://www.topografix.com/GPX/1/1"}


def test_gpx_contains_points_altitude_and_speed() -> None:
    points = [
        TrackPoint(START, *north(0), speed=36.0, altitude=601.25),
        TrackPoint(minutes(1), *north(500)),
    ]
    document = build_gpx(points, "Fahrt <Süd> & Nord")
    root = ET.fromstring(document)  # noqa: S314 - parses the GPX this test just built

    assert root.findtext("g:trk/g:name", namespaces=NS) == "Fahrt <Süd> & Nord"
    trkpts = root.findall("g:trk/g:trkseg/g:trkpt", NS)
    assert len(trkpts) == 2
    assert trkpts[0].get("lat") == "47.000000"
    assert trkpts[0].findtext("g:ele", namespaces=NS) == "601.2"
    assert trkpts[0].findtext("g:time", namespaces=NS) == "2026-10-01T08:00:00Z"
    assert trkpts[0].findtext("g:extensions/g:speed", namespaces=NS) == "10.00"
    assert trkpts[1].find("g:ele", NS) is None
    assert trkpts[1].find("g:extensions", NS) is None
