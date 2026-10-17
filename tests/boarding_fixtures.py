"""A tiny Hayward warehouse for the boarding-group API tests (docs/boarding_groups.md).

Bay Fair (A50), Hayward (A60) and South Hayward (A70), with BART's platforms and the
Orange and Green lines' own direction_id conventions: Orange-N (toward Richmond) and
Green-N (toward Berryessa) are both direction 0, yet they travel opposite ways. One
real-time snapshot lists every train at Hayward, plus:

- a train listed at the platform its schedule does not use there;
- a train whose trip ends at Hayward;
- a train that matches no scheduled trip;
- a bus bridge stopping at the "wrong" platform, which must not create or join a group.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from gtfs_fixtures import feed_bytes, write_gtfs_zip
from modeling_fixtures import DAYS, alert_snapshot, local

from bart_reliability.collector.storage import save_snapshot
from bart_reliability.transform.alerts import run_alerts
from bart_reliability.transform.pipeline import run as run_transform
from bart_reliability.warehouse.build import build_warehouse

DAY = DAYS[3]  # a weekday that service WKDY runs
SNAPSHOT = local(DAY, 8, 0)
AS_OF = SNAPSHOT + timedelta(seconds=30)

STATIONS = {"A50": "Bay Fair", "A60": "Hayward", "A70": "South Hayward"}
ROUTES = [
    ["route_id", "route_short_name", "route_long_name", "route_type"],
    ["3", "Orange-N", "Berryessa/North San Jose to Richmond", "1"],
    ["4", "Orange-S", "Richmond to Berryessa/North San Jose", "1"],
    ["5", "Green-S", "Berryessa/North San Jose to Daly City", "1"],
    ["6", "Green-N", "Daly City to Berryessa/North San Jose", "1"],
    ["BB", "BridgeA", "Bus Bridge", "3"],
]
NORTH, SOUTH = ["A70", "A60", "A50"], ["A50", "A60", "A70"]
# trip_id -> (route, direction_id, headsign, stations in order, first departure h:m)
TRIPS = {
    "OR_N": ("3", "0", "OAK Airport / Richmond", NORTH, (8, 5)),
    "OR_S": ("4", "1", "OAK Airport / Berryessa/North San Jose", SOUTH, (8, 6)),
    "GR_S": ("5", "1", "OAK Airport / SF / Daly City", NORTH, (8, 7)),
    "GR_N": ("6", "0", "SF / OAK Airport / Berryessa", SOUTH, (8, 8)),
    "GR_END": ("5", "1", "Hayward", ["A70", "A60"], (8, 2)),  # ends at Hayward
    "OR_MOVED": ("4", "1", "OAK Airport / Berryessa/North San Jose", SOUTH, (8, 14)),
    "BUS": ("BB", "0", "Bus to Bay Fair", NORTH, (8, 1)),
}
# Platform 1 serves trains toward South Hayward, platform 2 trains toward Bay Fair.
PLATFORM = {("A60", "A70"): "1", ("A60", "A50"): "2", ("A50", "A60"): "1", ("A70", "A60"): "2"}
STOP_MINUTES = 4


def _platform(station: str, stations: list[str], k: int) -> str:
    """The side of the line a train leaves (or, at its last stop, arrives) from."""
    nxt = stations[k + 1] if k + 1 < len(stations) else None
    if nxt is not None:
        return PLATFORM.get((station, nxt), "1")
    prev = stations[k - 1]
    return "1" if (prev, station) in {("A50", "A60"), ("A60", "A70")} else "2"


def stop_time(trip_id: str, k: int):
    _, _, _, stations, (h, m) = TRIPS[trip_id]
    station = stations[k]
    minutes = h * 60 + m + STOP_MINUTES * k
    platform = _platform(station, stations, k)
    if trip_id == "BUS":
        platform = "1" if platform == "2" else "2"  # buses stop on the far side
    return station, f"{station}-{platform}", minutes


def static_overrides() -> dict:
    stops = [
        ["stop_id", "stop_name", "stop_lat", "stop_lon", "location_type", "parent_station"]
        + ["platform_code"]
    ]
    for sid, name in STATIONS.items():
        stops.append([sid, name, "37.6", "-122.1", "1", "", ""])
        for p in ("1", "2"):
            stops.append([f"{sid}-{p}", name, "37.6", "-122.1", "0", sid, p])
    trips = [["route_id", "service_id", "trip_id", "trip_headsign", "direction_id"]]
    stop_times = [["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]]
    for trip_id, (route, direction, headsign, stations, _) in TRIPS.items():
        trips.append([route, "WKDY", trip_id, headsign, direction])
        for k in range(len(stations)):
            _, stop_id, minutes = stop_time(trip_id, k)
            t = f"{minutes // 60:02d}:{minutes % 60:02d}:00"
            stop_times.append([trip_id, t, t, stop_id, str(k + 1)])
    return {
        "routes.txt": ROUTES,
        "stops.txt": stops,
        "trips.txt": trips,
        "stop_times.txt": stop_times,
    }


def hayward_updates() -> list[dict]:
    """What the snapshot lists at Hayward: every train, each at its scheduled time."""
    updates = []
    for trip_id in ("OR_N", "OR_S", "GR_S", "GR_N", "GR_END", "OR_MOVED"):
        stations = TRIPS[trip_id][3]
        _, stop_id, minutes = stop_time(trip_id, stations.index("A60"))
        if trip_id == "OR_MOVED":
            stop_id = "A60-2"  # scheduled on platform 1
        updates.append({"trip_id": trip_id, "stop_id": stop_id, "arrival": local(DAY, 0, minutes)})
    # A real-time trip with no scheduled trip, like the Antioch extension's.
    updates.append({"trip_id": "RT_ONLY", "stop_id": "A60-1", "arrival": local(DAY, 8, 20)})
    return updates


def build_hayward_warehouse(root: Path) -> Path:
    raw = root / "raw" / "gtfs_rt"
    for k in range(3):
        now = SNAPSHOT - timedelta(minutes=2 - k)
        save_snapshot(raw, "trip_updates", now, feed_bytes(now, hayward_updates()))
        save_snapshot(raw, "alerts", now, alert_snapshot(now))
    processed = root / "processed"
    run_transform(raw, processed)
    run_alerts(raw, processed)
    gtfs_zip = write_gtfs_zip(
        root / "gtfs" / "2026-10-01" / "google_transit.zip", static_overrides()
    )
    db = root / "warehouse" / "bart.duckdb"
    build_warehouse(gtfs_zip, processed, db)
    return db
