"""Write the rail boarding patterns of a static GTFS archive, the real-schedule fixture for
tests/test_boarding_groups.py (docs/boarding_groups.md, "Tests").

    python -m bart_reliability.api.boarding_patterns \\
        data/raw/gtfs_static/2026-10-08/google_transit.zip \\
        tests/data/bart_boarding_patterns_2026-10-08.csv \\
        --sha256 affdc4d70cac01f71e54f049c754ba36824a885edcdef2ef8b024820c9e93080

A visit is a trip's consecutive scheduled stops at one station (SFO lists two); its
platform is that of its last stop, where the train leaves from. A boarding is a visit that
does not end the trip. Each row counts the scheduled boardings that share every other
column, over every rail trip in the archive (all service days). Bus bridges
(route_type 3) are left out, as in the API. Rows are sorted by their first seven columns
as plain strings, so an empty previous_station_id (a trip starting there) sorts first.
The output is UTF-8 with LF line endings, and the same archive always gives the same bytes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from bart_reliability.api.replay import destination

COLUMNS = (
    "station_id",  # parent station of the visit
    "previous_station_id",  # station of the trip's previous visit; empty at the trip's start
    "next_station_id",  # station of the trip's next visit
    "platform_code",  # platform the train leaves from (platform_code of the visit's last stop)
    "route_short_name",
    "gtfs_direction_id",
    "trip_headsign",
    "destination",  # last part of the headsign ("SFO / SF / Antioch" -> "Antioch")
    "scheduled_departures",  # number of such boardings over every service day in the archive
)
RAIL_ROUTE_TYPE = "1"


def _read(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    with archive.open(name) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline="")))


def boarding_patterns(archive_path: Path) -> list[tuple[str, ...]]:
    with zipfile.ZipFile(archive_path) as archive:
        stops = {s["stop_id"]: s for s in _read(archive, "stops.txt")}
        routes = {
            r["route_id"]: r
            for r in _read(archive, "routes.txt")
            if r["route_type"] == RAIL_ROUTE_TYPE
        }
        trips = {t["trip_id"]: t for t in _read(archive, "trips.txt") if t["route_id"] in routes}
        stop_times: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for st in _read(archive, "stop_times.txt"):
            if st["trip_id"] in trips:
                stop_times[st["trip_id"]].append((int(st["stop_sequence"]), st["stop_id"]))

    counts: Counter[tuple[str, ...]] = Counter()
    for trip_id, sequence in stop_times.items():
        visits: list[tuple[str, str]] = []  # (station, departure platform)
        for _, stop_id in sorted(sequence):
            stop = stops[stop_id]
            station = stop["parent_station"]
            if not station:
                continue  # not a platform of a station; the API skips these too
            if visits and visits[-1][0] == station:
                visits[-1] = (station, stop.get("platform_code", ""))
            else:
                visits.append((station, stop.get("platform_code", "")))
        trip = trips[trip_id]
        route = routes[trip["route_id"]]
        for k, (station, platform) in enumerate(visits[:-1]):  # the last visit ends the trip
            previous = visits[k - 1][0] if k else ""
            counts[
                (
                    station,
                    previous,
                    visits[k + 1][0],
                    platform,
                    route["route_short_name"],
                    trip["direction_id"],
                    trip["trip_headsign"],
                )
            ] += 1
    return [key + (destination(key[6]), str(n)) for key, n in sorted(counts.items())]


def write_patterns(archive_path: Path, out: Path) -> int:
    rows = boarding_patterns(archive_path)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    return len(rows)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("archive", type=Path, help="static GTFS zip")
    parser.add_argument("out", type=Path, help="CSV to write")
    parser.add_argument("--sha256", help="refuse any archive whose SHA-256 differs")
    args = parser.parse_args(argv)
    actual = sha256_of(args.archive)
    if args.sha256 and actual != args.sha256.lower():
        parser.error(f"{args.archive} has SHA-256 {actual}, expected {args.sha256}")
    n = write_patterns(args.archive, args.out)
    print(f"{args.out}: {n} rows from {args.archive.name} (SHA-256 {actual})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
