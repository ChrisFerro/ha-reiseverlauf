"""Elevation and speed profile drawn with Pillow."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
import math

from PIL import Image, ImageDraw

from custom_components.reiseverlauftracker.utils.geo import distance_m

from .fonts import load_font
from .model import StepSeries, TrackPoint
from .texts import Texts

BASE_WIDTH = 2400
BASE_PANEL_HEIGHT = 900
TIME_TICK_CANDIDATES_S = (600, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800)
MAX_TIME_TICKS = 7
SECONDS_PER_DAY = 86400


@dataclass(frozen=True, slots=True)
class Panel:
    """One chart panel: a polyline with axes, ticks and labels."""

    title: str
    y_label: str
    x_label: str
    xs: Sequence[float]
    ys: Sequence[float]
    x_ticks: Sequence[tuple[float, str]]
    line_color: str
    fill_color: str | None = None
    y_min: float | None = None


def nice_step(span: float, target: int = 6) -> float:
    """Round `span / target` up to 1, 2 or 5 times a power of ten."""
    if span <= 0:
        return 1.0
    raw = span / target
    decade = 10 ** math.floor(math.log10(raw))
    for factor in (1, 2, 5, 10):
        if raw <= factor * decade:
            return factor * decade
    return 10 * decade


def time_ticks(x0: float, x1: float, tz: tzinfo, texts: Texts) -> list[tuple[float, str]]:
    """Return tick positions (epoch seconds) and labels in local time."""
    span = x1 - x0
    interval = next((c for c in TIME_TICK_CANDIDATES_S if span / c <= MAX_TIME_TICKS), 2 * SECONDS_PER_DAY)
    tick = datetime.fromtimestamp(x0, tz).replace(hour=0, minute=0, second=0, microsecond=0)
    step = timedelta(seconds=interval)
    while tick.timestamp() < x0:
        tick += step
    fmt = "%H:%M" if span <= SECONDS_PER_DAY else texts.chart_datetime_format
    ticks = []
    while tick.timestamp() <= x1:
        ticks.append((tick.timestamp(), tick.strftime(fmt)))
        tick += step
    return ticks


def _draw_panel(draw: ImageDraw.ImageDraw, top: int, width: int, height: int, panel: Panel, k: float) -> None:
    def s(v: float) -> int:
        return max(1, round(v * k))

    f_title, f_text = load_font(s(52)), load_font(s(34))
    px0, px1 = s(190), width - s(70)
    py0, py1 = top + s(130), top + height - s(150)
    x0, x1 = panel.xs[0], panel.xs[-1]
    if x1 <= x0:
        x1 = x0 + 1
    step = nice_step(max(panel.ys) - min(panel.ys))
    y_min = panel.y_min if panel.y_min is not None else math.floor(min(panel.ys) / step) * step
    y_max = math.ceil(max(panel.ys) / step) * step
    if y_max <= y_min:
        y_max = y_min + step

    def px(x: float) -> float:
        return px0 + (x - x0) / (x1 - x0) * (px1 - px0)

    def py(y: float) -> float:
        return py1 - (y - y_min) / (y_max - y_min) * (py1 - py0)

    y = y_min
    while y <= y_max + 1e-9:
        yy = py(y)
        draw.line([(px0, yy), (px1, yy)], fill="#dddddd", width=s(2))
        label = f"{y:.0f}"
        draw.text((px0 - s(15) - draw.textlength(label, font=f_text), yy - s(18)), label, fill="#333333", font=f_text)
        y += step
    for xv, label in panel.x_ticks:
        if x0 <= xv <= x1:
            xx = px(xv)
            draw.line([(xx, py0), (xx, py1)], fill="#eeeeee", width=s(2))
            draw.text((xx - draw.textlength(label, font=f_text) / 2, py1 + s(15)), label, fill="#333333", font=f_text)

    line = [(px(x), py(y)) for x, y in zip(panel.xs, panel.ys, strict=True)]
    if panel.fill_color:
        draw.polygon([*line, (px1, py1), (px0, py1)], fill=panel.fill_color)
    draw.line(line, fill=panel.line_color, width=s(5), joint="curve")
    draw.rectangle([px0, py0, px1, py1], outline="#555555", width=s(2))
    draw.text((px0, top + s(25)), panel.title, fill="#111111", font=f_title)
    draw.text((px0, py0 - s(48)), panel.y_label, fill="#555555", font=f_text)
    x_label_width = draw.textlength(panel.x_label, font=f_text)
    draw.text(((px0 + px1) / 2 - x_label_width / 2, py1 + s(70)), panel.x_label, fill="#555555", font=f_text)


def _elevation_panel(points: Sequence[TrackPoint], title: str | None, texts: Texts) -> Panel:
    km: list[float] = []
    altitudes: list[float] = []
    total = 0.0
    for prev, point in zip([None, *points[:-1]], points, strict=True):
        if prev is not None:
            total += distance_m(prev.position, point.position) / 1000
        if point.altitude is not None:
            km.append(total)
            altitudes.append(point.altitude)
    step = nice_step(km[-1] - km[0])
    ticks = [(i * step, f"{i * step:.0f}") for i in range(int(km[-1] / step) + 1)]
    return Panel(
        title=f"{title} – {texts.elevation_profile}" if title else texts.elevation_profile,
        y_label=texts.altitude_axis,
        x_label=texts.distance_axis,
        xs=km,
        ys=altitudes,
        x_ticks=ticks,
        line_color="#023047",
        fill_color="#bde0f2",
    )


def _speed_panel(speed: StepSeries, start: datetime, end: datetime, tz: tzinfo, texts: Texts) -> Panel:
    current = speed.value_at(start)
    xs, ys = [start.timestamp()], [current if current is not None else speed.values[0]]
    for t, v in zip(speed.times, speed.values, strict=True):
        if start < t <= end:
            xs += [t.timestamp(), t.timestamp()]
            ys += [ys[-1], v]
    xs.append(end.timestamp())
    ys.append(ys[-1])
    return Panel(
        title=texts.speed,
        y_label="km/h",
        x_label=texts.time_axis,
        xs=xs,
        ys=ys,
        x_ticks=time_ticks(xs[0], xs[-1], tz, texts),
        line_color="#d62828",
        y_min=0,
    )


def render_profile(
    points: Sequence[TrackPoint],
    speed: StepSeries | None,
    window: tuple[datetime, datetime],
    texts: Texts,
    tz: tzinfo,
    scale: float = 1.0,
    title: str | None = None,
) -> Image.Image | None:
    """Draw elevation over distance and speed over time; None without data for either."""
    panels = []
    if sum(1 for p in points if p.altitude is not None) >= 2:
        panels.append(_elevation_panel(points, title, texts))
    if speed is not None and len(speed) >= 2:
        panels.append(_speed_panel(speed, window[0], window[1], tz, texts))
    if not panels:
        return None
    width, panel_height = round(BASE_WIDTH * scale), round(BASE_PANEL_HEIGHT * scale)
    image = Image.new("RGB", (width, panel_height * len(panels)), "white")
    draw = ImageDraw.Draw(image)
    for index, panel in enumerate(panels):
        _draw_panel(draw, index * panel_height, width, panel_height, panel, scale)
    return image
