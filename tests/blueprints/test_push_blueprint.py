"""Tests for the push notification blueprint."""

from pathlib import Path
import shutil
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component

BLUEPRINT = Path(__file__).parents[2] / "blueprints" / "automation" / "reiseverlauftracker" / "benachrichtigung.yaml"
ENTRY_ID = "01TESTENTRY"

ENDED: dict[str, Any] = {
    "entry_id": ENTRY_ID,
    "fortgesetzt": False,
    "titel": "Hamburg – Kiel, 12.10.2026",
    "start": "2026-10-12T08:00:00+00:00",
    "ende": "2026-10-12T09:30:00+00:00",
    "strecke_km": 96.4,
    "fahrzeit_min": 72,
    "ordner": "2026-10-12_1000",
    "gesamtbild_url": "/media/local/reiseverlauf/2026-10-12_1000/hamburg_gesamt.png",
}


@pytest.fixture
async def phone(hass: HomeAssistant, tmp_path: Path) -> str:
    """Install the blueprint and register one phone with the companion app; return its device ID."""
    await hass.config.async_set_time_zone("Europe/Berlin")
    hass.config.config_dir = str(tmp_path)
    target = tmp_path / "blueprints" / "automation" / "reiseverlauftracker"
    target.mkdir(parents=True)
    shutil.copy(BLUEPRINT, target / BLUEPRINT.name)

    phone_entry = MockConfigEntry(domain="mobile_app")
    phone_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=phone_entry.entry_id, identifiers={("mobile_app", "pixel")}, name="Pixel 8"
    )
    return device.id


@pytest.fixture
def notify_calls(hass: HomeAssistant, phone: str) -> list[ServiceCall]:
    """Return the calls of the notify action of the phone."""
    return async_mock_service(hass, "notify", "mobile_app_pixel_8")


async def setup_automation(hass: HomeAssistant, phone: str, **inputs: Any) -> None:
    """Create an automation from the blueprint."""
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "use_blueprint": {
                    "path": "reiseverlauftracker/benachrichtigung.yaml",
                    "input": {"fahrzeug": ENTRY_ID, "geraete": [phone], **inputs},
                }
            }
        },
    )


async def test_trip_end_notification(hass: HomeAssistant, phone: str, notify_calls: list[ServiceCall]) -> None:
    await setup_automation(hass, phone)

    hass.bus.async_fire("reiseverlauftracker_beendet", ENDED)
    await hass.async_block_till_done()

    assert len(notify_calls) == 1
    data = notify_calls[0].data
    assert data["title"] == "Reise beendet: Hamburg – Kiel, 12.10.2026"
    assert data["message"] == "96,4 km · 1 h 12 min Fahrzeit · 10:00–11:30 Uhr"
    assert data["data"] == {
        "tag": "reiseverlauf_2026-10-12_1000",
        "image": ENDED["gesamtbild_url"],
        "clickAction": ENDED["gesamtbild_url"],
        "url": ENDED["gesamtbild_url"],
    }


async def test_resumed_trip_over_several_days_without_image(
    hass: HomeAssistant, phone: str, notify_calls: list[ServiceCall]
) -> None:
    await setup_automation(hass, phone, mit_bild=False)

    hass.bus.async_fire(
        "reiseverlauftracker_beendet", {**ENDED, "fortgesetzt": True, "ende": "2026-10-13T16:05:00+00:00"}
    )
    await hass.async_block_till_done()

    data = notify_calls[0].data
    assert data["title"] == "Reise aktualisiert: Hamburg – Kiel, 12.10.2026"
    assert data["message"] == "96,4 km · 1 h 12 min Fahrzeit · 12.10. 10:00 – 13.10. 18:05 Uhr"
    assert "image" not in data["data"]
    assert data["data"]["tag"] == "reiseverlauf_2026-10-12_1000"


async def test_start_notification_only_for_new_trips(
    hass: HomeAssistant, phone: str, notify_calls: list[ServiceCall]
) -> None:
    await setup_automation(hass, phone)

    start = {"entry_id": ENTRY_ID, "start": "2026-10-12T08:00:00+00:00"}
    hass.bus.async_fire("reiseverlauftracker_gestartet", {**start, "resumed": True})
    hass.bus.async_fire("reiseverlauftracker_gestartet", {**start, "resumed": False})
    await hass.async_block_till_done()

    assert len(notify_calls) == 1
    assert notify_calls[0].data["title"] == "Reise gestartet"
    assert notify_calls[0].data["message"] == "um 10:00 Uhr"


async def test_switches_and_other_vehicles(hass: HomeAssistant, phone: str, notify_calls: list[ServiceCall]) -> None:
    await setup_automation(hass, phone, bei_start=False)

    hass.bus.async_fire(
        "reiseverlauftracker_gestartet", {"entry_id": ENTRY_ID, "start": ENDED["start"], "resumed": False}
    )
    hass.bus.async_fire("reiseverlauftracker_exportiert", ENDED)
    hass.bus.async_fire("reiseverlauftracker_beendet", {**ENDED, "entry_id": "other"})
    await hass.async_block_till_done()

    assert notify_calls == []


async def test_manual_export_when_enabled(hass: HomeAssistant, phone: str, notify_calls: list[ServiceCall]) -> None:
    await setup_automation(hass, phone, bei_export=True)

    hass.bus.async_fire("reiseverlauftracker_exportiert", ENDED)
    await hass.async_block_till_done()

    assert notify_calls[0].data["title"] == "Export fertig: Hamburg – Kiel, 12.10.2026"
