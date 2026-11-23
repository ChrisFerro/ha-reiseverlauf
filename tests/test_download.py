"""Tests for the download views: export files, ZIP per export and the logbook CSV."""

from datetime import UTC, date, datetime, timedelta
import io
from pathlib import Path
import zipfile

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.reiseverlauftracker.const import DOMAIN, EXPORT_CHOICE_ALL
from custom_components.reiseverlauftracker.coordinator.download_links import (
    ATTR_DOWNLOADS,
    LINK_VALIDITY,
    RENEW_INTERVAL,
    file_path,
    logbook_path,
    zip_path,
)
from custom_components.reiseverlauftracker.coordinator.exports import ExportInfo, write_metadata
from custom_components.reiseverlauftracker.coordinator.logbook import CostCategory
from custom_components.reiseverlauftracker.export import ExportFile
from homeassistant.components.http.auth import DATA_SIGN_SECRET, async_sign_path
from homeassistant.core import HomeAssistant

FOLDER = "2026-10-12_1000"
FILES = {
    ExportFile.COMPOSITE: "trip_gesamt.png",
    ExportFile.GPX: "trip.gpx",
    ExportFile.STATS: "trip_statistik.txt",
    ExportFile.RAW: "trip_rohdaten.json",
}


def make_export(media_dir: Path, folder: str = FOLDER) -> Path:
    """Write an export with one small file per kind and return its folder."""
    path = media_dir / "reiseverlauf" / folder
    path.mkdir(parents=True)
    for name in FILES.values():
        (path / name).write_text(f"content of {name}", encoding="utf-8")
    start = datetime(2026, 10, 12, 8, tzinfo=UTC)
    info = ExportInfo(
        folder=folder,
        title="Hamburg – Kiel",
        start=start,
        end=start + timedelta(hours=2),
        distance_km=98.0,
        driving_time=timedelta(minutes=80),
        files=dict(FILES),
        stats_text="Hamburg – Kiel\n",
        automatic=True,
    )
    write_metadata(media_dir / "reiseverlauf", info)
    return path


