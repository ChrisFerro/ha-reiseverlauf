"""Tests for the geographic helpers."""

import pytest

from custom_components.reiseverlauftracker.utils.geo import Position, distance_m

pytestmark = pytest.mark.unit


def test_distance_zero() -> None:
    p = Position(52.52, 13.405)
    assert distance_m(p, p) == 0.0


def test_distance_one_degree_latitude() -> None:
    assert distance_m(Position(50.0, 8.0), Position(51.0, 8.0)) == pytest.approx(111195, rel=1e-3)


def test_distance_berlin_munich() -> None:
    berlin = Position(52.5200, 13.4050)
    munich = Position(48.1351, 11.5820)
    assert distance_m(berlin, munich) == pytest.approx(504_000, rel=0.01)
