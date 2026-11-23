"""Place names for coordinates from OpenStreetMap Nominatim."""

import asyncio
from typing import Any

from aiohttp import ClientError, ClientSession

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
REQUEST_TIMEOUT_S = 10
PLACE_ZOOM = 14
# Zoom 18 returns the feature at the position, e.g. a camp site (docs/features/feat-10-tour.md 5.7).
STAY_ZOOM = 18
STAY_TYPES = ("camp_site", "caravan_site")
# Zoom 3 asks for the country only, which keeps the response small.
COUNTRY_ZOOM = 3
PLACE_KEYS = ("city", "town", "village", "municipality", "hamlet", "suburb", "county")


async def async_reverse_geocode(
    session: ClientSession,
    lat: float,
    lon: float,
    language: str,
    user_agent: str,
) -> str | None:
    """
    Return the name of the city, town or village at a coordinate, or None.

    Any network or format problem yields None, because the title then falls back to the date.
    """
    return place_name(await _async_reverse(session, lat, lon, PLACE_ZOOM, language, user_agent))


async def async_reverse_stay(
    session: ClientSession, lat: float, lon: float, language: str, user_agent: str
) -> str | None:
    """Return the name of the camp site or motorhome pitch at a coordinate, else the place name, or None."""
    return stay_name(await _async_reverse(session, lat, lon, STAY_ZOOM, language, user_agent))


async def async_reverse_camp_site(
    session: ClientSession, lat: float, lon: float, language: str, user_agent: str
) -> str | None:
    """Return the name of the camp site or motorhome pitch at a coordinate, or None if there is none."""
    return camp_site_name(await _async_reverse(session, lat, lon, STAY_ZOOM, language, user_agent))


async def async_reverse_country(session: ClientSession, lat: float, lon: float, user_agent: str) -> str | None:
    """Return the ISO 3166-1 alpha-2 code of the country at a coordinate, or None (e.g. at sea or on errors)."""
    return country_code(await _async_reverse(session, lat, lon, COUNTRY_ZOOM, "en", user_agent))


async def _async_reverse(
    session: ClientSession, lat: float, lon: float, zoom: int, language: str, user_agent: str
) -> Any:
    params = {"format": "jsonv2", "lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "zoom": str(zoom), "addressdetails": "1"}
    headers = {"User-Agent": user_agent, "Accept-Language": language}
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT_S):
            response = await session.get(NOMINATIM_URL, params=params, headers=headers)
            response.raise_for_status()
            return await response.json()
    except ClientError, TimeoutError, ValueError:
        return None


def country_code(data: Any) -> str | None:
    """Return the upper-case country code of a Nominatim reverse response."""
    if not isinstance(data, dict) or not isinstance(address := data.get("address"), dict):
        return None
    code = address.get("country_code")
    return code.upper() if isinstance(code, str) and len(code) == 2 and code.isalpha() else None


def place_name(data: Any) -> str | None:
    """Pick the most fitting place name from a Nominatim reverse response."""
    if not isinstance(data, dict):
        return None
    address = data.get("address")
    if isinstance(address, dict):
        for key in PLACE_KEYS:
            if isinstance(name := address.get(key), str) and name:
                return name
    name = data.get("name")
    return name if isinstance(name, str) and name else None


def camp_site_name(data: Any) -> str | None:
    """Return the name of a camp site or motorhome pitch in a Nominatim response, or None for any other place."""
    if not isinstance(data, dict):
        return None
    name = data.get("name")
    return name if data.get("type") in STAY_TYPES and isinstance(name, str) and name else None


def stay_name(data: Any) -> str | None:
    """Return the name of a camp site or motorhome pitch in a Nominatim response, else the place name."""
    if not isinstance(data, dict):
        return None
    if (name := camp_site_name(data)) is not None:
        return name
    address = data.get("address")
    if isinstance(address, dict):
        for key in PLACE_KEYS:
            if isinstance(place := address.get(key), str) and place:
                return place
    return None
