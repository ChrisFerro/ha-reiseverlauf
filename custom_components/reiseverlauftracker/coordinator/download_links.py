"""
Download paths and their signed links for the dashboard.

A browser opens a link without the login header, so each link carries a signature (`authSig`) of the read-only
content user of Home Assistant. A link is valid for 24 hours and renewed every hour; the signing secret lives in
memory only, so every link becomes invalid on a restart and is signed anew.
"""

from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import quote

from custom_components.reiseverlauftracker.const import DOMAIN
from homeassistant.components.http.auth import async_sign_path

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .exports import ExportInfo

URL_BASE: Final = f"/api/{DOMAIN}"
FILE_URL: Final = URL_BASE + "/{entry_id}/datei/{folder}/{name}"
ZIP_URL: Final = URL_BASE + "/{entry_id}/zip/{folder}"
LOGBOOK_URL: Final = URL_BASE + "/{entry_id}/fahrtenbuch"
TRAVEL_COSTS_URL: Final = URL_BASE + "/{entry_id}/reisekosten"

LINK_VALIDITY: Final = timedelta(hours=24)
RENEW_INTERVAL: Final = timedelta(hours=1)
ATTR_DOWNLOADS: Final = "downloads"
TYPE_ZIP: Final = "zip"
TYPE_CSV: Final = "csv"


def file_path(entry_id: str, folder: str, name: str) -> str:
    """Return the unsigned download path of one export file."""
    return FILE_URL.format(entry_id=entry_id, folder=quote(folder, safe=""), name=quote(name, safe=""))


def zip_path(entry_id: str, folder: str) -> str:
    """Return the unsigned download path of the ZIP with all files of an export."""
    return ZIP_URL.format(entry_id=entry_id, folder=quote(folder, safe=""))


def logbook_path(entry_id: str) -> str:
    """Return the unsigned download path of the logbook CSV."""
    return LOGBOOK_URL.format(entry_id=entry_id)


def travel_costs_path(entry_id: str) -> str:
    """Return the unsigned download path of the travel costs CSV."""
    return TRAVEL_COSTS_URL.format(entry_id=entry_id)


class DownloadLinks:
    """Signs download paths and keeps each link until the next renewal, so attributes do not change meanwhile."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Create an empty cache; links are signed when first asked for."""
        self._hass = hass
        self._entry_id = entry_id
        self._signed: dict[str, str] = {}

    def renew(self) -> None:
        """Forget every link, so the next request signs it anew."""
        self._signed.clear()

    def sign(self, path: str) -> str:
        """Return the signed link of `path`."""
        if (link := self._signed.get(path)) is None:
            link = self._signed[path] = async_sign_path(self._hass, path, LINK_VALIDITY, use_content_user=True)
        return link

    def for_export(self, info: ExportInfo) -> list[dict[str, Any]]:
        """Return the links of every file of an export and of its ZIP, as the `downloads` attribute lists them."""
        links = [
            {"typ": kind.value, "name": name, "url": self.sign(file_path(self._entry_id, info.folder, name))}
            for kind, name in info.files.items()
        ]
        if links:
            links.append(
                {"typ": TYPE_ZIP, "name": f"{info.folder}.zip", "url": self.sign(zip_path(self._entry_id, info.folder))}
            )
        return links

    def for_logbook(self, name: str | None, travel_costs_name: str | None = None) -> list[dict[str, Any]]:
        """Return the links of the logbook CSV and the travel costs CSV, as the `downloads` attribute lists them."""
        links = []
        if name is not None:
            links.append({"typ": TYPE_CSV, "name": name, "url": self.sign(logbook_path(self._entry_id))})
        if travel_costs_name is not None:
            links.append(
                {"typ": TYPE_CSV, "name": travel_costs_name, "url": self.sign(travel_costs_path(self._entry_id))}
            )
        return links
