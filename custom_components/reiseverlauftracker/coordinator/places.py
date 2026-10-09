"""Place names for positions of a trip, looked up once each from Nominatim."""

from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.const import DOMAIN
from custom_components.reiseverlauftracker.utils.geocode import async_reverse_geocode
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_loaded_integration

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.settings import ReiseverlaufSettings
    from homeassistant.core import HomeAssistant

PROJECT_URL = "https://github.com/ChrisFerro/ha-reiseverlauf"


def user_agent(version: str | None) -> str:
    """Return the User-Agent sent to OpenStreetMap services."""
    return f"reiseverlauftracker/{version or 'dev'} (+{PROJECT_URL})"


async def async_place_name(
    hass: HomeAssistant, settings: ReiseverlaufSettings, lat: float | None, lon: float | None
) -> str | None:
    """Return the place name at a position, or None when lookups are off or fail."""
    if not settings.place_names or lat is None or lon is None:
        return None
    version = async_get_loaded_integration(hass, DOMAIN).version
    return await async_reverse_geocode(
        async_get_clientsession(hass), lat, lon, hass.config.language, user_agent(str(version) if version else None)
    )
