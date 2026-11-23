"""Tests for the logbook reminder blueprint."""

from datetime import timedelta
from pathlib import Path
import shutil
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, async_mock_service

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

BLUEPRINT = Path(__file__).parents[2] / "blueprints" / "automation" / "reiseverlauftracker" / "fahrtenbuch.yaml"
ENTRY_ID = "01TESTENTRY"
TIME = "2026-10-12T08:00:00.123456+00:00"
ACTION = f"REISEVERLAUF_FAHRTENBUCH_{ENTRY_ID}_{TIME}"
TAG = f"reiseverlauf_fahrtenbuch_{ENTRY_ID}"

OCCASION: dict[str, Any] = {
    "entry_id": ENTRY_ID,
    "anlass": "reisestart",
    "zeit": TIME,
    "ort": "Kiel",
    "reise_start": "2026-10-12T08:00:00+00:00",
    "halt_start": None,
    "vorschlag": {"kilometerstand": 34439.0, "kraftstoff": 72.4, "gas_1": 81.0, "gas_2": 60.0},
}
SAVED: dict[str, Any] = {
    "eintrag": {
        "id": "abc",
        "anlass": "reisestart",
        "kilometerstand": 34440.0,
        "kraftstoff": 70.0,
        "gas_1": 80.0,
        "gas_2": None,
    }
}


@pytest.fixture
def expected_lingering_timers() -> bool:
    """Allow the timer of the toll reminder's time trigger, which stays armed after each test."""
    return True


@pytest.fixture
async def phone(hass: HomeAssistant, tmp_path: Path) -> str:
    """Install the blueprint and register one phone with the companion app; return its device ID."""
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
                    "path": "reiseverlauftracker/fahrtenbuch.yaml",
                    "input": {"fahrzeug": ENTRY_ID, "geraete": [phone], **inputs},
                }
            }
        },
    )


async def test_trip_start_reminder_with_button(
    hass: HomeAssistant, phone: str, notify_calls: list[ServiceCall]
) -> None:
    await setup_automation(hass, phone)

    hass.bus.async_fire("reiseverlauftracker_fahrtenbuch", OCCASION)
    await hass.async_block_till_done()

    assert len(notify_calls) == 1
    data = notify_calls[0].data
    assert data["title"] == "Fahrtenbuch: Reisebeginn in Kiel"
    assert data["message"] == "34439 km · Diesel 72 % · Gas 81 % / 60 %"
    assert data["data"] == {
        "tag": TAG,
        "clickAction": "/dashboard-reiseverlauf/fahrtenbuch",
        "url": "/dashboard-reiseverlauf/fahrtenbuch",
        "actions": [{"action": ACTION, "title": "Übernehmen"}],
    }


async def test_stop_reminder_without_values_button_or_link(
    hass: HomeAssistant, phone: str, notify_calls: list[ServiceCall]
) -> None:
    await setup_automation(hass, phone, mit_knopf=False, dashboard="")

    empty = {"kilometerstand": None, "kraftstoff": None, "gas_1": None, "gas_2": None}
    hass.bus.async_fire(
        "reiseverlauftracker_fahrtenbuch", {**OCCASION, "anlass": "halt", "ort": None, "vorschlag": empty}
    )
    await hass.async_block_till_done()

    data = notify_calls[0].data
    assert data["title"] == "Fahrtenbuch: Halt"
    assert data["message"] == "Noch keine Werte – bitte im Formular eintragen"
    assert data["data"] == {"tag": TAG}


async def test_switches_and_other_vehicles(hass: HomeAssistant, phone: str, notify_calls: list[ServiceCall]) -> None:
    await setup_automation(hass, phone, bei_start=False)

    hass.bus.async_fire("reiseverlauftracker_fahrtenbuch", OCCASION)
    hass.bus.async_fire("reiseverlauftracker_fahrtenbuch", {**OCCASION, "anlass": "halt", "entry_id": "other"})
    await hass.async_block_till_done()
    assert notify_calls == []

    hass.bus.async_fire("reiseverlauftracker_fahrtenbuch", {**OCCASION, "anlass": "halt"})
    await hass.async_block_till_done()
    assert len(notify_calls) == 1


