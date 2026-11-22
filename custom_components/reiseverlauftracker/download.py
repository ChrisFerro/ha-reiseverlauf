"""
Authenticated downloads of export files, a ZIP per export and the CSV files of logbook and travel costs.

The media browser of Home Assistant only serves images, audio and video, so GPX, statistics, raw points and the
CSV file are served here. Only files an export lists in `export.json` (or the two CSV files) are ever served; the
folder and the name are looked up, never joined from the request.
"""

from collections.abc import Iterator
import mimetypes
from pathlib import Path
import tempfile
from typing import IO, TYPE_CHECKING, Final
from urllib.parse import quote
import zipfile

from aiohttp import hdrs, web

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.http import KEY_HASS, HomeAssistantView

from .const import DOMAIN
from .coordinator.download_links import FILE_URL, LOGBOOK_URL, TRAVEL_COSTS_URL, ZIP_URL
from .coordinator.export_runner import media_base

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import ReiseverlaufDataUpdateCoordinator
    from .coordinator.exports import ExportInfo

CONTENT_TYPES: Final = {
    ".csv": "text/csv; charset=utf-8",
    ".gpx": "application/gpx+xml",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
}
ZIP_CHUNK_BYTES: Final = 256 * 1024
ZIP_SPOOL_BYTES: Final = 8 * 1024 * 1024
COMPRESSED_SUFFIXES: Final = {".png", ".jpg", ".jpeg"}
# Browsers must ask again every time, so an expired or old link never opens a cached copy.
NO_STORE: Final = "no-store, private"


def async_register_views(hass: HomeAssistant) -> None:
    """Register the download views once for all entries."""
    hass.http.register_view(ExportFileView())
    hass.http.register_view(ExportZipView())
    hass.http.register_view(LogbookCsvView())
    hass.http.register_view(TravelCostsCsvView())


def _coordinator(request: web.Request, entry_id: str) -> ReiseverlaufDataUpdateCoordinator:
    entry = request.app[KEY_HASS].config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        raise web.HTTPNotFound
    return entry.runtime_data.coordinator


def _export(coordinator: ReiseverlaufDataUpdateCoordinator, folder: str) -> ExportInfo:
    for info in coordinator.exports:
        if info.folder == folder:
            return info
    raise web.HTTPNotFound


def _content_disposition(name: str) -> str:
    fallback = name.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name, safe='')}"


def _content_type(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return CONTENT_TYPES.get(suffix) or mimetypes.guess_type(name)[0] or "application/octet-stream"


def _file_response(path: Path, name: str) -> web.FileResponse:
    return web.FileResponse(
        path,
        headers={
            hdrs.CONTENT_TYPE: _content_type(name),
            hdrs.CONTENT_DISPOSITION: _content_disposition(name),
            hdrs.CACHE_CONTROL: NO_STORE,
        },
    )


class ExportFileView(HomeAssistantView):
    """One file of an export, as listed in its `export.json`."""

    url = FILE_URL
    name = f"api:{DOMAIN}:file"

    async def get(self, request: web.Request, entry_id: str, folder: str, name: str) -> web.StreamResponse:
        """Serve the file, or 404 if the export does not list it or it is gone."""
        coordinator = _coordinator(request, entry_id)
        info = _export(coordinator, folder)
        if name not in info.files.values():
            raise web.HTTPNotFound
        path = media_base(coordinator.hass, coordinator.settings) / info.folder / name
        if not await coordinator.hass.async_add_executor_job(path.is_file):
            raise web.HTTPNotFound
        return _file_response(path, name)

    # Download managers may ask for size and type first; the signature is valid for HEAD as well.
    head = get


class ExportZipView(HomeAssistantView):
    """All existing files of an export as one ZIP, built on request and not stored."""

    url = ZIP_URL
    name = f"api:{DOMAIN}:zip"

    async def get(self, request: web.Request, entry_id: str, folder: str) -> web.StreamResponse:
        """Stream the ZIP, or 404 if the export has no files left."""
        coordinator = _coordinator(request, entry_id)
        info = _export(coordinator, folder)
        hass = coordinator.hass
        folder_path = media_base(hass, coordinator.settings) / info.folder
        archive = await hass.async_add_executor_job(_build_zip, folder_path, list(info.files.values()))
        if archive is None:
            raise web.HTTPNotFound
        try:
            response = web.StreamResponse(
                headers={
                    hdrs.CONTENT_TYPE: "application/zip",
                    hdrs.CONTENT_DISPOSITION: _content_disposition(f"{info.folder}.zip"),
                    hdrs.CACHE_CONTROL: NO_STORE,
                }
            )
            response.content_length = await hass.async_add_executor_job(_size, archive)
            await response.prepare(request)
            if request.method != hdrs.METH_HEAD:
                chunks = _chunks(archive)
                while chunk := await hass.async_add_executor_job(next, chunks, b""):
                    await response.write(chunk)
            await response.write_eof()
            return response
        finally:
            await hass.async_add_executor_job(archive.close)

    # Download managers may ask for size and type first; the signature is valid for HEAD as well.
    head = get


class LogbookCsvView(HomeAssistantView):
    """The logbook CSV of an entry."""

    url = LOGBOOK_URL
    name = f"api:{DOMAIN}:logbook"

    async def get(self, request: web.Request, entry_id: str) -> web.StreamResponse:
        """Serve `fahrtenbuch.csv`, or 404 if it was not written yet."""
        coordinator = _coordinator(request, entry_id)
        path = coordinator.logbook.csv_path
        if not await coordinator.hass.async_add_executor_job(path.is_file):
            raise web.HTTPNotFound
        return _file_response(path, path.name)

    # Download managers may ask for size and type first; the signature is valid for HEAD as well.
    head = get


class TravelCostsCsvView(HomeAssistantView):
    """The travel costs CSV of an entry."""

    url = TRAVEL_COSTS_URL
    name = f"api:{DOMAIN}:travel_costs"

    async def get(self, request: web.Request, entry_id: str) -> web.StreamResponse:
        """Serve `reisekosten.csv`, or 404 if it was not written yet."""
        coordinator = _coordinator(request, entry_id)
        path = coordinator.logbook.travel_csv_path
        if not await coordinator.hass.async_add_executor_job(path.is_file):
            raise web.HTTPNotFound
        return _file_response(path, path.name)

    # Download managers may ask for size and type first; the signature is valid for HEAD as well.
    head = get


def _build_zip(folder: Path, names: list[str]) -> IO[bytes] | None:
    """Write the existing files into a temporary ZIP below the folder name; None if none exists."""
    existing = [name for name in names if (folder / name).is_file()]
    if not existing:
        return None
    archive = tempfile.SpooledTemporaryFile(max_size=ZIP_SPOOL_BYTES)
    with zipfile.ZipFile(archive, "w") as zf:
        for name in existing:
            compression = (
                zipfile.ZIP_STORED if Path(name).suffix.lower() in COMPRESSED_SUFFIXES else zipfile.ZIP_DEFLATED
            )
            zf.write(folder / name, f"{folder.name}/{name}", compress_type=compression)
    return archive


def _size(archive: IO[bytes]) -> int:
    size = archive.seek(0, 2)
    archive.seek(0)
    return size


def _chunks(archive: IO[bytes]) -> Iterator[bytes]:
    while chunk := archive.read(ZIP_CHUNK_BYTES):
        yield chunk
