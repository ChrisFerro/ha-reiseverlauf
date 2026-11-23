"""Tests for the Nominatim place-name lookup."""

from typing import Any

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.reiseverlauftracker.utils.geocode import (
    NOMINATIM_URL,
    async_reverse_country,
    async_reverse_geocode,
    country_code,
    place_name,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"address": {"town": "Kiel", "county": "X"}}, "Kiel"),
        ({"address": {"village": "Laboe"}, "name": "Ehrenmal"}, "Laboe"),
        ({"address": {}, "name": "Fähranleger"}, "Fähranleger"),
        ({"error": "Unable to geocode"}, None),
        ([], None),
    ],
)
def test_place_name(data: Any, expected: str | None) -> None:
    assert place_name(data) == expected


async def test_reverse_geocode_sends_user_agent_and_language(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(NOMINATIM_URL, json={"address": {"city": "Hamburg"}})

    name = await async_reverse_geocode(async_get_clientsession(hass), 53.55, 9.99, "de", "reiseverlauftracker/test")

    assert name == "Hamburg"
    _, url, _, headers = aioclient_mock.mock_calls[0]
    assert url.query["lat"] == "53.55000"
    assert headers["User-Agent"] == "reiseverlauftracker/test"
    assert headers["Accept-Language"] == "de"


async def test_reverse_geocode_returns_none_on_http_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(NOMINATIM_URL, status=429)

    assert await async_reverse_geocode(async_get_clientsession(hass), 53.55, 9.99, "de", "ua") is None


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"address": {"country_code": "at"}}, "AT"),
        ({"address": {"country_code": "eu-x"}}, None),
        ({"address": {}}, None),
        ({"error": "Unable to geocode"}, None),
        (None, None),
    ],
)
def test_country_code(data: Any, expected: str | None) -> None:
    assert country_code(data) == expected


async def test_reverse_country_asks_for_the_country_zoom(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(NOMINATIM_URL, json={"address": {"country": "Österreich", "country_code": "at"}})

    code = await async_reverse_country(async_get_clientsession(hass), 47.26, 11.39, "reiseverlauftracker/test")

    assert code == "AT"
    _, url, _, _ = aioclient_mock.mock_calls[0]
    assert url.query["zoom"] == "3"