async def test_button_saves_the_occasion_and_confirms(
    hass: HomeAssistant, phone: str, notify_calls: list[ServiceCall]
) -> None:
    save_calls = async_mock_service(hass, "reiseverlauftracker", "fahrtenbuch_speichern", response=SAVED)
    await setup_automation(hass, phone)

    hass.bus.async_fire("mobile_app_notification_action", {"action": "SOMETHING_ELSE"})
    hass.bus.async_fire("mobile_app_notification_action", {"action": ACTION.replace(ENTRY_ID, "OTHER")})
    await hass.async_block_till_done()
    assert save_calls == []

    hass.bus.async_fire("mobile_app_notification_action", {"action": ACTION})
    await hass.async_block_till_done()

    assert len(save_calls) == 1
    assert save_calls[0].data == {"config_entry_id": ENTRY_ID, "anlass_zeit": TIME}
    assert len(notify_calls) == 1
    data = notify_calls[0].data
    assert data["title"] == "Fahrtenbuch gespeichert"
    assert data["message"] == "34440 km · Diesel 70 % · Gas 80 %"
    assert data["data"]["tag"] == TAG
    assert "actions" not in data["data"]


async def test_button_for_an_occasion_that_is_gone_confirms_nothing(
    hass: HomeAssistant, phone: str, notify_calls: list[ServiceCall]
) -> None:
    async_mock_service(
        hass,
        "reiseverlauftracker",
        "fahrtenbuch_speichern",
        raise_exception=ServiceValidationError("gone"),
        supports_response=SupportsResponse.OPTIONAL,
    )
    await setup_automation(hass, phone)

    hass.bus.async_fire("mobile_app_notification_action", {"action": ACTION})
    await hass.async_block_till_done()

    assert notify_calls == []


TRIPS: list[dict[str, Any]] = [
    {
        "titel": "Ulm – Bozen, 22.11.2026",
        "start": "2026-11-22T07:00:00+00:00",
        "ordner": "2026-11-22_0800",
        "laender": ["AT", "IT"],
    },
    {"titel": "Lyon – Nîmes, 02.11.2026", "start": "2026-11-02T07:00:00+00:00", "ordner": "x", "laender": ["FR"]},
]


def open_toll_sensor(hass: HomeAssistant, entry_id: str, trips: list[dict[str, Any]]) -> None:
    """Register the open toll sensor of a vehicle and set its state."""
    entry = MockConfigEntry(domain="reiseverlauftracker", entry_id=entry_id)
    entry.add_to_hass(hass)
    entity = er.async_get(hass).async_get_or_create(
        "sensor", "reiseverlauftracker", f"{entry_id}_open_toll", config_entry=entry
    )
    hass.states.async_set(entity.entity_id, str(len(trips)), {"reisen": trips})


async def at_nine(hass: HomeAssistant, freezer: FrozenDateTimeFactory, day: str) -> None:
    """Let the clock reach 09:00 local time on `day`."""
    nine = dt_util.parse_datetime(f"{day} 09:00:00")
    assert nine is not None
    freezer.move_to(nine.replace(tzinfo=dt_util.get_default_time_zone()) + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_toll_reminder_on_the_first_of_the_month(
    hass: HomeAssistant, phone: str, notify_calls: list[ServiceCall], freezer: FrozenDateTimeFactory
) -> None:
    open_toll_sensor(hass, ENTRY_ID, TRIPS)
    open_toll_sensor(hass, "other", [TRIPS[1]])
    freezer.move_to("2026-11-30 12:00:00+00:00")
    await setup_automation(hass, phone)

    await at_nine(hass, freezer, "2026-12-01")

    assert len(notify_calls) == 1
    data = notify_calls[0].data
    assert data["title"] == "Maut eintragen"
    assert data["message"] == ("2 Reisen ohne Maut: Ulm – Bozen, 22.11.2026 (AT, IT); Lyon – Nîmes, 02.11.2026 (FR)")
    assert data["data"] == {
        "tag": f"reiseverlauf_maut_{ENTRY_ID}",
        "clickAction": "/dashboard-reiseverlauf/reisekosten",
        "url": "/dashboard-reiseverlauf/reisekosten",
    }


@pytest.mark.parametrize(
    ("day", "trips", "inputs"),
    [
        ("2026-12-02", TRIPS, {}),
        ("2026-12-01", [], {}),
        ("2026-12-01", TRIPS, {"maut_erinnerung": False}),
    ],
)
async def test_no_toll_reminder(
    hass: HomeAssistant,
    phone: str,
    notify_calls: list[ServiceCall],
    freezer: FrozenDateTimeFactory,
    day: str,
    trips: list[dict[str, Any]],
    inputs: dict[str, Any],
) -> None:
    open_toll_sensor(hass, ENTRY_ID, trips)
    freezer.move_to("2026-11-30 12:00:00+00:00")
    await setup_automation(hass, phone, **inputs)

    await at_nine(hass, freezer, day)

    assert notify_calls == []
