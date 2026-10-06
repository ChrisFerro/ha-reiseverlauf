"""Tests for the map rendering and the tile download."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from custom_components.reiseverlauftracker.export import ExportOptions, StepSeries, TrackPoint
from custom_components.reiseverlauftracker.export.map import http_tile_fetcher, render_map
from custom_components.reiseverlauftracker.export.track import prepare_track

pytestmark = pytest.mark.unit

START = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
DEPARTURE = START + timedelta(minutes=15)
ARRIVAL = START + timedelta(minutes=55)


def minutes(n: float) -> datetime:
    return START + timedelta(minutes=n)


def north(metres: float) -> tuple[float, float]:
    return 47.0 + metres / 111195.0, 11.0


def test_map_renders_with_offline_tiles(
    positions: list[TrackPoint],
    speed: StepSeries,
    altitude: StepSeries,
    offline_fetcher: Callable[[str], bytes],
    fake_tiles: list[str],
) -> None:
    track = prepare_track(positions, None, None, ExportOptions())
    image = render_map(track.points, (800, 600), 6, offline_fetcher)

    assert image is not None
    assert image.size == (800, 600)
    assert fake_tiles
    assert all(url.startswith("https://tile.openstreetmap.org/") for url in fake_tiles)


def test_missing_tiles_leave_gaps_instead_of_failing(
    positions: list[TrackPoint], speed: StepSeries, altitude: StepSeries
) -> None:
    track = prepare_track(positions, None, None, ExportOptions())
    image = render_map(track.points, (800, 600), 6, lambda _url: None)

    assert image is not None


def test_broken_tiles_are_left_blank(
    positions: list[TrackPoint], speed: StepSeries, altitude: StepSeries, caplog: pytest.LogCaptureFixture
) -> None:
    track = prepare_track(positions, None, None, ExportOptions())

    assert render_map(track.points, (800, 600), 6, lambda _url: b"not an image") is not None
    assert "missing tiles" in caplog.text


def test_http_fetcher_sends_user_agent_and_retries() -> None:
    ok = MagicMock(status_code=200, content=b"png")
    with patch(
        "custom_components.reiseverlauftracker.export.map.requests.get",
        side_effect=[requests.ConnectionError(), ok],
    ) as get:
        assert http_tile_fetcher("reiseverlauftracker/test")("https://tile/1/2/3.png") == b"png"

    assert get.call_count == 2
    assert get.call_args.kwargs["headers"] == {"User-Agent": "reiseverlauftracker/test"}
    assert get.call_args.kwargs["timeout"] > 0


def test_http_fetcher_gives_up_on_errors() -> None:
    with patch(
        "custom_components.reiseverlauftracker.export.map.requests.get",
        return_value=MagicMock(status_code=429, content=b""),
    ) as get:
        assert http_tile_fetcher("ua")("https://tile/1/2/3.png") is None
    assert get.call_count == 2
