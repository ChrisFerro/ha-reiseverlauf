"""
Files of a tour export: statistics, day CSV, GPX, map, composite image and raw data (feat-10-tour.md 6.4).

Everything here blocks (tiles are downloaded, images rendered), so callers run it in an executor.
"""

from collections.abc import Sequence
import csv
from dataclasses import dataclass
from datetime import date, tzinfo
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .chart import BASE_WIDTH
from .composite import render_composite
from .exporter import FILE_SUFFIXES, MAX_SCALE, MIN_SCALE, ExportFile, slugify
from .fonts import load_font
from .gpx import build_gpx_tracks
from .map import TileFetcher, http_tile_fetcher, render_route_map
from .model import ExportOptions
from .stats import stats_text
from .texts import Texts, format_dates, format_duration, format_money, format_number, texts_for
from .tour import NO_COUNTRY, Night, PlaceRow, TourSummary, TourTrip, main_place


@dataclass(frozen=True, slots=True)
class TourTexts:
    """Strings of a tour export in one language, in addition to `Texts`."""

    default_title: str
    days: str
    days_nights: str
    one_night: str
    nights: str
    overview: str
    paid: str
    by_country: str
    no_country: str
    total: str
    estimate: str
    consumption: str
    approx: str
    countries: str
    trips: str
    csv_headers: tuple[str, ...]
    csv_delimiter: str


TOUR_TEXTS: dict[str, TourTexts] = {
    "de": TourTexts(
        default_title="Tour {}",
        days="Tage",
        days_nights="Tage / Nächte",
        one_night="1 Nacht",
        nights="{} Nächte",
        overview="Tagesübersicht",
        paid="Kosten (bezahlt)",
        by_country="Je Land",
        no_country="ohne Land",
        total="Gesamt",
        estimate="Verbrauch (geschätzt)",
        consumption="Verbrauch",
        approx="ca.",
        countries="Länder",
        trips="Reisen",
        csv_headers=("Datum", "km", "Standort", "Kosten"),
        csv_delimiter=";",
    ),
    "en": TourTexts(
        default_title="Tour {}",
        days="Days",
        days_nights="Days / nights",
        one_night="1 night",
        nights="{} nights",
        overview="Days",
        paid="Costs (paid)",
        by_country="By country",
        no_country="no country",
        total="Total",
        estimate="Consumption (estimated)",
        consumption="Consumption",
        approx="approx.",
        countries="Countries",
        trips="Trips",
        csv_headers=("Date", "km", "Place", "Costs"),
        csv_delimiter=",",
    ),
}

TABLE_FONT = 34
HEADING_FONT = 40
ROW_HEIGHT = 52
COLUMN_GAP = 50
MARGIN = 80

type Table = tuple[str, list[tuple[str, ...]], str]
"""Heading, rows and the alignment of each column ("l" or "r")."""


@dataclass(frozen=True, slots=True)
class TourResult:
    """What a tour export wrote."""

    title: str
    basename: str
    files: dict[ExportFile, str]
    stats_text: str


def tour_texts_for(language: str) -> TourTexts:
    """Return the tour texts for a Home Assistant language code, falling back to English."""
    return TOUR_TEXTS.get(language.split("-", maxsplit=1)[0].lower(), TOUR_TEXTS["en"])


def format_days(texts: Texts, first: date, last: date) -> str:
    """Return a short span of days with an en dash, e.g. 10.-15.10. or 28.09.-03.10.; month-day in English."""
    if texts.decimal_separator == ",":
        if first == last:
            return f"{first:%d.%m.}"
        if (first.year, first.month) == (last.year, last.month):
            return f"{first:%d.}–{last:%d.%m.}"
        return f"{first:%d.%m.}–{last:%d.%m.}"
    if first == last:
        return f"{first:%m-%d}"
    return f"{first:%m-%d} – {last:%m-%d}"


