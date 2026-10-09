"""Read positions, speed and altitude of a period from the recorder."""

from datetime import datetime
from typing import TYPE_CHECKING

from custom_components.reiseverlauftracker.export import StepSeries, TrackPoint, decode_speed
from homeassistant.components.recorder import history
from homeassistant.const import ATTR_GPS_ACCURACY, ATTR_LATITUDE, ATTR_LONGITUDE
from homeassistant.core import State
from homeassistant.helpers.recorder import get_instance

if TYPE_CHECKING:
    from custom_components.reiseverlauftracker.settings import ReiseverlaufSettings
    from homeassistant.core import HomeAssistant


async def async_load_period(
    hass: HomeAssistant,
    settings: ReiseverlaufSettings,
    start: datetime,
    end: datetime,
) -> tuple[list[TrackPoint], StepSeries | None, StepSeries | None]:
    """Return positions, speed and altitude between `start` and `end` in the shape `export_trip()` takes."""
    entity_ids = [settings.tracker_entity, settings.speed_entity]
    if settings.altitude_entity:
        entity_ids.append(settings.altitude_entity)
    states = await get_instance(hass).async_add_executor_job(
        history.get_significant_states, hass, start, end, entity_ids, None, True, False, False, False
    )
    positions = [point for state in states.get(settings.tracker_entity, []) if (point := _point(state)) is not None]
    speed = [
        (t, kmh) for t, v in _values(states.get(settings.speed_entity, [])) if (kmh := decode_speed(v)) is not None
    ]
    altitude = _values(states.get(settings.altitude_entity, [])) if settings.altitude_entity else []
    return positions, StepSeries(speed) if speed else None, StepSeries(altitude) if altitude else None


def _point(state: State | dict) -> TrackPoint | None:
    if not isinstance(state, State):
        return None
    try:
        lat = float(state.attributes[ATTR_LATITUDE])
        lon = float(state.attributes[ATTR_LONGITUDE])
    except KeyError, TypeError, ValueError:
        return None
    accuracy = state.attributes.get(ATTR_GPS_ACCURACY)
    return TrackPoint(
        time=state.last_updated,
        lat=lat,
        lon=lon,
        accuracy=float(accuracy) if isinstance(accuracy, int | float) else None,
    )


def _values(states: list[State | dict]) -> list[tuple[datetime, float]]:
    values: list[tuple[datetime, float]] = []
    for state in states:
        if not isinstance(state, State):
            continue
        try:
            values.append((state.last_updated, float(state.state)))
        except ValueError:
            continue
    return values
