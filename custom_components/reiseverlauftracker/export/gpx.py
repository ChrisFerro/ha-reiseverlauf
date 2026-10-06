"""GPX 1.1 track with altitude and speed."""

from collections.abc import Sequence
from datetime import UTC
from xml.sax.saxutils import escape, quoteattr

from .model import TrackPoint

KMH_PER_MPS = 3.6


def build_gpx(points: Sequence[TrackPoint], name: str) -> str:
    """Return a GPX document; speed goes into `<extensions><speed>` in m/s."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="reiseverlauftracker" xmlns="http://www.topografix.com/GPX/1/1">',
        f"  <trk><name>{escape(name)}</name><trkseg>",
    ]
    for p in points:
        altitude = f"<ele>{p.altitude:.1f}</ele>" if p.altitude is not None else ""
        time = p.time.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        speed = f"<extensions><speed>{p.speed / KMH_PER_MPS:.2f}</speed></extensions>" if p.speed is not None else ""
        lines.append(
            f"    <trkpt lat={quoteattr(f'{p.lat:.6f}')} lon={quoteattr(f'{p.lon:.6f}')}>"
            f"{altitude}<time>{time}</time>{speed}</trkpt>"
        )
    lines += ["  </trkseg></trk>", "</gpx>"]
    return "\n".join(lines) + "\n"