def tour_title(language: str, summary: TourSummary, nights: Sequence[Night], tz: tzinfo) -> str:
    """Return the suggested title: the place with the most nights and the period, else "Tour" and the period."""
    texts, tour_texts = texts_for(language), tour_texts_for(language)
    first, last = summary.start.astimezone(tz).date(), summary.end.astimezone(tz).date()
    if texts.decimal_separator == ",":
        period = f"{format_days(texts, first, last)}{last:%Y}"
    else:
        period = format_dates(texts, summary.start, summary.end, tz)
    place = main_place(nights)
    return f"{place} · {period}" if place else tour_texts.default_title.format(period)


def _nights(tour_texts: TourTexts, count: int) -> str:
    return tour_texts.one_night if count == 1 else tour_texts.nights.format(count)


def figure_rows(
    summary: TourSummary, texts: Texts, tour_texts: TourTexts, currency: str, tz: tzinfo
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return the key figures: period, distance, driving time, days, elevation; then odometer, costs and estimate."""
    days = len(summary.days)
    figures = [
        (texts.period, format_dates(texts, summary.start, summary.end, tz)),
        (texts.distance, f"{format_number(texts, summary.distance_km)} km"),
        (texts.moving_time, format_duration(summary.moving_time)),
        (tour_texts.days_nights, f"{days} / {summary.nights}"),
    ]
    if summary.ascent_m is not None and summary.descent_m is not None:
        figures.append(
            (
                texts.elevation_gain,
                f"+{format_number(texts, summary.ascent_m)} / -{format_number(texts, summary.descent_m)} m",
            )
        )
    extra: list[tuple[str, str]] = []
    start, end = summary.odometer_start_km, summary.odometer_end_km
    if start is not None and end is not None:
        extra.append((texts.odometer, f"{format_number(texts, start)} – {format_number(texts, end)} km"))
    if summary.costs.total > 0:
        extra.append((texts.costs, format_money(texts, summary.costs.total, currency)))
    if summary.estimate is not None:
        extra.append(
            (
                tour_texts.consumption,
                f"{tour_texts.approx} {format_number(texts, summary.estimate.fuel_litres)} l {texts.diesel}",
            )
        )
    if summary.countries:
        extra.append((tour_texts.countries, " · ".join(summary.countries)))
    return figures, extra


def tables(summary: TourSummary, texts: Texts, tour_texts: TourTexts, currency: str) -> list[Table]:
    """Return the overview by place, the costs paid, by country, and the estimate, as tables."""

    def money(value: float) -> str:
        return format_money(texts, value, currency)

    overview = [_place_row(row, texts, tour_texts, money) for row in summary.places]
    result: list[Table] = [(tour_texts.overview, overview, "llrrr")]

    costs = summary.costs
    paid: list[tuple[str, ...]] = []
    if costs.fuel_litres > 0 or costs.fuel_amount > 0:
        paid.append(
            (texts.diesel.capitalize(), f"{format_number(texts, costs.fuel_litres, 1)} l", money(costs.fuel_amount))
        )
    if costs.gas_litres > 0 or costs.gas_amount > 0:
        paid.append((texts.gas.capitalize(), f"{format_number(texts, costs.gas_litres, 1)} l", money(costs.gas_amount)))
    for category, amount in costs.travel.items():
        paid.append((texts.cost_categories.get(category, category).capitalize(), "", money(amount)))
    if paid:
        paid.append((tour_texts.total, "", money(costs.total)))
        result.append((tour_texts.paid, paid, "lrr"))
    countries = [
        (tour_texts.no_country if country == NO_COUNTRY else country, money(amount))
        for country, amount in sorted(costs.by_country.items(), key=lambda item: -item[1])
    ]
    if len(countries) > 1:
        result.append((tour_texts.by_country, countries, "lr"))

    if (estimate := summary.estimate) is not None:
        approx = tour_texts.approx
        rows: list[tuple[str, ...]] = [
            (
                texts.diesel.capitalize(),
                f"{approx} {format_number(texts, estimate.fuel_litres)} l",
                f"{approx} {money(estimate.fuel_cost)}" if estimate.fuel_cost is not None else "",
            )
        ]
        if estimate.gas_litres is not None:
            gas = f"{approx} {format_number(texts, estimate.gas_litres)} l"
        elif estimate.gas_percent is not None:
            gas = f"{approx} {format_number(texts, estimate.gas_percent)} %"
        else:
            gas = None
        if gas is not None:
            cost = f"{approx} {money(estimate.gas_cost)}" if estimate.gas_cost is not None else ""
            rows.append((texts.gas.capitalize(), gas, cost))
        result.append((tour_texts.estimate, rows, "lrr"))
    return result


def _place_row(row: PlaceRow, texts: Texts, tour_texts: TourTexts, money: Any) -> tuple[str, ...]:
    return (
        format_days(texts, row.first, row.last),
        row.name or texts.unknown_place,
        _nights(tour_texts, row.nights) if row.nights else "",
        f"{format_number(texts, row.km)} km" if row.km >= 0.5 else "",
        money(row.cost) if row.cost > 0 else "",
    )


def tables_text(sections: Sequence[Table]) -> list[str]:
    """Return the tables as aligned plain-text lines, each under its heading."""
    lines: list[str] = []
    for heading, rows, align in sections:
        if not rows:
            continue
        widths = [max(len(row[i]) for row in rows) for i in range(len(align))]
        lines += ["", f"{heading}:"]
        for row in rows:
            cells = [
                cell.rjust(w) if a == "r" else cell.ljust(w) for cell, w, a in zip(row, widths, align, strict=True)
            ]
            lines.append(("  " + "  ".join(cells)).rstrip())
    return lines


def days_csv(summary: TourSummary, language: str) -> str:
    """Return one row per day: date, km, place of the night and the costs of the day (5.6)."""
    texts, tour_texts = texts_for(language), tour_texts_for(language)
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=tour_texts.csv_delimiter, lineterminator="\r\n")
    writer.writerow(tour_texts.csv_headers)
    for day in summary.days:
        writer.writerow(
            (
                day.day.strftime(texts.date_format),
                format_number(texts, day.km, 1),
                (day.night.name or "") if day.night else "",
                format_number(texts, day.cost, 2),
            )
        )
    return buffer.getvalue()


def render_tables(sections: Sequence[Table], scale: float = 1.0) -> Image.Image | None:
    """Draw the tables one below the other, with columns as wide as their longest cell; None without rows."""
    sections = [s for s in sections if s[1]]
    if not sections:
        return None

    def s(v: float) -> int:
        return round(v * scale)

    width = s(BASE_WIDTH)
    font, heading_font = load_font(s(TABLE_FONT)), load_font(s(HEADING_FONT))
    height = sum(s(ROW_HEIGHT) * (len(rows) + 2) for _, rows, _ in sections) + s(MARGIN)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    y = s(20)
    for heading, rows, align in sections:
        draw.text((s(MARGIN), y), heading, fill="#111111", font=heading_font)
        y += round(s(ROW_HEIGHT) * 1.3)
        widths = [max(draw.textlength(row[i], font=font) for row in rows) for i in range(len(align))]
        for index, row in enumerate(rows):
            if index % 2 == 1:
                draw.rectangle(
                    [(s(MARGIN) - s(10), y - s(6)), (width - s(MARGIN), y + s(ROW_HEIGHT) - s(10))], fill="#f3f3f3"
                )
            x = s(MARGIN)
            for cell, column_width, a in zip(row, widths, align, strict=True):
                offset = column_width - draw.textlength(cell, font=font) if a == "r" else 0
                draw.text((x + offset, y), cell, fill="#222222", font=font)
                x += column_width + s(COLUMN_GAP)
            y += s(ROW_HEIGHT)
        y += round(s(ROW_HEIGHT) * 0.7)
    return image.crop((0, 0, width, min(y, height)))


def export_tour(
    summary: TourSummary,
    trips: Sequence[TourTrip],
    nights: Sequence[Night],
    title: str,
    out_dir: Path,
    options: ExportOptions,
    *,
    previous: dict[ExportFile, str] | None = None,
    raw: dict[str, Any] | None = None,
    reuse_map: bool = False,
    fetch_tile: TileFetcher | None = None,
) -> TourResult:
    """
    Write statistics, day CSV, GPX, map, composite and raw data of a tour into `out_dir`.

    With `reuse_map`, the map of `previous` is taken over (renamed to the new title)
    instead of downloading tiles again. Without `raw`, the previous raw data stays.
    Files of `previous` that are not written again are removed.
    """
    previous = previous or {}
    texts, tour_texts = texts_for(options.language), tour_texts_for(options.language)
    tz = options.timezone
    scale = min(max(options.scale, MIN_SCALE), MAX_SCALE)
    first, last = summary.start.astimezone(tz), summary.end.astimezone(tz)
    basename = slugify(title) or f"tour_{first:%Y%m%d}_{last:%Y%m%d}"
    figures, extra = figure_rows(summary, texts, tour_texts, options.currency, tz)
    sections = tables(summary, texts, tour_texts, options.currency)
    text = stats_text(title, [*figures, *extra], tables_text(sections))

    out_dir.mkdir(parents=True, exist_ok=True)
    files: dict[ExportFile, str] = {}

    def path(kind: ExportFile, suffix: str | None = None) -> Path:
        files[kind] = f"{basename}{suffix or FILE_SUFFIXES[kind]}"
        return out_dir / files[kind]

    path(ExportFile.STATS).write_text(text, encoding="utf-8")
    path(ExportFile.DAYS).write_text(days_csv(summary, options.language), encoding="utf-8-sig", newline="")
    tracks = [(trip.title, trip.points) for trip in trips]
    path(ExportFile.GPX).write_text(build_gpx_tracks(tracks, title), encoding="utf-8")

    map_image = None
    old_map = out_dir / previous[ExportFile.MAP] if ExportFile.MAP in previous else None
    if reuse_map and old_map is not None and old_map.is_file():
        map_image = _open_image(old_map)
    if map_image is None and options.with_map:
        width, height = options.map_size
        map_image = render_route_map(
            [trip.points for trip in trips],
            (round(width * scale), round(height * scale)),
            round(options.map_line_width * scale),
            fetch_tile or http_tile_fetcher(options.user_agent),
            places=[(n.lat, n.lon) for n in nights],
        )
    if map_image is not None:
        map_image.save(path(ExportFile.MAP))

    table_image = render_tables(sections, scale)
    composite = render_composite([map_image, table_image], title, figures[0][1], figures[1:], scale, extra)
    if composite is not None:
        composite.save(path(ExportFile.COMPOSITE))
        composite.close()
    for image in (map_image, table_image):
        if image is not None:
            image.close()

    if raw is not None:
        path(ExportFile.RAW).write_text(json.dumps(raw), encoding="utf-8")
    elif ExportFile.RAW in previous and (out_dir / previous[ExportFile.RAW]).is_file():
        old_raw = out_dir / previous[ExportFile.RAW]
        new_raw = path(ExportFile.RAW)
        if old_raw != new_raw:
            old_raw.replace(new_raw)

    for kind, name in previous.items():
        if files.get(kind) != name:
            (out_dir / name).unlink(missing_ok=True)
    return TourResult(title=title, basename=basename, files=files, stats_text=text)


def _open_image(path: Path) -> Image.Image | None:
    try:
        with Image.open(path) as image:
            image.load()
            return image.copy()
    except OSError:
        return None
