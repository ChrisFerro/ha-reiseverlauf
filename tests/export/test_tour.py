"""Tests for tours: night places, overview by day and place, costs, estimate and the exported files."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image
import pytest

from custom_components.reiseverlauftracker.export import ExportFile, ExportOptions
from custom_components.reiseverlauftracker.export.model import TrackPoint
from custom_components.reiseverlauftracker.export.texts import texts_for
from custom_components.reiseverlauftracker.export.tour import (
    NO_COUNTRY,
    ConsumptionInputs,
    Night,
    TourCost,
    TourRefill,
    TourTrip,
    gas_used_percent,
    locate_nights,
    main_place,
    night_dates,
    night_groups,
    rename_nights,
    summarize,
    unnamed_groups,
)
from custom_components.reiseverlauftracker.export.tour_export import days_csv, export_tour, format_days, tour_title
from custom_components.reiseverlauftracker.utils.geo import Position, distance_m

BERLIN = ZoneInfo("Europe/Berlin")
METRES_PER_DEGREE_LAT = 111195.0
HOME = (53.55, 10.0)
CAMP = (46.5, 11.35)
LAKE = (46.6, 11.1)


def local(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=BERLIN).astimezone(UTC)


def trip(folder: str, start: datetime, origin: tuple[float, float], target: tuple[float, float]) -> TourTrip:
    """Return a straight trip of 11 points over one hour."""
    points = tuple(
        TrackPoint(
            start + timedelta(minutes=6 * i),
            origin[0] + (target[0] - origin[0]) * i / 10,
            origin[1] + (target[1] - origin[1]) * i / 10,
        )
        for i in range(11)
    )
    km = distance_m(Position(*origin), Position(*target)) / 1000
    return TourTrip(
        folder, folder, points[0].time, points[-1].time, points, km, timedelta(hours=1), 100.0, 50.0, ("DE",)
    )


@pytest.fixture
def trips() -> list[TourTrip]:
    """Home to camp on the 10th, an excursion to the lake and back on the 12th, home on the 15th."""
    return [
        trip("hin", local(10, 8), HOME, CAMP),
        trip("ausflug", local(12, 10), CAMP, LAKE),
        trip("zurueck", local(12, 16), LAKE, CAMP),
        trip("heim", local(15, 9), CAMP, HOME),
    ]


def test_night_dates_are_the_evenings_whose_morning_lies_in_the_tour() -> None:
    assert night_dates(local(10, 8), local(15, 11), BERLIN) == [date(2026, 10, d) for d in range(10, 15)]
    assert night_dates(local(10, 8), local(10, 18), BERLIN) == []
    # 03:00 exactly at the start does not count, 03:00 exactly at the end does.
    assert night_dates(local(11, 3), local(12, 3), BERLIN) == [date(2026, 10, 11)]


def test_nights_are_where_the_last_trip_ended(trips: list[TourTrip]) -> None:
    nights = locate_nights(trips, local(10, 8), local(15, 11), BERLIN)

    assert [n.night.day for n in nights] == [10, 11, 12, 13, 14]
    assert all(distance_m(n.position, Position(*CAMP)) < 1 for n in nights)
    groups = night_groups(nights)
    assert [len(g) for g in groups] == [5]


def test_known_names_are_kept_for_the_same_place(trips: list[TourTrip]) -> None:
    known = [Night(date(2026, 10, 11), CAMP[0] + 0.001, CAMP[1], "Camping Seeblick", name_changed=True)]

    nights = locate_nights(trips, local(10, 8), local(15, 11), BERLIN, known)

    assert {n.name for n in nights} == {"Camping Seeblick"}
    assert all(n.name_changed for n in nights)


def test_rename_applies_to_the_whole_run(trips: list[TourTrip]) -> None:
    nights = locate_nights(trips, local(10, 8), local(15, 11), BERLIN)
    assert len(unnamed_groups(nights)) == 1

    renamed = rename_nights(nights, {date(2026, 10, 12): "  Camping Seeblick "})

    assert {(n.name, n.name_changed) for n in renamed} == {("Camping Seeblick", True)}
    assert unnamed_groups(renamed) == []
    assert main_place(renamed) == "Camping Seeblick"


def test_a_name_set_by_hand_splits_a_run() -> None:
    nights = [
        Night(date(2026, 10, 10), *CAMP, name="Camping A"),
        Night(date(2026, 10, 11), *CAMP, name="Camping B", name_changed=True),
    ]
    assert [len(g) for g in night_groups(nights)] == [1, 1]


def test_different_places_and_gaps_split_runs() -> None:
    nights = [
        Night(date(2026, 10, 10), *CAMP),
        Night(date(2026, 10, 11), CAMP[0] + 600 / METRES_PER_DEGREE_LAT, CAMP[1]),
        Night(date(2026, 10, 13), CAMP[0] + 600 / METRES_PER_DEGREE_LAT, CAMP[1]),
    ]
    assert [len(g) for g in night_groups(nights)] == [1, 1, 1]


def test_summary_overview_costs_and_estimate(trips: list[TourTrip]) -> None:
    start, end = local(10, 7), local(15, 12)
    nights = rename_nights(locate_nights(trips, start, end, BERLIN), {date(2026, 10, 10): "Camping Seeblick"})
    refills = [
        TourRefill(local(10, 12), fuel_litres=60, fuel_amount=105.0, country="AT"),
        TourRefill(local(13, 10), gas_litres=20, gas_amount=19.0, country="IT"),
        TourRefill(local(16, 10), fuel_litres=50, fuel_amount=90.0, country="DE"),  # after the tour
    ]
    costs = [
        TourCost(date(2026, 10, 10), "maut", 23.4, "AT"),
        TourCost(date(2026, 10, 11), "stellplatz", 140.0),
        TourCost(date(2026, 10, 15), "maut", 23.4, "AT"),
        TourCost(date(2026, 10, 16), "maut", 10.0, "DE"),  # after the tour
    ]
    inputs = ConsumptionInputs(consumption_l_100km=12.0, gas_used_percent=40, gas_litres_per_percent=0.5)

    summary = summarize(
        trips, nights, refills, costs, inputs, start, end, BERLIN, end_place="Hamburg", odometer=(34_000, 36_100)
    )

    assert summary.distance_km == pytest.approx(sum(t.distance_km for t in trips))
    assert summary.moving_time == timedelta(hours=4)
    assert summary.ascent_m == 400
    assert summary.nights == 5
    assert [d.day.day for d in summary.days] == [10, 11, 12, 13, 14, 15]
    assert summary.days[0].cost == pytest.approx(128.4)
    assert summary.days[1].km == 0
    assert summary.days[2].km > 0

    camp, arrival = summary.places
    assert (camp.first, camp.last, camp.nights, camp.name) == (
        date(2026, 10, 10),
        date(2026, 10, 15),
        5,
        "Camping Seeblick",
    )
    assert camp.km == pytest.approx(sum(d.km for d in summary.days[:5]))
    assert (arrival.first, arrival.nights, arrival.name) == (date(2026, 10, 15), 0, "Hamburg")

    paid = summary.costs
    assert (paid.fuel_litres, paid.fuel_amount, paid.gas_litres, paid.gas_amount) == (60, 105.0, 20, 19.0)
    assert paid.travel == {"maut": pytest.approx(46.8), "stellplatz": 140.0}
    assert paid.by_country == {"AT": pytest.approx(151.8), NO_COUNTRY: 140.0, "IT": 19.0}
    assert paid.total == pytest.approx(310.8)
    assert paid.as_dict()["je_land"]["-"] == 140.0
    assert summary.countries == ("DE", "AT", "IT")

    estimate = summary.estimate
    assert estimate is not None
    assert estimate.fuel_litres == pytest.approx(summary.distance_km * 0.12)
    assert estimate.fuel_cost == pytest.approx(estimate.fuel_litres * 1.75)
    assert estimate.gas_litres == 20
    assert estimate.gas_cost == pytest.approx(19.0)


def test_estimate_falls_back_to_the_last_price_and_needs_a_consumption(trips: list[TourTrip]) -> None:
    start, end = local(10, 7), local(15, 12)
    with_price = summarize(trips, [], [], [], ConsumptionInputs(10.0, fuel_price=2.0), start, end, BERLIN)
    assert with_price.estimate is not None
    assert with_price.estimate.fuel_cost == pytest.approx(with_price.estimate.fuel_litres * 2.0)
    assert with_price.estimate.gas_litres is None

    assert summarize(trips, [], [], [], ConsumptionInputs(), start, end, BERLIN).estimate is None


def test_gas_used_from_levels_and_stops() -> None:
    assert gas_used_percent(150, 90, 0, None) == 60
    assert gas_used_percent(150, 180, 20, 0.25) == 50
    assert gas_used_percent(150, 180, 20, None) is None
    assert gas_used_percent(None, 180, 0, None) is None


@pytest.fixture
def tour():
    """Return trips, nights and summary of a tour from the 10th to the 15th with five nights at a camp site."""
    trips = [
        trip("hin", local(10, 8), HOME, CAMP),
        trip("ausflug", local(12, 10), CAMP, LAKE),
        trip("zurueck", local(12, 16), LAKE, CAMP),
        trip("heim", local(15, 9), CAMP, HOME),
    ]
    start, end = local(10, 7), local(15, 12)
    nights = rename_nights(locate_nights(trips, start, end, BERLIN), {date(2026, 10, 10): "Camping Seeblick"})
    summary = summarize(
        trips,
        nights,
        [TourRefill(local(10, 12), fuel_litres=60, fuel_amount=105.0, country="AT")],
        [TourCost(date(2026, 10, 10), "maut", 23.4, "AT"), TourCost(date(2026, 10, 11), "stellplatz", 140.0)],
        ConsumptionInputs(consumption_l_100km=12.0),
        start,
        end,
        BERLIN,
        end_place="Hamburg",
        odometer=(34_000, 36_100),
    )
    return trips, nights, summary


def test_format_days() -> None:
    de, en = texts_for("de"), texts_for("en")
    assert format_days(de, date(2026, 10, 10), date(2026, 10, 15)) == "10.–15.10."
    assert format_days(de, date(2026, 9, 28), date(2026, 10, 3)) == "28.09.–03.10."
    assert format_days(de, date(2026, 10, 10), date(2026, 10, 10)) == "10.10."
    assert format_days(en, date(2026, 10, 10), date(2026, 10, 15)) == "10-10 – 10-15"


def test_title_suggestion(tour) -> None:
    _trips, nights, summary = tour
    assert tour_title("de", summary, nights, BERLIN) == "Camping Seeblick · 10.–15.10.2026"
    assert tour_title("de", summary, [], BERLIN) == "Tour 10.–15.10.2026"
    assert tour_title("en", summary, [], BERLIN) == "Tour 2026-10-10 – 2026-10-15"


def test_days_csv_has_one_row_per_day(tour) -> None:
    _trips, _nights, summary = tour
    lines = days_csv(summary, "de").splitlines()
    assert lines[0] == "Datum;km;Standort;Kosten"
    assert len(lines) == 7
    assert lines[2] == "11.10.2026;0,0;Camping Seeblick;140,00"
    assert lines[-1].startswith("15.10.2026;") and lines[-1].endswith(";;0,00")


def test_export_writes_all_files(tour, tmp_path: Path, offline_fetcher) -> None:
    trips, nights, summary = tour
    options = ExportOptions(language="de", timezone=BERLIN, map_size=(800, 600))

    result = export_tour(
        summary, trips, nights, "Südtirol 2026", tmp_path, options, raw={"version": 1}, fetch_tile=offline_fetcher
    )

    assert result.basename == "suedtirol_2026"
    assert set(result.files) == {
        ExportFile.STATS,
        ExportFile.DAYS,
        ExportFile.GPX,
        ExportFile.MAP,
        ExportFile.COMPOSITE,
        ExportFile.RAW,
    }
    text = (tmp_path / result.files[ExportFile.STATS]).read_text(encoding="utf-8")
    assert text == result.stats_text
    assert "Tage / Nächte:   6 / 5" in text
    assert "Kilometerstand:  34000 – 36100 km" in text
    assert "10.–15.10.  Camping Seeblick  5 Nächte" in text
    assert "Stellplatz" in text and "Gesamt" in text and "ca." in text
    gpx = (tmp_path / result.files[ExportFile.GPX]).read_text(encoding="utf-8")
    assert gpx.count("<trk>") == 4
    with Image.open(tmp_path / result.files[ExportFile.COMPOSITE]) as image:
        assert image.width == 2400
        assert image.height > 2000


def test_new_export_reuses_the_map_and_removes_old_files(tour, tmp_path: Path, offline_fetcher, fake_tiles) -> None:
    trips, nights, summary = tour
    options = ExportOptions(language="de", timezone=BERLIN, map_size=(800, 600))
    first = export_tour(summary, trips, nights, "Alt", tmp_path, options, raw={"v": 1}, fetch_tile=offline_fetcher)
    tiles = len(fake_tiles)

    second = export_tour(
        summary,
        trips,
        nights,
        "Neu",
        tmp_path,
        options,
        previous=first.files,
        reuse_map=True,
        fetch_tile=offline_fetcher,
    )

    assert len(fake_tiles) == tiles
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(second.files.values())
    assert second.files[ExportFile.RAW] == "neu_rohdaten.json"
    assert (tmp_path / "neu_rohdaten.json").read_text() == '{"v": 1}'
