"""
Export folders below the output directory and their metadata.

Every export lives in its own folder with an `export.json` that lists its files.
All functions here do blocking file I/O and must run in the executor.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any

from custom_components.reiseverlauftracker.export import ExportFile

METADATA_FILE = "export.json"
METADATA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ExportInfo:
    """What one export folder contains; also the "last trip" shown by the entities."""

    folder: str
    title: str
    start: datetime
    end: datetime
    distance_km: float
    driving_time: timedelta
    files: dict[ExportFile, str]
    stats_text: str
    automatic: bool

    @property
    def duration(self) -> timedelta:
        """Return the time from start to end."""
        return self.end - self.start

    def as_dict(self) -> dict[str, Any]:
        """Return the metadata as written to `export.json`."""
        return {
            "version": METADATA_VERSION,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "distance_km": self.distance_km,
            "driving_time_s": self.driving_time.total_seconds(),
            "files": {kind.value: name for kind, name in self.files.items()},
            "stats_text": self.stats_text,
            "automatic": self.automatic,
        }

    @classmethod
    def from_dict(cls, folder: str, data: dict[str, Any]) -> ExportInfo:
        """Rebuild the info from `export.json` of `folder`."""
        return cls(
            folder=folder,
            title=data["title"],
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]),
            distance_km=data["distance_km"],
            driving_time=timedelta(seconds=data["driving_time_s"]),
            files={ExportFile(kind): name for kind, name in data["files"].items() if kind in set(ExportFile)},
            stats_text=data["stats_text"],
            automatic=data.get("automatic", False),
        )


def write_metadata(base: Path, info: ExportInfo) -> None:
    """Write `export.json` into the folder of `info`."""
    (base / info.folder / METADATA_FILE).write_text(json.dumps(info.as_dict(), ensure_ascii=False), encoding="utf-8")


def read_export(base: Path, folder: str) -> ExportInfo | None:
    """Return the export in `folder`, or None if it has no readable metadata."""
    try:
        data = json.loads((base / folder / METADATA_FILE).read_text(encoding="utf-8"))
        return ExportInfo.from_dict(folder, data)
    except OSError, ValueError, KeyError, TypeError:
        return None


def list_exports(base: Path) -> list[ExportInfo]:
    """Return all exports below `base`, newest trip first."""
    if not base.is_dir():
        return []
    exports = [info for path in base.iterdir() if path.is_dir() and (info := read_export(base, path.name))]
    return sorted(exports, key=lambda info: info.start, reverse=True)


def remove_files(base: Path, folder: str, kinds: set[ExportFile]) -> ExportInfo | None:
    """
    Delete the listed file kinds of one export; the folder goes when nothing is left.

    Only files named in the metadata are touched, never anything else in the folder.

    Returns:
        The remaining export, or None once it is gone completely.

    """
    info = read_export(base, folder)
    if info is None:
        return None
    path = base / info.folder
    for kind in kinds & info.files.keys():
        (path / info.files[kind]).unlink(missing_ok=True)
    remaining = {kind: name for kind, name in info.files.items() if kind not in kinds}
    if not remaining:
        (path / METADATA_FILE).unlink(missing_ok=True)
        if not any(path.iterdir()):
            path.rmdir()
        return None
    updated = replace(info, files=remaining)
    write_metadata(base, updated)
    return updated
