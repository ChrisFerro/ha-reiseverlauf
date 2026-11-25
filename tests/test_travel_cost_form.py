"""Tests for the travel costs form and the reisekosten_* and keine_maut actions."""

from datetime import date, timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.reiseverlauftracker.const import DOMAIN, EXPORT_CHOICE_ALL
from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
from custom_components.reiseverlauftracker.coordinator.logbook import CostCategory
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.components.date import ATTR_DATE, SERVICE_SET_VALUE as SET_DATE
from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.components.select import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.components.text import SERVICE_SET_VALUE as SET_TEXT
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

DPLUS = "sensor.camper_dplus"
TRACKER = "device_tracker.camper_gps"
SPEED = "sensor.camper_speed"
METRES_PER_DEGREE_LAT = 111195.0

CATEGORY = "select.camper_gps_reisekosten_kategorie"
COUNTRY = "select.camper_gps_reisekosten_land"
AMOUNT = "number.camper_gps_reisekosten_betrag"
NOTE = "text.camper_gps_reisekosten_notiz"
DAY = "date.camper_gps_reisekosten_datum"
SAVE = "button.camper_gps_reisekosten_speichern"
NO_TOLL = "button.camper_gps_keine_maut"
CHOICE = "select.camper_gps_export_auswahl"


def set_position(hass: HomeAssistant, metres_north: float) -> None:
    """Move the tracker `metres_north` of the start point."""
    hass.states.async_set(
        TRACKER,
        "not_home",
        {"latitude": 50.0 + metres_north / METRES_PER_DEGREE_LAT, "longitude": 8.0, "gps_accuracy": 10},
    )


async def advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    """Move the clock forward and run the timers and tasks that became due."""
    freezer.tick(delta)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.fixture
async def trip(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> ReiseverlaufDataUpdateCoordinator:
    """Set up the integration and drive one 10 km trip from Germany into Austria."""
    freezer.move_to("2026-11-02 07:00:00+00:00")
    hass.config.language = "de"
    hass.states.async_set(DPLUS, "OFF")
    set_position(hass, 0)
    hass.states.async_set(SPEED, "0")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set(DPLUS, "ON")
    for step in range(1, 11):
        await advance(hass, freezer, timedelta(minutes=1))
        hass.states.async_set(SPEED, "60")
        set_position(hass, 1000 * step)
    await advance(hass, freezer, timedelta(minutes=1))
    hass.states.async_set(DPLUS, "OFF")
    await hass.async_block_till_done()
    await advance(hass, freezer, timedelta(minutes=61))
    await hass.async_block_till_done(wait_background_tasks=True)
    coordinator: ReiseverlaufDataUpdateCoordinator = config_entry.runtime_data.coordinator
    assert coordinator.last_export is not None
    assert coordinator.last_export.countries == ("DE", "AT")
    return coordinator


async def call(hass: HomeAssistant, platform: Platform, service: str, target: str, **data: object) -> None:
    """Call an entity service and wait for it."""
    await hass.services.async_call(platform, service, {ATTR_ENTITY_ID: target, **data}, blocking=True)


async def action(hass: HomeAssistant, name: str, coordinator: ReiseverlaufDataUpdateCoordinator, **data: object):
    """Call an action of the integration and return its response."""
    return await hass.services.async_call(
        DOMAIN,
        name,
        {"config_entry_id": coordinator.config_entry.entry_id, **data},
        blocking=True,
        return_response=name not in {"reisekosten_loeschen", "keine_maut"},
    )


async def test_toll_for_two_countries_of_the_chosen_trip(
    hass: HomeAssistant, trip: ReiseverlaufDataUpdateCoordinator
) -> None:
    info = trip.last_export
    assert info is not None
    country = hass.states.get(COUNTRY)
    assert country.attributes["options"][:2] == ["de", "at"]
    assert country.attributes["options"][-1] == "none"
    assert "fr" in country.attributes["options"]
    assert country.state == "at"
    assert country.attributes["laender_der_reise"] == ["DE", "AT"]
    assert hass.states.get(CATEGORY).state == "maut"
    assert hass.states.get(DAY).state == dt_util.as_local(info.start).date().isoformat()

    await call(hass, Platform.NUMBER, SERVICE_SET_VALUE, AMOUNT, **{ATTR_VALUE: 23.4})
    await call(hass, Platform.BUTTON, SERVICE_PRESS, SAVE)
    assert hass.states.get(AMOUNT).state == "unknown"
    assert hass.states.get(COUNTRY).state == "at"

    await call(hass, Platform.SELECT, SERVICE_SELECT_OPTION, COUNTRY, **{ATTR_OPTION: "it"})
    await call(hass, Platform.NUMBER, SERVICE_SET_VALUE, AMOUNT, **{ATTR_VALUE: 61.1})
    await call(hass, Platform.TEXT, SET_TEXT, NOTE, value="Brenner")
    await call(hass, Platform.BUTTON, SERVICE_PRESS, SAVE)

    costs = trip.logbook.logbook.travel_costs_of_trip(info.start)
    assert [(c.country, c.amount, c.category, c.note) for c in costs] == [
        ("AT", 23.4, CostCategory.TOLL, None),
        ("IT", 61.1, CostCategory.TOLL, "Brenner"),
    ]
    assert {c.day for c in costs} == {dt_util.as_local(info.start).date()}
    summary = hass.states.get(CHOICE).attributes["reisekosten"]
    assert summary["summen"] == {"maut": 84.5}
    assert summary["summe"] == 84.5
    assert [e["land"] for e in summary["eintraege"]] == ["AT", "IT"]
    assert trip.logbook.travel_csv_path.exists()


async def test_save_without_amount_is_rejected(hass: HomeAssistant, trip: ReiseverlaufDataUpdateCoordinator) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, Platform.BUTTON, SERVICE_PRESS, SAVE)

    assert err.value.translation_key == "travel_cost_without_amount"


