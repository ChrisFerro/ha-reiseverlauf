"""Tests for the map symbols, their layout, the ferry crossings and the base map (Feat-12)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import math

from PIL import Image, ImageColor
import pytest

from custom_components.reiseverlauftracker.export.map import (
    FERRY_COLOR,
    ROUTE_COLOR,
    _halfway,
    dashes,
    default_markers,
    draw_overlay,
    render_base_map,
    render_route_map,
    symbol_diameter,
)
from custom_components.reiseverlauftracker.export.model import (
    FerryLeg,
    MapMarker,
    MapProjection,
    MarkerKind,
    TrackPoint,
)
from custom_components.reiseverlauftracker.export.symbols import (
    COLORS,
    draw_symbol,
    layout,
    merge_markers,
    render_legend,
    symbol_image,
)

pytestmark = pytest.mark.unit

START = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
SIZE = (800, 600)
LINE = 6


def route(lat: float, lon: float, steps: int = 20, d_lat: float = 0.002, d_lon: float = 0.001) -> list[TrackPoint]:
    return [
        TrackPoint(START + timedelta(minutes=i), lat + i * d_lat, lon + i * d_lon, accuracy=10) for i in range(steps)
    ]


def close(pixel: tuple[int, ...], color: str, tolerance: int = 40) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(pixel[:3], ImageColor.getrgb(color), strict=True))


def share(image: Image.Image, color: str) -> float:
    """Return the share of pixels close to `color`."""
    rgb = image.convert("RGB")
    pixels = rgb.get_flattened_data()
    matches = sum(1 for p in pixels if close(p, color))
    return matches / (rgb.width * rgb.height)


@pytest.mark.parametrize("kind", list(MarkerKind))
def test_every_kind_has_a_coloured_symbol_with_a_white_pictogram(kind: MarkerKind) -> None:
    image = symbol_image(kind, 96)

    assert image.mode == "RGBA"
    assert image.width == image.height > 96
    assert share(image, COLORS[kind]) > 0.2
    assert share(image, "#ffffff") > 0.1


def test_symbols_scale_with_the_line_width() -> None:
    assert symbol_diameter(12) == 2 * symbol_diameter(6)
    assert symbol_image(MarkerKind.FUEL, symbol_diameter(12)).width > symbol_image(MarkerKind.FUEL, 48).width


def test_a_stop_where_fuel_was_bought_shows_only_the_fuel_symbol() -> None:
    markers = [
        MapMarker(MarkerKind.STOP, 47.0, 11.0),
        MapMarker(MarkerKind.FUEL, 47.0003, 11.0),  # about 33 m away
        MapMarker(MarkerKind.GAS, 47.0003, 11.0),
        MapMarker(MarkerKind.STOP, 47.1, 11.0),  # far away: stays
    ]

    merged = merge_markers(markers, same_place_m=100)

    assert [m.kind for m in merged] == [MarkerKind.FUEL, MarkerKind.GAS, MarkerKind.STOP]
    assert merged[-1].lat == 47.1


def test_overlapping_symbols_move_aside_and_start_keeps_its_place() -> None:
    placed = layout(
        [(MarkerKind.FUEL, (100.0, 100.0)), (MarkerKind.GAS, (100.0, 100.0)), (MarkerKind.START, (102.0, 100.0))],
        diameter=40,
    )

    positions = dict(placed)
    assert positions[MarkerKind.START] == (102.0, 100.0)
    points = list(positions.values())
    assert all(math.dist(a, b) >= 36 for i, a in enumerate(points) for b in points[i + 1 :])
    # Drawing order: start on top, i.e. last.
    assert [kind for kind, _ in placed] == [MarkerKind.FUEL, MarkerKind.GAS, MarkerKind.START]


def test_symbols_far_apart_stay_where_they_are() -> None:
    placed = layout([(MarkerKind.STOP, (10.0, 10.0)), (MarkerKind.END, (300.0, 300.0))], diameter=40)

    assert placed == [(MarkerKind.STOP, (10.0, 10.0)), (MarkerKind.END, (300.0, 300.0))]


def test_a_symbol_at_the_edge_is_clipped_instead_of_failing() -> None:
    image = Image.new("RGBA", (100, 100), "white")

    draw_symbol(image, MarkerKind.END, (2.0, 98.0), 40)

    assert close(image.getpixel((5, 95)), COLORS[MarkerKind.END])


def test_legend_lists_the_given_kinds_in_a_fixed_order() -> None:
    labels = {MarkerKind.FUEL: "Diesel", MarkerKind.START: "Start"}

    legend = render_legend([MarkerKind.FUEL, MarkerKind.START], labels, 1200)

    assert legend is not None
    assert legend.size == (1200, 80)
    start = next(x for x in range(1200) if close(legend.getpixel((x, 40)), COLORS[MarkerKind.START], 20))
    fuel = next(x for x in range(1200) if close(legend.getpixel((x, 40)), COLORS[MarkerKind.FUEL], 20))
    assert start < fuel


def test_no_legend_without_symbols() -> None:
    assert render_legend([], {}, 1200) is None


def test_legend_scales() -> None:
    legend = render_legend([MarkerKind.GAS], {}, 2400, scale=2)

    assert legend is not None
    assert legend.height == 160


def test_dashes_alternate_dash_and_gap() -> None:
    pieces = dashes([(0.0, 0.0), (100.0, 0.0)], dash=18, gap=12)

    assert [round(a[0]) for a, _ in pieces] == [0, 30, 60, 90]
    assert [round(b[0]) for _, b in pieces] == [18, 48, 78, 100]


def test_dashes_continue_around_corners() -> None:
    pieces = dashes([(0.0, 0.0), (10.0, 0.0), (10.0, 20.0)], dash=15, gap=5)

    assert round(sum(math.dist(a, b) for a, b in pieces)) == 25


def test_halfway_follows_the_path() -> None:
    assert _halfway([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]) == (10.0, 0.0)
    assert _halfway([(5.0, 5.0), (5.0, 5.0)]) == (5.0, 5.0)


def test_projection_survives_a_round_trip() -> None:
    projection = MapProjection(zoom=12, x_center=2173.5, y_center=1420.25, width=2400, height=1600)

    assert MapProjection.from_dict(projection.as_dict()) == projection


def test_base_map_has_only_tiles_and_the_overlay_draws_the_route_where_the_projection_says(
    offline_fetcher: Callable[[str], bytes],
) -> None:
    points = route(47.0, 11.0)

    base = render_base_map([points], SIZE, LINE, offline_fetcher)

    assert base is not None
    assert base.image.size == SIZE
    middle = points[10]
    x, y = base.projection.to_px(middle.lat, middle.lon)
    assert not close(base.image.getpixel((round(x), round(y))), ROUTE_COLOR)
    image = draw_overlay(base.image, base.projection, [points], [], [], LINE)
    assert close(image.getpixel((round(x), round(y))), ROUTE_COLOR)


def test_base_map_frames_symbols_and_ferries_outside_the_route(
    offline_fetcher: Callable[[str], bytes],
) -> None:
    points = route(47.0, 11.0)
    far = MapMarker(MarkerKind.PITCH, 47.2, 11.3)

    base = render_base_map([points], SIZE, LINE, offline_fetcher, markers=[far])

    assert base is not None
    x, y = base.projection.to_px(far.lat, far.lon)
    assert 0 <= x <= SIZE[0]
    assert 0 <= y <= SIZE[1]


def test_overlay_draws_symbols_and_dashed_ferry_without_changing_the_base(
    offline_fetcher: Callable[[str], bytes],
) -> None:
    land = route(54.40, 11.05)
    other = route(54.70, 11.30)
    ferry = FerryLeg(((land[-1].lat, land[-1].lon), (other[0].lat, other[0].lon)))
    stop = MapMarker(MarkerKind.STOP, land[5].lat, land[5].lon)
    base = render_base_map([land, other], SIZE, LINE, offline_fetcher, [stop], [ferry])
    assert base is not None
    before = base.image.copy()

    image = draw_overlay(base.image, base.projection, [land, other], [stop], [ferry], LINE)

    assert image.mode == "RGB"
    assert image.size == SIZE
    assert before.tobytes() == base.image.tobytes()
    x, y = base.projection.to_px(stop.lat, stop.lon)
    assert close(image.getpixel((round(x) - 10, round(y))), COLORS[MarkerKind.STOP])

    a = base.projection.to_px(*ferry.points[0])
    b = base.projection.to_px(*ferry.points[1])
    samples = [image.getpixel((round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t))) for t in _steps()]
    blue = [close(p, FERRY_COLOR) for p in samples]
    assert any(blue)
    assert not all(blue)
    # The ship sits halfway along the crossing.
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    assert close(image.getpixel((round(mid[0]), round(mid[1]) - symbol_diameter(LINE) // 3)), FERRY_COLOR)


def _steps() -> list[float]:
    # Leave out the middle, where the ship covers the line.
    return [i / 100 for i in range(10, 40)] + [i / 100 for i in range(60, 90)]


def test_default_markers_are_start_end_and_places() -> None:
    first, second = route(47.0, 11.0), route(47.5, 11.5)

    markers = default_markers([first, [], second], places=[(47.3, 11.2)])

    assert [m.kind for m in markers] == [MarkerKind.PITCH, MarkerKind.START, MarkerKind.END]
    assert (markers[1].lat, markers[1].lon) == (first[0].lat, first[0].lon)
    assert (markers[2].lat, markers[2].lon) == (second[-1].lat, second[-1].lon)
    assert default_markers([[]]) == []


def test_route_map_draws_start_and_end_symbols(offline_fetcher: Callable[[str], bytes]) -> None:
    points = route(47.0, 11.0)
    image = render_route_map([points], SIZE, LINE, offline_fetcher)

    assert image is not None
    base = render_base_map([points], SIZE, LINE, offline_fetcher, default_markers([points]))
    assert base is not None
    x, y = base.projection.to_px(points[-1].lat, points[-1].lon)
    assert share(image.crop((round(x) - 20, round(y) - 20, round(x) + 20, round(y) + 20)), COLORS[MarkerKind.END]) > 0.2


def test_route_map_without_route_is_none(offline_fetcher: Callable[[str], bytes]) -> None:
    assert render_route_map([[]], SIZE, LINE, offline_fetcher) is None
    assert render_base_map([], SIZE, LINE, offline_fetcher) is None
