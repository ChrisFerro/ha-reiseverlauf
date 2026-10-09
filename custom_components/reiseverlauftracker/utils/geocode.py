"""Place names for coordinates from OpenStreetMap Nominatim."""

import asyncio
from typing import Any

from aiohttp import ClientError, ClientSession

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
REQUEST_TIMEOUT_S = 10
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
    params = {"format": "jsonv2", "lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "zoom": "14", "addressdetails": "1"}
    headers = {"User-Agent": user_agent, "Accept-Language": language}
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT_S):
            response = await session.get(NOMINATIM_URL, params=params, headers=headers)
            response.raise_for_status()
            data: Any = await response.json()
    except ClientError, TimeoutError, ValueError:
        return None
    return place_name(data)


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