async def test_no_toll_toggles_the_mark_of_the_chosen_trip(
    hass: HomeAssistant, trip: ReiseverlaufDataUpdateCoordinator
) -> None:
    await call(hass, Platform.BUTTON, SERVICE_PRESS, NO_TOLL)
    assert hass.states.get(CHOICE).attributes["reisekosten"]["keine_maut"] is True

    await call(hass, Platform.BUTTON, SERVICE_PRESS, NO_TOLL)
    assert hass.states.get(CHOICE).attributes["reisekosten"]["keine_maut"] is False

    await call(hass, Platform.SELECT, SERVICE_SELECT_OPTION, CHOICE, **{ATTR_OPTION: EXPORT_CHOICE_ALL})
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, Platform.BUTTON, SERVICE_PRESS, NO_TOLL)
    assert err.value.translation_key == "travel_cost_without_trip"


async def test_pitch_without_trip_on_a_chosen_day(hass: HomeAssistant, trip: ReiseverlaufDataUpdateCoordinator) -> None:
    await call(hass, Platform.SELECT, SERVICE_SELECT_OPTION, COUNTRY, **{ATTR_OPTION: "it"})
    await call(hass, Platform.SELECT, SERVICE_SELECT_OPTION, CHOICE, **{ATTR_OPTION: EXPORT_CHOICE_ALL})
    assert hass.states.get(CHOICE).attributes["reisekosten"] is None
    assert hass.states.get(COUNTRY).state == "none"
    await call(hass, Platform.SELECT, SERVICE_SELECT_OPTION, CATEGORY, **{ATTR_OPTION: "stellplatz"})
    await call(hass, Platform.DATE, SET_DATE, DAY, **{ATTR_DATE: date(2026, 11, 5)})
    await call(hass, Platform.NUMBER, SERVICE_SET_VALUE, AMOUNT, **{ATTR_VALUE: 18})
    await call(hass, Platform.BUTTON, SERVICE_PRESS, SAVE)

    [cost] = trip.logbook.logbook.travel_costs
    assert (cost.trip_start, cost.day, cost.category, cost.country) == (
        None,
        date(2026, 11, 5),
        CostCategory.PITCH,
        None,
    )

    # Another trip choice starts again at the trip's first day.
    info = trip.last_export
    assert info is not None
    label = info.label(dt_util.get_default_time_zone())
    await call(hass, Platform.SELECT, SERVICE_SELECT_OPTION, CHOICE, **{ATTR_OPTION: label})
    assert hass.states.get(DAY).state == dt_util.as_local(info.start).date().isoformat()


async def test_actions_add_change_and_delete_costs(
    hass: HomeAssistant, trip: ReiseverlaufDataUpdateCoordinator
) -> None:
    info = trip.last_export
    assert info is not None

    response = await action(
        hass, "reisekosten_eintragen", trip, reise=info.folder, kategorie="maut", betrag=23.4, land="at"
    )
    cost = response["eintrag"]
    first_day = dt_util.as_local(info.start).date().isoformat()
    assert (cost["datum"], cost["land"], cost["reise"]) == (first_day, "AT", info.start.isoformat())

    by_start = await action(
        hass, "reisekosten_eintragen", trip, reise=info.start.isoformat(), kategorie="faehre", betrag=85
    )
    assert by_start["eintrag"]["reise"] == info.start.isoformat()

    changed = await action(hass, "reisekosten_aendern", trip, eintrag=cost["id"], betrag=24.1, datum="2026-11-03")
    assert (changed["eintrag"]["betrag"], changed["eintrag"]["datum"]) == (24.1, "2026-11-03")

    await action(hass, "reisekosten_loeschen", trip, eintrag=cost["id"])
    assert [c.category for c in trip.logbook.logbook.travel_costs] == [CostCategory.FERRY]

    await action(hass, "keine_maut", trip, reise=info.folder)
    assert trip.logbook.logbook.toll_settled(info.start)


