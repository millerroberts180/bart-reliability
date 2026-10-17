"""Boarding groups: the ways a train can leave a station (docs/boarding_groups.md).

GTFS direction_id is defined per route, so it cannot stand for a station-wide direction.
At Hayward, direction 1 holds Green line trains to Daly City and Orange line trains to
Berryessa, which leave from opposite platforms. Groups are built from the schedule's
boardings instead: each boarding is a train leaving the station, described by the
station it came from and the station it goes to next.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Boarding:
    """A scheduled visit that does not end the trip: the train leaves toward `next_station`."""

    station: str
    previous_station: str | None
    next_station: str

    @property
    def reverses(self) -> bool:
        """The train leaves the way it came (no such visit in BART's current feed)."""
        return self.previous_station == self.next_station


def group_id(next_stations: Iterable[str]) -> str:
    """Stable ID from the shape of the network alone: "to-SHAY", "to-CAST-HAYW"."""
    return "to-" + "-".join(sorted(set(next_stations)))


def opposite_pairs(boardings: Iterable[Boarding]) -> list[tuple[Boarding, Boarding]]:
    """Pairs where one train heads to the station the other has just come from."""
    items = [b for b in boardings if not b.reverses]
    return [(a, c) for a in items for c in items if a.next_station == c.previous_station]


def group_boardings(boardings: Iterable[Boarding]) -> dict[tuple[str, str], str]:
    """(station, next station) -> boarding group ID.

    At each station, the stations a train can leave toward are joined when trains toward
    them share a previous station: those trains leave from the same side of the line (Bay
    Fair toward Hayward and toward Castro Valley). A group that would hold trains going
    opposite ways is split back into one group per next station, so no group can.
    A reversing visit never joins groups; its train is still placed by where it goes next.
    """
    by_station: dict[str, set[Boarding]] = defaultdict(set)
    for b in boardings:
        by_station[b.station].add(b)

    mapping: dict[tuple[str, str], str] = {}
    for station, items in by_station.items():
        exits = sorted({b.next_station for b in items})
        parent = {x: x for x in exits}
        toward_from: dict[str, set[str]] = defaultdict(set)  # previous station -> exits
        for b in items:
            if b.previous_station is not None and not b.reverses:
                toward_from[b.previous_station].add(b.next_station)
        for joined in toward_from.values():
            first, *rest = sorted(joined)
            for other in rest:
                parent[_root(parent, other)] = _root(parent, first)

        groups: dict[str, list[str]] = defaultdict(list)
        for x in exits:
            groups[_root(parent, x)].append(x)
        for members in groups.values():
            inside = [b for b in items if b.next_station in members]
            parts = [[x] for x in members] if opposite_pairs(inside) else [members]
            for part in parts:
                for x in part:
                    mapping[(station, x)] = group_id(part)
    return mapping


def _root(parent: dict[str, str], x: str) -> str:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def group_label(destinations: Iterable[str]) -> str:
    """The group's label, e.g. "Toward Daly City and Richmond". A destination that only
    shortens another ("Berryessa" beside "Berryessa/North San Jose") is named once, in its
    longer form."""
    names = sorted(set(destinations))
    shown = [
        d
        for d in names
        if not any(o != d and (o.startswith(d + "/") or o.startswith(d + " (")) for o in names)
    ]
    if not shown:
        return "Toward unlisted destinations"
    if len(shown) == 1:
        return f"Toward {shown[0]}"
    return f"Toward {', '.join(shown[:-1])} and {shown[-1]}"
