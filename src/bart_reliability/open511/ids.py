"""How 511 regional BART identifiers relate to BART's own GTFS and GTFS-Realtime IDs.

Verified against the September 2026 historic regional feed (docs/511_arrival_feasibility.md):

| Regional               | BART direct                                       |
|------------------------|---------------------------------------------------|
| trip `BA:1965520:YYYYMMDD` | trip_id `1965520` (prefix and feed-date suffix removed) |
| stop `900101`          | stops.txt `stop_code` (not stop_id, e.g. `K10-1`) |
| route `BA:Blue-N`      | route with route_short_name `Blue-N`              |
| service `= trip_id`    | one service per trip, dates in calendar_dates.txt |
"""

from __future__ import annotations

import re

_TRIP = re.compile(r"^BA:(?P<trip>[^:]+)(?::(?P<suffix>\d{8}))?$")
AGENCY_ID = "BA"


def bart_trip_id(regional_trip_id: str) -> str | None:
    """`BA:1965520:20260930` -> `1965520`; None if it is not a BART regional trip ID."""
    match = _TRIP.match(regional_trip_id or "")
    return match["trip"] if match else None


def bart_route_short_name(regional_route_id: str) -> str | None:
    """`BA:Blue-N` -> `Blue-N`."""
    if not regional_route_id or not regional_route_id.startswith(f"{AGENCY_ID}:"):
        return None
    return regional_route_id.split(":", 1)[1]


def gtfs_seconds(value: str | None) -> int | None:
    """GTFS service-day time `25:10:03` -> 90603 seconds (not a wall-clock time)."""
    if not value:
        return None
    h, m, s = (int(x) for x in value.split(":"))
    return h * 3600 + m * 60 + s