@pytest.mark.parametrize(
    ("data", "key"),
    [
        ({"kategorie": "maut", "betrag": 5}, "travel_cost_needs_day"),
        ({"reise": "nirgendwo", "kategorie": "maut", "betrag": 5}, "unknown_trip"),
        ({"datum": "2026-11-02", "kategorie": "maut", "betrag": 5, "land": "Austria"}, "invalid_travel_cost"),
    ],
)
async def test_invalid_actions_are_rejected(
    hass: HomeAssistant, trip: ReiseverlaufDataUpdateCoordinator, data: dict, key: str
) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await action(hass, "reisekosten_eintragen", trip, **data)

    assert err.value.translation_key == key
    assert trip.logbook.logbook.travel_costs == []


async def test_unknown_cost_is_rejected(hass: HomeAssistant, trip: ReiseverlaufDataUpdateCoordinator) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await action(hass, "reisekosten_loeschen", trip, eintrag="missing")

    assert err.value.translation_key == "unknown_travel_cost"


ENTRY = "select.camper_gps_reisekosten_eintrag"
UPDATE = "button.camper_gps_reisekosten_aendern"
REMOVE = "button.camper_gps_reisekosten_loeschen"


async def test_choosing_a_cost_fills_the_form_and_changing_stores_it(
    hass: HomeAssistant, trip: ReiseverlaufDataUpdateCoordinator
) -> None:
    info = trip.last_export
    assert info is not None
    await action(hass, "reisekosten_eintragen", trip, reise=info.folder, kategorie="maut", betrag=23.4, land="AT")
    await action(hass, "reisekosten_eintragen", trip, reise=info.folder, kategorie="vignette", betrag=12.5, land="SI")
    day = dt_util.as_local(info.start).date()
    trip.async_update_listeners()
    await hass.async_block_till_done()

    options = hass.states.get(ENTRY).attributes["options"]
    assert options[0] == "new"
    assert f"{day:%d.%m.} · Maut AT · 23,40 €" in options
    await call(
        hass, Platform.SELECT, SERVICE_SELECT_OPTION, ENTRY, **{ATTR_OPTION: f"{day:%d.%m.} · Vignette SI · 12,50 €"}
    )

    assert hass.states.get(CATEGORY).state == "vignette"
    assert hass.states.get(COUNTRY).state == "si"
    assert float(hass.states.get(AMOUNT).state) == 12.5
    assert hass.states.get(ENTRY).attributes["eintrag"]["land"] == "SI"
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, Platform.BUTTON, SERVICE_PRESS, SAVE)
    assert err.value.translation_key == "travel_cost_editing"

    await call(hass, Platform.NUMBER, SERVICE_SET_VALUE, AMOUNT, **{ATTR_VALUE: 15})
    await call(hass, Platform.TEXT, SET_TEXT, NOTE, value="10 Tage")
    await call(hass, Platform.BUTTON, SERVICE_PRESS, UPDATE)

    costs = trip.logbook.logbook.travel_costs_of_trip(info.start)
    assert [(c.category, c.amount, c.country, c.note) for c in costs] == [
        (CostCategory.TOLL, 23.4, "AT", None),
        (CostCategory.VIGNETTE, 15, "SI", "10 Tage"),
    ]
    assert hass.states.get(ENTRY).state == "new"
    assert hass.states.get(AMOUNT).state == "unknown"


async def test_deleting_removes_the_chosen_cost(hass: HomeAssistant, trip: ReiseverlaufDataUpdateCoordinator) -> None:
    info = trip.last_export
    assert info is not None
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, Platform.BUTTON, SERVICE_PRESS, REMOVE)
    assert err.value.translation_key == "no_entry_chosen"
    await action(hass, "reisekosten_eintragen", trip, reise=info.folder, kategorie="maut", betrag=23.4, land="AT")
    trip.async_update_listeners()
    await hass.async_block_till_done()
    label = hass.states.get(ENTRY).attributes["options"][1]

    await call(hass, Platform.SELECT, SERVICE_SELECT_OPTION, ENTRY, **{ATTR_OPTION: label})
    await call(hass, Platform.BUTTON, SERVICE_PRESS, REMOVE)

    assert trip.logbook.logbook.travel_costs == []
    assert hass.states.get(ENTRY).state == "new"


async def test_all_exports_lists_the_costs_without_a_trip(
    hass: HomeAssistant, trip: ReiseverlaufDataUpdateCoordinator
) -> None:
    info = trip.last_export
    assert info is not None
    await action(hass, "reisekosten_eintragen", trip, reise=info.folder, kategorie="maut", betrag=23.4, land="AT")
    await call(hass, Platform.SELECT, SERVICE_SELECT_OPTION, CHOICE, **{ATTR_OPTION: EXPORT_CHOICE_ALL})
    await action(
        hass, "reisekosten_eintragen", trip, datum=date(2026, 11, 3).isoformat(), kategorie="stellplatz", betrag=18
    )
    trip.async_update_listeners()
    await hass.async_block_till_done()

    options = hass.states.get(ENTRY).attributes["options"]
    assert len(options) == 2
    assert "Stellplatz · 18,00 €" in options[1]
