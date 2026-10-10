"""A tiny synthetic BART-like GTFS feed and matching real-time snapshots.

Service WKDY runs Mon-Fri in October 2026 (PDT, UTC-7) except Mon 2026-10-12,
which calendar_dates removes. Service SPECIAL exists only as a calendar_dates
addition on Sun 2026-10-11.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from google.transit import gtfs_realtime_pb2

GTFS_FILES: dict[str, list[list[str]]] = {
    "agency.txt": [
        ["agency_id", "agency_name", "agency_url", "agency_timezone"],
        ["BART", "Bay Area Rapid Transit", "https://www.bart.gov/", "America/Los_Angeles"],
    ],
    "routes.txt": [
        ["route_id", "route_short_name", "route_long_name", "route_type"],
        ["1", "Yellow-S", "Antioch to SFO/Millbrae", "1"],
        ["07", "Red-S", "Richmond to SFO/Millbrae", "1"],
    ],
    "trips.txt": [
        ["route_id", "service_id", "trip_id", "trip_headsign", "direction_id"],
        ["1", "WKDY", "T1", "Millbrae", "0"],
        ["07", "WKDY", "T_SFO", "SFO / Millbrae", "0"],
        ["1", "WKDY", "T_LATE", "Millbrae", "0"],
        ["1", "SPECIAL", "T_SPECIAL", "Millbrae", "0"],
        ["07", "WKDY", "0042", "Millbrae", "1"],
    ],
    "stops.txt": [
        ["stop_id", "stop_name", "stop_lat", "stop_lon", "location_type", "parent_station"],
        ["A10-1", "Lake Merritt", "37.797", "-122.265", "0", "LAKE"],
        ["M10-1", "Embarcadero", "37.793", "-122.397", "0", "EMBR"],
        ["Y10-1", "San Francisco International Airport", "37.616", "-122.392", "0", "SFIA"],
    ],
    "stop_times.txt": [
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        ["T1", "08:00:00", "08:00:00", "A10-1", "1"],
        ["T1", "08:10:00", "08:11:00", "M10-1", "2"],
        # Visits SFO twice, two minutes apart, like BART's Red/Yellow trips.
        ["T_SFO", "07:00:00", "07:00:00", "M10-1", "1"],
        ["T_SFO", "07:30:00", "07:30:00", "Y10-1", "2"],
        ["T_SFO", "07:32:00", "07:32:00", "Y10-1", "3"],
        # Runs after midnight: times past 24:00:00 on the previous service day.
        ["T_LATE", "24:20:00", "24:20:00", "A10-1", "1"],
        ["T_LATE", "27:20:00", "27:20:00", "M10-1", "2"],
        ["T_SPECIAL", "10:00:00", "10:00:00", "M10-1", "1"],
        ["0042", "09:00:00", "09:00:00", "M10-1", "1"],
    ],
    "calendar.txt": [
        [
            "service_id",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "start_date",
            "end_date",
        ],
        ["WKDY", "1", "1", "1", "1", "1", "0", "0", "20261001", "20261031"],
    ],
    "calendar_dates.txt": [
        ["service_id", "date", "exception_type"],
        ["WKDY", "20261012", "2"],
        ["SPECIAL", "20261011", "1"],
    ],
    "feed_info.txt": [
        [
            "feed_publisher_name",
            "feed_publisher_url",
            "feed_lang",
            "feed_start_date",
            "feed_end_date",
            "feed_version",
        ],
        ["Bay Area Rapid Transit", "http://www.bart.gov", "en", "20261001", "20261031", "7"],
    ],
}

SOURCE = {
    "source_url": "https://example.test/google_transit.zip",
    "resolved_url": "https://example.test/files/google_transit_v7.zip",
    "retrieved": "2026-10-01T00:00:00Z",
}


def write_gtfs_zip(
    path: Path,
    overrides: dict[str, list[list[str]] | None] | None = None,
    source: dict | None = SOURCE,
) -> Path:
    """Write the synthetic feed; overrides replace a file's rows, or drop it when None.

    Also writes source.json provenance beside it unless source is None.
    """
    files = {**GTFS_FILES, **(overrides or {})}
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, rows in files.items():
            if rows is None:
                continue
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator="\n").writerows(rows)
            archive.writestr(name, buffer.getvalue())
    if source is not None:
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_name("source.json").write_text(json.dumps({**source, "sha256": sha256}))
    return path


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def feed_bytes(feed_time: datetime, updates: list[dict]) -> bytes:
    """updates: [{"trip_id", "stop_id", "arrival": datetime, "delay": int}, ...]"""
    message = gtfs_realtime_pb2.FeedMessage()
    message.header.gtfs_realtime_version = "1.0"
    message.header.timestamp = int(feed_time.timestamp())
    by_trip: dict[str, list[dict]] = {}
    for update in updates:
        by_trip.setdefault(update["trip_id"], []).append(update)
    for trip_id, stops in by_trip.items():
        entity = message.entity.add(id=trip_id)
        entity.trip_update.trip.trip_id = trip_id
        for stop in stops:
            stu = entity.trip_update.stop_time_update.add(stop_id=stop["stop_id"])
            stu.arrival.time = int(stop["arrival"].timestamp())
            stu.arrival.delay = stop.get("delay", 0)
    return message.SerializeToString()
