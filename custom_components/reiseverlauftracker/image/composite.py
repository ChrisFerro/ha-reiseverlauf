"""Composite image of the last trip, served through Home Assistant's authenticated image proxy."""

from datetime import datetime
from pathlib import Path

from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
from custom_components.reiseverlauftracker.coordinator.export_runner import media_base
from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from custom_components.reiseverlauftracker.export import ExportFile
from homeassistant.components.image import ImageEntity, ImageEntityDescription
from homeassistant.core import callback
from homeassistant.util import dt as dt_util


class ReiseverlaufCompositeImage(ImageEntity, ReiseverlaufEntity):
    """Shows the composite image of the last trip; the state is when it last changed."""

    _attr_content_type = "image/png"

    def __init__(self, coordinator: ReiseverlaufDataUpdateCoordinator, description: ImageEntityDescription) -> None:
        """Initialize the entity."""
        ReiseverlaufEntity.__init__(self, coordinator, description)
        ImageEntity.__init__(self, coordinator.hass)
        self._path: Path | None = None
        self._key: tuple[Path | None, datetime | None] = (None, None)
        self._update_path()

    def image(self) -> bytes | None:
        """Return the PNG bytes; runs in the executor."""
        if self._path is None:
            return None
        try:
            return self._path.read_bytes()
        except OSError:
            return None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_path()
        super()._handle_coordinator_update()

    def _update_path(self) -> None:
        info = self.coordinator.data.last_export
        name = info.files.get(ExportFile.COMPOSITE) if info else None
        path = (
            media_base(self.coordinator.hass, self.coordinator.settings) / info.folder / name if info and name else None
        )
        key = (path, info.end if info else None)
        if key != self._key:
            self._key = key
            self._path = path
            self._cached_image = None
            self._attr_image_last_updated = dt_util.utcnow() if path is not None else None
