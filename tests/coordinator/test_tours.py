"""Tests for tours: two trips with a stay between them, combined afterwards (docs/features/feat-10-tour.md)."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import shutil

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events, async_fire_time_changed

from custom_components.reiseverlauftracker.const import DOMAIN, EVENT_TOUR
from custom_components.reiseverlauftracker.coordinator import ReiseverlaufDataUpdateCoordinator
from custom_components.reiseverlauftracker.coordinator.exports import ExportKind, read_export, write_metadata
from custom_components.reiseverlauftracker.coordinator.logbook import CostCategory, Occasion, Refill
from custom_components.reiseverlauftracker.export import ExportFile
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

DPLUS = "sensor.camper_dplus"
TRACKER = "device_tracker.camper_gps"
SPEED = "sensor.camper_speed"
IMAGE = "image.camper_gps_letzte_reise_gesamtbild"
METRES_PER_DEGREE_LAT = 111195.0


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


async def drive(hass: HomeAssistant, freezer: FrozenDateTimeFactory, start_m: float, metres: float) -> None:
    """Drive `metres` north from `start_m` with D+ on, then switch D+ off and wait until the trip ended."""
    hass.states.async_set(DPLUS, "ON")
    for step in range(1, 11):
        await advance(hass, freezer, timedelta(minutes=1))
        hass.states.async_set(SPEED, "60")
        set_position(hass, start_m + metres * step / 10)
    await advance(hass, freezer, timedelta(minutes=1))
    hass.states.async_set(SPEED, "0")
    hass.states.async_set(DPLUS, "OFF")
    await hass.async_block_till_done()
    await advance(hass, freezer, timedelta(minutes=61))
    await advance(hass, freezer, timedelta(seconds=5))


CHOICE = "select.camper_gps_export_auswahl"


@pytest.fixture
async def two_trips(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> ReiseverlaufDataUpdateCoordinator:
    """Drive 10 km north on 10 October, stand there two nights, drive back on the 12th."""
    await hass.config.async_set_time_zone("Europe/Berlin")
    hass.config.language = "de"
    freezer.move_to("2026-10-10 06:00:00+00:00")
    hass.states.async_set(DPLUS, "OFF")
    set_position(hass, 0)
    hass.states.async_set(SPEED, "0")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator: ReiseverlaufDataUpdateCoordinator = config_entry.runtime_data.coordinator
    book = coordinator.logbook.logbook
    book.add(dt_util.utcnow(), Occasion.MANUAL, odometer_km=34_000, fuel_percent=100, fuel=Refill(50, 90.0))
    await drive(hass, freezer, 0, 10_000)
    freezer.move_to("2026-10-11 09:00:00+00:00")
    book.add(dt_util.utcnow(), Occasion.MANUAL, fuel_percent=100, fuel=Refill(10, 18.0), odometer_km=34_010)
    freezer.move_to("2026-10-12 08:00:00+00:00")
    await drive(hass, freezer, 10_000, -10_000)
    assert len([i for i in coordinator.exports if i.automatic]) == 2
    return coordinator


async def create(hass: HomeAssistant, entry_id: str, **data) -> dict:
    return await hass.services.async_call(
        DOMAIN, "tour_erstellen", {"config_entry_id": entry_id, **data}, blocking=True, return_response=True
    )


PERIOD = {"von": "2026-10-10 07:00:00", "bis": "2026-10-12 12:00:00"}


async def test_create_tour_from_two_trips(
    hass: HomeAssistant, two_trips: ReiseverlaufDataUpdateCoordinator, config_entry: MockConfigEntry, media_dir: Path
) -> None:
    events = async_capture_events(hass, EVENT_TOUR)
    await two_trips.logbook.async_add_travel_cost(date(2026, 10, 11), CostCategory.PITCH, 35.0)

    response = await create(hass, config_entry.entry_id, **PERIOD)

    assert response["anlass"] == "erstellt"
    assert response["titel"] == "Camping Ziel · 10.–12.10.2026"
    assert response["ordner"] == "tour-2026-10-10-2026-10-12"
    assert response["naechte"] == 2
    assert response["tage"] == 3
    assert response["strecke_km"] == pytest.approx(20, abs=0.5)
    assert response["kosten"] == pytest.approx(90 + 18 + 35)
    assert len(response["reisen"]) == 2
    assert [e.data["anlass"] for e in events] == ["erstellt"]

    info = read_export(media_dir / "reiseverlauf", response["ordner"])
    assert info is not None
    assert info.kind is ExportKind.TOUR
    assert set(info.files) == {
        ExportFile.STATS,
        ExportFile.DAYS,
        ExportFile.GPX,
        ExportFile.MAP,
        ExportFile.COMPOSITE,
        ExportFile.RAW,
    }
    assert "10.–12.10.  Camping Ziel  2 Nächte" in info.stats_text
    assert "12.10.      Startort" in info.stats_text
    assert "Stellplatz" in info.stats_text

    tz = dt_util.get_default_time_zone()
    label = info.label(tz)
    assert label.startswith("10.10.–12.10.26 · Tour · ")
    assert label in hass.states.get(CHOICE).attributes["options"]
    await hass.services.async_call("select", "select_option", {"entity_id": CHOICE, "option": label}, blocking=True)
    attributes = hass.states.get(CHOICE).attributes
    assert attributes["art"] == "tour"
    assert attributes["reisekosten"] is None
    assert attributes["standorte"] == [
        {"nacht": "2026-10-10", "bis": "2026-10-12", "naechte": 2, "name": "Camping Ziel", "geaendert": False}
    ]
    assert {d["typ"] for d in attributes["downloads"]} >= {"days", "zip"}
    # The travel costs form saves costs without a trip while a tour is chosen.
    assert two_trips.cost_form.trip() is None


async def test_new_cost_renews_the_tour(
    hass: HomeAssistant,
    two_trips: ReiseverlaufDataUpdateCoordinator,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    created = await create(hass, config_entry.entry_id, **PERIOD)
    events = async_capture_events(hass, EVENT_TOUR)

    await two_trips.logbook.async_add_travel_cost(date(2026, 10, 12), CostCategory.TOLL, 12.5, country="AT")
    await two_trips.logbook.async_add_travel_cost(date(2026, 10, 20), CostCategory.TOLL, 99.0)  # after the tour
    await advance(hass, freezer, timedelta(seconds=31))

    assert [e.data["anlass"] for e in events] == ["aktualisiert"]
    assert events[0].data["kosten"] == pytest.approx(created["kosten"] + 12.5)
    assert events[0].data["kostenaufstellung"]["je_land"]["AT"] == 12.5
    tour = next(i for i in two_trips.exports if i.is_tour)
    assert tour.updated is not None
    assert "Maut" in tour.stats_text


async def test_change_title_and_place_name(
    hass: HomeAssistant, two_trips: ReiseverlaufDataUpdateCoordinator, config_entry: MockConfigEntry, media_dir: Path
) -> None:
    created = await create(hass, config_entry.entry_id, **PERIOD)

    response = await hass.services.async_call(
        DOMAIN,
        "tour_aendern",
        {
            "config_entry_id": config_entry.entry_id,
            "export": created["ordner"],
            "titel": "Werkstatt Ulm",
            "standorte": [{"nacht": "2026-10-11", "name": "Hof der Werkstatt"}],
        },
        blocking=True,
        return_response=True,
    )

    assert response["anlass"] == "aktualisiert"
    assert response["titel"] == "Werkstatt Ulm"
    tour = next(i for i in two_trips.exports if i.is_tour)
    assert tour.tour is not None
    assert {(n.name, n.name_changed) for n in tour.tour.nights} == {("Hof der Werkstatt", True)}
    folder = media_dir / "reiseverlauf" / created["ordner"]
    assert sorted(p.name for p in folder.iterdir()) == sorted([*tour.files.values(), "export.json"])
    assert all(name.startswith("werkstatt_ulm") for name in tour.files.values())

    # An empty title returns to the suggestion, now with the place named by hand.
    await hass.services.async_call(
        DOMAIN,
        "tour_aendern",
        {"config_entry_id": config_entry.entry_id, "export": created["ordner"], "titel": ""},
        blocking=True,
    )
    tour = next(i for i in two_trips.exports if i.is_tour)
    assert tour.title == "Hof der Werkstatt · 10.–12.10.2026"


async def test_tour_keeps_its_own_raw_data(
    hass: HomeAssistant, two_trips: ReiseverlaufDataUpdateCoordinator, config_entry: MockConfigEntry
) -> None:
    created = await create(hass, config_entry.entry_id, **PERIOD)
    trips = [i for i in two_trips.exports if i.automatic]
    await two_trips.async_remove_files(trips, {ExportFile.RAW})

    with pytest.raises(ServiceValidationError) as err:
        await create(hass, config_entry.entry_id, **PERIOD)
    assert err.value.translation_key == "tour_raw_missing"

    response = await hass.services.async_call(
        DOMAIN,
        "tour_aendern",
        {"config_entry_id": config_entry.entry_id, "export": created["ordner"], "titel": "Ohne Reisen"},
        blocking=True,
        return_response=True,
    )
    assert response["strecke_km"] == created["strecke_km"]


async def test_manual_exports_join_without_overlap(
    hass: HomeAssistant, two_trips: ReiseverlaufDataUpdateCoordinator, config_entry: MockConfigEntry, media_dir: Path
) -> None:
    base = media_dir / "reiseverlauf"
    first, second = sorted((i for i in two_trips.exports if i.automatic), key=lambda i: i.start)
    # The second trip was exported by hand, e.g. before the integration recorded trips.
    write_metadata(base, replace(second, automatic=False))
    # A manual export of the first trip overlaps it and must not count twice.
    shutil.copytree(base / first.folder, base / "2026-10-10_0805-0900")
    write_metadata(
        base,
        replace(first, folder="2026-10-10_0805-0900", start=first.start + timedelta(minutes=5), automatic=False),
    )
    # A manual export without raw data is left out instead of stopping the tour.
    (base / "2026-10-11_1000-1100").mkdir()
    files = {kind: name for kind, name in first.files.items() if kind is not ExportFile.RAW}
    write_metadata(
        base,
        replace(
            first,
            folder="2026-10-11_1000-1100",
            start=datetime(2026, 10, 11, 8, tzinfo=UTC),
            end=datetime(2026, 10, 11, 9, tzinfo=UTC),
            files=files,
            automatic=False,
        ),
    )
    await two_trips.async_refresh_exports()

    response = await create(hass, config_entry.entry_id, **PERIOD)

    assert response["reisen"] == [first.folder, second.folder]
    assert response["strecke_km"] == pytest.approx(20, abs=0.5)
    assert response["naechte"] == 2

    # The export selection marks manual exports and lists every export with its kind.
    options = hass.states.get(CHOICE).attributes["options"]
    second = next(i for i in two_trips.exports if i.folder == second.folder)
    assert two_trips.export_label(second).startswith("12.10.26 10:00 · Manuell · ")
    assert two_trips.export_label(second) in options
    assert not two_trips.export_label(first).count("Manuell")
    exports = {e["ordner"]: e for e in hass.states.get(CHOICE).attributes["exporte"]}
    assert exports[first.folder]["automatisch"] is True
    assert exports[first.folder]["art"] == "reise"
    assert exports[second.folder]["automatisch"] is False
    assert exports["2026-10-11_1000-1100"]["rohdaten"] is False
    assert exports[second.folder]["rohdaten"] is True
    assert exports[response["ordner"]]["art"] == "tour"
    assert exports[response["ordner"]]["auswahl"] in options
    assert exports[first.folder]["strecke_km"] == pytest.approx(10, abs=0.5)


async def test_no_trip_in_the_period(hass: HomeAssistant, two_trips, config_entry: MockConfigEntry) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await create(hass, config_entry.entry_id, von="2026-09-01 00:00:00", bis="2026-09-05 00:00:00")
    assert err.value.translation_key == "tour_no_trips"


async def test_form_creates_and_updates_a_tour(
    hass: HomeAssistant, two_trips: ReiseverlaufDataUpdateCoordinator, freezer: FrozenDateTimeFactory
) -> None:
    tz = dt_util.get_default_time_zone()
    first = min((i for i in two_trips.exports if i.automatic), key=lambda i: i.start)
    await hass.services.async_call(
        "select", "select_option", {"entity_id": CHOICE, "option": first.label(tz)}, blocking=True
    )
    assert hass.states.get("datetime.camper_gps_tour_von").state == first.start.isoformat()
    await hass.services.async_call(
        "datetime",
        "set_value",
        {"entity_id": "datetime.camper_gps_tour_bis", "datetime": datetime(2026, 10, 12, 12, tzinfo=tz)},
        blocking=True,
    )

    await hass.services.async_call("button", "press", {"entity_id": "button.camper_gps_tour_erstellen"}, blocking=True)

    tour = next(i for i in two_trips.exports if i.is_tour)
    assert hass.states.get(CHOICE).state == tour.label(tz)
    assert hass.states.get("text.camper_gps_tour_titel").state == tour.title

    await hass.services.async_call(
        "text", "set_value", {"entity_id": "text.camper_gps_tour_titel", "value": "Kurztrip"}, blocking=True
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.camper_gps_tour_aktualisieren"}, blocking=True
    )
    tour = next(i for i in two_trips.exports if i.is_tour)
    assert tour.title == "Kurztrip"
    assert hass.states.get(CHOICE).state == tour.label(tz)

    await hass.services.async_call(
        "select", "select_option", {"entity_id": CHOICE, "option": first.label(tz)}, blocking=True
    )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.camper_gps_tour_aktualisieren"}, blocking=True
        )