async def setup(hass: HomeAssistant, config_entry: MockConfigEntry) -> MockConfigEntry:
    """Set up the entry after the export folders exist."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def test_file_is_served_as_attachment(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path, hass_client: ClientSessionGenerator
) -> None:
    make_export(media_dir)
    entry = await setup(hass, config_entry)
    client = await hass_client()

    response = await client.get(file_path(entry.entry_id, FOLDER, "trip.gpx"))

    assert response.status == 200
    assert await response.text() == "content of trip.gpx"
    assert response.headers["Content-Type"] == "application/gpx+xml"
    assert response.headers["Content-Disposition"].startswith('attachment; filename="trip.gpx"')


async def test_text_files_have_charset(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path, hass_client: ClientSessionGenerator
) -> None:
    make_export(media_dir)
    entry = await setup(hass, config_entry)
    client = await hass_client()

    response = await client.get(file_path(entry.entry_id, FOLDER, "trip_statistik.txt"))

    assert response.headers["Content-Type"] == "text/plain; charset=utf-8"


async def test_needs_login(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path, hass_client_no_auth: ClientSessionGenerator
) -> None:
    make_export(media_dir)
    entry = await setup(hass, config_entry)
    client = await hass_client_no_auth()

    for path in (
        file_path(entry.entry_id, FOLDER, "trip.gpx"),
        zip_path(entry.entry_id, FOLDER),
        logbook_path(entry.entry_id),
    ):
        assert (await client.get(path)).status == 401


async def test_only_listed_files_are_served(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path, hass_client: ClientSessionGenerator
) -> None:
    folder = make_export(media_dir)
    (folder / "secret.txt").write_text("not listed", encoding="utf-8")
    (media_dir / "outside.txt").write_text("outside", encoding="utf-8")
    entry = await setup(hass, config_entry)
    client = await hass_client()

    for path in (
        file_path(entry.entry_id, FOLDER, "secret.txt"),
        file_path(entry.entry_id, FOLDER, "export.json"),
        file_path(entry.entry_id, FOLDER, "../../outside.txt"),
        file_path(entry.entry_id, "..", "outside.txt"),
        file_path(entry.entry_id, "unknown", "trip.gpx"),
        file_path("unknown_entry", FOLDER, "trip.gpx"),
        zip_path(entry.entry_id, "unknown"),
    ):
        # Home Assistant's security filter already rejects "../" with 400 before the view sees it.
        assert (await client.get(path)).status in {400, 404}, path


async def test_deleted_file_is_not_found(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path, hass_client: ClientSessionGenerator
) -> None:
    folder = make_export(media_dir)
    entry = await setup(hass, config_entry)
    (folder / "trip.gpx").unlink()
    client = await hass_client()

    assert (await client.get(file_path(entry.entry_id, FOLDER, "trip.gpx"))).status == 404


async def test_unloaded_entry_serves_nothing(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path, hass_client: ClientSessionGenerator
) -> None:
    make_export(media_dir)
    entry = await setup(hass, config_entry)
    await hass.config_entries.async_unload(entry.entry_id)
    client = await hass_client()

    assert (await client.get(file_path(entry.entry_id, FOLDER, "trip.gpx"))).status == 404


async def test_zip_holds_all_existing_files(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path, hass_client: ClientSessionGenerator
) -> None:
    folder = make_export(media_dir)
    (folder / "trip_rohdaten.json").unlink()
    entry = await setup(hass, config_entry)
    client = await hass_client()

    response = await client.get(zip_path(entry.entry_id, FOLDER))

    assert response.status == 200
    assert response.headers["Content-Type"] == "application/zip"
    assert response.headers["Content-Disposition"].startswith(f'attachment; filename="{FOLDER}.zip"')
    with zipfile.ZipFile(io.BytesIO(await response.read())) as zf:
        assert sorted(zf.namelist()) == sorted(
            f"{FOLDER}/{name}" for name in ("trip_gesamt.png", "trip.gpx", "trip_statistik.txt")
        )
        assert zf.read(f"{FOLDER}/trip.gpx") == b"content of trip.gpx"


async def test_zip_without_files_is_not_found(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path, hass_client: ClientSessionGenerator
) -> None:
    folder = make_export(media_dir)
    for name in FILES.values():
        (folder / name).unlink()
    entry = await setup(hass, config_entry)
    client = await hass_client()

    assert (await client.get(zip_path(entry.entry_id, FOLDER))).status == 404


async def test_logbook_csv(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path, hass_client: ClientSessionGenerator
) -> None:
    entry = await setup(hass, config_entry)
    client = await hass_client()
    assert (await client.get(logbook_path(entry.entry_id))).status == 404

    csv = media_dir / "reiseverlauf" / "fahrtenbuch.csv"
    csv.parent.mkdir(parents=True, exist_ok=True)
    csv.write_text("Datum;Kilometerstand\n", encoding="utf-8")
    response = await client.get(logbook_path(entry.entry_id))

    assert response.status == 200
    assert response.headers["Content-Type"] == "text/csv; charset=utf-8"
    assert response.headers["Content-Disposition"].startswith('attachment; filename="fahrtenbuch.csv"')
    assert await response.text() == "Datum;Kilometerstand\n"


async def test_non_ascii_names_keep_utf8_filename(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path, hass_client: ClientSessionGenerator
) -> None:
    folder = make_export(media_dir)
    (folder / "trip.gpx").rename(folder / "Lübeck.gpx")
    info_path = folder / "export.json"
    info_path.write_text(info_path.read_text(encoding="utf-8").replace("trip.gpx", "Lübeck.gpx"), encoding="utf-8")
    entry = await setup(hass, config_entry)
    client = await hass_client()

    response = await client.get(file_path(entry.entry_id, FOLDER, "Lübeck.gpx"))

    assert response.status == 200
    assert "filename*=UTF-8''L%C3%BCbeck.gpx" in response.headers["Content-Disposition"]


LAST_TRIP = "sensor.camper_gps_last_trip"
CHOICE = "select.camper_gps_export_selection"
LOGBOOK_ENTRY = "sensor.camper_gps_logbook_entry"


def downloads(hass: HomeAssistant, entity_id: str) -> list[dict[str, str]]:
    """Return the `downloads` attribute of an entity."""
    state = hass.states.get(entity_id)
    assert state is not None
    return state.attributes[ATTR_DOWNLOADS]


async def test_signed_links_work_without_login(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    media_dir: Path,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    make_export(media_dir)
    await setup(hass, config_entry)
    client = await hass_client_no_auth()

    links = downloads(hass, LAST_TRIP)

    assert [(link["typ"], link["name"]) for link in links] == [
        *((kind.value, name) for kind, name in FILES.items()),
        ("zip", f"{FOLDER}.zip"),
    ]
    for link in links:
        assert "authSig=" in link["url"]
        assert (await client.get(link["url"])).status == 200, link["name"]


async def test_tampered_link_is_rejected(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    media_dir: Path,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    make_export(media_dir)
    await setup(hass, config_entry)
    client = await hass_client_no_auth()
    gpx = next(link["url"] for link in downloads(hass, LAST_TRIP) if link["typ"] == "gpx")

    assert (await client.get(gpx.replace("trip.gpx", "trip_statistik.txt"))).status == 401


async def test_links_expire_after_a_day(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    media_dir: Path,
    hass_client_no_auth: ClientSessionGenerator,
    freezer: FrozenDateTimeFactory,
) -> None:
    make_export(media_dir)
    await setup(hass, config_entry)
    client = await hass_client_no_auth()
    gpx = next(link["url"] for link in downloads(hass, LAST_TRIP) if link["typ"] == "gpx")

    freezer.tick(LINK_VALIDITY + timedelta(minutes=1))

    assert (await client.get(gpx)).status == 401


async def test_links_are_renewed_every_hour(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    media_dir: Path,
    freezer: FrozenDateTimeFactory,
) -> None:
    make_export(media_dir)
    await setup(hass, config_entry)
    first = downloads(hass, LAST_TRIP)

    freezer.tick(timedelta(minutes=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert downloads(hass, LAST_TRIP) == first

    freezer.tick(RENEW_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    renewed = downloads(hass, LAST_TRIP)
    assert [link["name"] for link in renewed] == [link["name"] for link in first]
    assert renewed[0]["url"] != first[0]["url"]


async def test_export_choice_lists_links_of_the_chosen_export(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path
) -> None:
    make_export(media_dir)
    await setup(hass, config_entry)

    assert [link["name"] for link in downloads(hass, CHOICE)][-1] == f"{FOLDER}.zip"

    await hass.services.async_call(
        "select", "select_option", {"entity_id": CHOICE, "option": EXPORT_CHOICE_ALL}, blocking=True
    )
    assert downloads(hass, CHOICE) == []


async def test_logbook_entry_lists_the_csv(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    entry = await setup(hass, config_entry)
    assert downloads(hass, LOGBOOK_ENTRY) == []

    await hass.services.async_call(
        DOMAIN,
        "fahrtenbuch_eintragen",
        {"config_entry_id": entry.entry_id, "kilometerstand": 34299},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()

    links = downloads(hass, LOGBOOK_ENTRY)
    assert [(link["typ"], link["name"]) for link in links] == [("csv", "fahrtenbuch.csv")]
    client = await hass_client_no_auth()
    response = await client.get(links[0]["url"])
    assert response.status == 200
    assert "34299" in await response.text()


async def test_links_are_not_recorded(hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path) -> None:
    make_export(media_dir)
    await setup(hass, config_entry)

    for entity_id in (LAST_TRIP, CHOICE, LOGBOOK_ENTRY):
        state = hass.states.get(entity_id)
        assert state is not None
        assert ATTR_DOWNLOADS in state.attributes
        component = hass.data["entity_components"][entity_id.split(".")[0]]
        entity = component.get_entity(entity_id)
        assert entity is not None
        assert ATTR_DOWNLOADS in entity._unrecorded_attributes, entity_id  # noqa: SLF001


async def test_responses_are_not_cached(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path, hass_client: ClientSessionGenerator
) -> None:
    make_export(media_dir)
    entry = await setup(hass, config_entry)
    csv = media_dir / "reiseverlauf" / "fahrtenbuch.csv"
    csv.write_text("Datum\n", encoding="utf-8")
    client = await hass_client()

    for path in (
        file_path(entry.entry_id, FOLDER, "trip.gpx"),
        zip_path(entry.entry_id, FOLDER),
        logbook_path(entry.entry_id),
    ):
        response = await client.get(path)
        assert response.status == 200, path
        assert response.headers["Cache-Control"] == "no-store, private", path


async def test_links_stop_working_after_a_restart(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    media_dir: Path,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    make_export(media_dir)
    await setup(hass, config_entry)
    client = await hass_client_no_auth()
    gpx = next(link["url"] for link in downloads(hass, LAST_TRIP) if link["typ"] == "gpx")
    assert (await client.get(gpx)).status == 200

    # A restart starts with a new signing secret; dropping it here has the same effect.
    hass.data.pop(DATA_SIGN_SECRET)
    async_sign_path(hass, "/", timedelta(seconds=1), use_content_user=True)

    assert (await client.get(gpx)).status == 401


async def test_head_answers_without_body(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    media_dir: Path,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    make_export(media_dir)
    entry = await setup(hass, config_entry)
    (media_dir / "reiseverlauf" / "fahrtenbuch.csv").write_text("Datum\n", encoding="utf-8")
    client = await hass_client_no_auth()
    links = [
        *downloads(hass, LAST_TRIP),
        {"url": entry.runtime_data.coordinator.download_links.sign(logbook_path(entry.entry_id))},
    ]

    for link in links:
        get = await client.get(link["url"])
        head = await client.head(link["url"])
        assert head.status == 200, link["url"]
        assert head.headers["Content-Type"] == get.headers["Content-Type"]
        assert head.headers["Content-Length"] == get.headers["Content-Length"]
        assert await head.read() == b""


async def test_travel_costs_csv_is_listed_and_served(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    entry = await setup(hass, config_entry)
    keeper = entry.runtime_data.coordinator.logbook
    await keeper.async_add_travel_cost(date(2026, 11, 2), CostCategory.TOLL, 23.4, country="AT")
    await hass.async_block_till_done()

    links = downloads(hass, LOGBOOK_ENTRY)
    assert [(link["typ"], link["name"]) for link in links] == [("csv", "reisekosten.csv")]
    client = await hass_client_no_auth()
    response = await client.get(links[0]["url"])
    assert response.status == 200
    assert response.headers["Content-Disposition"].startswith('attachment; filename="reisekosten.csv"')
    assert "AT" in await response.text()
