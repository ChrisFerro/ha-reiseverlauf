"""
Diagnostics support for reiseverlauftracker.

https://developers.home-assistant.io/docs/core/integration_diagnostics
"""

from typing import TYPE_CHECKING, Any

from homeassistant.helpers.redact import async_redact_data

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import ReiseverlaufConfigEntry

POSITION_KEYS = {"last_position", "start_position", "motion_anchor"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ReiseverlaufConfigEntry,
) -> dict[str, Any]:
    """
    Return diagnostics for a config entry.

    Positions are redacted: they reveal where the vehicle is parked.

    Returns:
        The entry configuration, the detector state, the trip status and the exports.

    """
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data
    log = coordinator.log
    return {
        "entry": {
            "version": entry.version,
            "minor_version": entry.minor_version,
            "state": str(entry.state),
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "detector": async_redact_data(coordinator.detector.as_dict(), POSITION_KEYS),
        "trip": {
            "status": data.status.value,
            "active": data.active,
            "trip_start": data.trip_start.isoformat() if data.trip_start else None,
            "expected_end": data.expected_end.isoformat() if data.expected_end else None,
            "merge_until": data.merge_until.isoformat() if data.merge_until else None,
            "recorded_positions": len(log.positions) if log else 0,
            "recorded_speeds": len(log.speed) if log else 0,
            "recorded_altitudes": len(log.altitude) if log else 0,
        },
        "exports": [
            {
                "folder": info.folder,
                "automatic": info.automatic,
                "start": info.start.isoformat(),
                "end": info.end.isoformat(),
                "files": sorted(kind.value for kind in info.files),
            }
            for info in data.exports
        ],
        "last_export": data.last_export.folder if data.last_export else None,
        "export_choice": coordinator.current_export_choice(),
    }
