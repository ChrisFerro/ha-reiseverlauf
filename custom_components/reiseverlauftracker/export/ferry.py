"""
Ferry crossings of a track: split off from the distance driven (docs/features/feat-12-kartensymbole.md 5.10).

A crossing is a stop marked as ferry. Every step of the track that overlaps it in
time belongs to the crossing: the step onto the ship, the positions on board and
the step off it; without positions on board, the one step from the last position
before to the first after it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

from .model import FerryLeg, Stop, TrackPoint


@dataclass(frozen=True, slots=True)
class SplitTrack:
    """A track split into the parts driven on land and the ferry crossings."""

    land: list[list[TrackPoint]]
    """Driven parts in order; a part may hold a single point."""
    ferries: list[list[TrackPoint]]
    """Positions of each crossing, from the last one before to the first one after it."""
    ferry_time: timedelta = timedelta()
    """Time on board: the durations of the ferry stops."""

    @property
    def legs(self) -> tuple[FerryLeg, ...]:
        """Return the crossings as drawn on the map."""
        return tuple(FerryLeg(tuple((p.lat, p.lon) for p in leg)) for leg in self.ferries)


def ferry_spans(stops: Sequence[Stop]) -> list[tuple[datetime, datetime]]:
    """Return start and end of each stop marked as ferry."""
    return [(s.start, s.end) for s in stops if s.ferry]


def on_ferry(time: datetime, spans: Sequence[tuple[datetime, datetime]]) -> bool:
    """Return whether `time` lies within a crossing."""
    return any(start <= time <= end for start, end in spans)


def split_track(points: Sequence[TrackPoint], stops: Sequence[Stop]) -> SplitTrack:
    """Split `points` (sorted by time) at the ferry stops among `stops`."""
    spans = ferry_spans(stops)
    if not spans or not points:
        return SplitTrack(land=[list(points)], ferries=[])
    land: list[list[TrackPoint]] = [[points[0]]]
    ferries: list[list[TrackPoint]] = []
    aboard = False
    for a, b in pairwise(points):
        crossing = any(a.time < end and b.time > start for start, end in spans)
        if crossing:
            if not aboard:
                ferries.append([a])
            ferries[-1].append(b)
        elif aboard:
            land.append([a, b])
        else:
            land[-1].append(b)
        aboard = crossing
    used = [(start, end) for start, end in spans if points[0].time <= end and start <= points[-1].time]
    return SplitTrack(
        land=[part for part in land if part],
        ferries=ferries,
        ferry_time=sum((end - start for start, end in used), timedelta()),
    )
