"""Read a static GTFS ZIP and load normalized, validated tables into DuckDB."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pyarrow as pa

# Files this project needs, and the columns each must have.
REQUIRED_COLUMNS: dict[str, list[str]] = {
    "agency.txt": ["agency_name", "agency_url", "agency_timezone"],
    "routes.txt": ["route_id", "route_type"],
    "trips.txt": ["route_id", "service_id", "trip_id"],
    "stops.txt": ["stop_id"],
    "stop_times.txt": ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
    "calendar.txt": [
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
    "calendar_dates.txt": ["service_id", "date", "exception_type"],
}
OPTIONAL_FILES = ["feed_info.txt"]

# H:MM:SS or HH:MM:SS, hours may exceed 23 (trips running past midnight).
GTFS_TIME_PATTERN = r"^[0-9]{1,3}:[0-5][0-9]:[0-5][0-9]$"
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class StaticGTFSError(ValueError):
    """Raised when the static GTFS archive is missing, unreadable, or malformed."""


@dataclass(frozen=True)
class StaticLoadResult:
    archive_path: Path
    archive_sha256: str
    row_counts: dict[str, int]
    warnings: list[str]
    provenance: dict


# Optional sidecar next to the archive recording where and when it was downloaded.
SOURCE_FILE = "source.json"


def read_source(zip_path: Path, sha256: str) -> dict:
    """Read <archive dir>/source.json, checking that it describes this exact archive."""
    path = zip_path.with_name(SOURCE_FILE)
    if not path.is_file():
        return {}
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise StaticGTFSError(f"{path} is not valid JSON: {e}") from e
    if source.get("sha256") not in (None, sha256):
        raise StaticGTFSError(
            f"{path} describes a different archive (sha256 {source['sha256']}, actual {sha256})"
        )
    return source


def read_archive(zip_path: Path) -> tuple[dict[str, pa.Table], str]:
    """Read every required file as an all-string Arrow table. Returns (tables, sha256)."""
    if not zip_path.is_file():
        raise StaticGTFSError(f"static GTFS archive not found: {zip_path}")
    data = zip_path.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise StaticGTFSError(f"static GTFS archive is not a valid ZIP: {zip_path}") from e

    with archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise StaticGTFSError(f"corrupt file in static GTFS archive: {bad_member}")
        names = set(archive.namelist())
        missing = [name for name in REQUIRED_COLUMNS if name not in names]
        if missing:
            raise StaticGTFSError(f"static GTFS archive is missing required files: {missing}")

        tables = {}
        for name in [*REQUIRED_COLUMNS, *OPTIONAL_FILES]:
            if name in names:
                tables[name] = _read_csv(archive, name, REQUIRED_COLUMNS.get(name, []))
    return tables, sha256


def _read_csv(archive: zipfile.ZipFile, name: str, required: list[str]) -> pa.Table:
    try:
        text = archive.read(name).decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise StaticGTFSError(f"{name} is not valid UTF-8") from e
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration as e:
        raise StaticGTFSError(f"{name} is empty") from e
    missing = [c for c in required if c not in header]
    if missing:
        raise StaticGTFSError(f"{name} is missing required columns: {missing}")
    if len(set(header)) != len(header):
        raise StaticGTFSError(f"{name} has duplicate column names")

    columns: dict[str, list[str | None]] = {h: [] for h in header}
    for line_number, row in enumerate(reader, start=2):
        if not row:
            continue
        if len(row) != len(header):
            raise StaticGTFSError(
                f"{name} line {line_number}: expected {len(header)} fields, got {len(row)}"
            )
        for column, value in zip(header, row, strict=True):
            value = value.strip()
            columns[column].append(value if value else None)
    # Every column is a string, so identifiers like "01" or "1965520" stay exactly as written.
    return pa.table({c: pa.array(v, pa.string()) for c, v in columns.items()})


def load_static(con: duckdb.DuckDBPyConnection, zip_path: Path) -> StaticLoadResult:
    """Load raw string tables, then build typed, keyed static_* tables from them."""
    tables, sha256 = read_archive(zip_path)
    for name, table in tables.items():
        raw = f"raw_{name.removesuffix('.txt')}"
        con.register("_incoming", table)
        con.execute(f"CREATE TABLE {raw} AS SELECT * FROM _incoming")
        con.unregister("_incoming")

    _validate_raw(con)
    for statement in _normalized_tables(con):
        con.execute(statement)
    con.execute(_SERVICE_DAYS_SQL)
    provenance = _record_provenance(con, zip_path, sha256, "raw_feed_info" in _tables(con))

    counts = {
        table: con.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in STATIC_TABLES
    }
    warnings = _provenance_warnings(provenance) + _referential_warnings(con)
    return StaticLoadResult(zip_path, sha256, counts, warnings, provenance)


def _tables(con) -> set[str]:
    return {row[0] for row in con.execute("SHOW TABLES").fetchall()}


def _record_provenance(con, zip_path: Path, sha256: str, has_feed_info: bool) -> dict:
    """Create static_feed_load: where the archive came from and what period it claims."""
    source = read_source(zip_path, sha256)
    feed_info = (
        """
        (SELECT any_value(feed_version) FROM raw_feed_info) AS feed_version,
        (SELECT CAST(try_strptime(any_value(feed_start_date), '%Y%m%d') AS DATE)
           FROM raw_feed_info) AS feed_info_start_date,
        (SELECT CAST(try_strptime(any_value(feed_end_date), '%Y%m%d') AS DATE)
           FROM raw_feed_info) AS feed_info_end_date
        """
        if has_feed_info
        else """
        CAST(NULL AS VARCHAR) AS feed_version, CAST(NULL AS DATE) AS feed_info_start_date,
        CAST(NULL AS DATE) AS feed_info_end_date
        """
    )
    con.execute(
        f"""
        CREATE TABLE static_feed_load AS
        SELECT ? AS archive_path, ? AS archive_sha256, ? AS archive_label,
               ? AS source_url, ? AS resolved_url, ? AS retrieved, ? AS verified_identical_at,
               {feed_info},
               (SELECT min(service_date) FROM static_service_days) AS calendar_start_date,
               (SELECT max(service_date) FROM static_service_days) AS calendar_end_date
        """,
        [
            str(zip_path),
            sha256,
            zip_path.parent.name,
            source.get("source_url"),
            source.get("resolved_url"),
            source.get("retrieved"),
            source.get("verified_identical_at"),
        ],
    )
    cursor = con.execute("SELECT * FROM static_feed_load")
    names = [d[0] for d in cursor.description]
    return dict(zip(names, cursor.fetchone(), strict=True))


def _provenance_warnings(p: dict) -> list[str]:
    """Stale or missing metadata is reported, never silently ignored."""
    warnings = []
    if not p["source_url"]:
        warnings.append(f"no {SOURCE_FILE} beside the archive: download source and date unknown")
    start, end = p["feed_info_start_date"], p["feed_info_end_date"]
    cal_start, cal_end = p["calendar_start_date"], p["calendar_end_date"]
    if start is None or end is None:
        warnings.append("feed_info.txt validity dates are missing")
    elif cal_start is not None and (start > cal_start or end < cal_end):
        warnings.append(
            f"feed_info.txt validity ({start} to {end}) does not cover the calendar's "
            f"service dates ({cal_start} to {cal_end}); service dates come from the calendar"
        )
    return warnings


STATIC_TABLES = [
    "static_agency",
    "static_routes",
    "static_trips",
    "static_stops",
    "static_stop_times",
    "static_calendar",
    "static_calendar_dates",
    "static_service_days",
]


def _column(con, raw: str, column: str) -> str:
    """Reference an optional column, or NULL if this feed doesn't include it."""
    present = {row[0] for row in con.execute(f"DESCRIBE {raw}").fetchall()}
    return column if column in present else "CAST(NULL AS VARCHAR)"


def _normalized_tables(con) -> list[str]:
    def c(raw, col):
        return _column(con, raw, col)

    weekday_cols = ",\n".join(f"{d} = '1' AS {d}" for d in WEEKDAYS)
    weekday_defs = ",\n".join(f"{d} BOOLEAN NOT NULL" for d in WEEKDAYS)
    return [
        f"""
        CREATE TABLE static_agency AS
        SELECT {c("raw_agency", "agency_id")} AS agency_id, agency_name, agency_url,
               agency_timezone
        FROM raw_agency
        """,
        """
        CREATE TABLE static_routes (
            route_id VARCHAR PRIMARY KEY, agency_id VARCHAR, route_short_name VARCHAR,
            route_long_name VARCHAR, route_type INTEGER NOT NULL, route_color VARCHAR,
            route_text_color VARCHAR
        )
        """,
        f"""
        INSERT INTO static_routes
        SELECT route_id, {c("raw_routes", "agency_id")}, {c("raw_routes", "route_short_name")},
               {c("raw_routes", "route_long_name")}, CAST(route_type AS INTEGER),
               {c("raw_routes", "route_color")}, {c("raw_routes", "route_text_color")}
        FROM raw_routes
        """,
        """
        CREATE TABLE static_trips (
            trip_id VARCHAR PRIMARY KEY, route_id VARCHAR NOT NULL, service_id VARCHAR NOT NULL,
            trip_headsign VARCHAR, direction_id INTEGER, block_id VARCHAR, shape_id VARCHAR
        )
        """,
        f"""
        INSERT INTO static_trips
        SELECT trip_id, route_id, service_id, {c("raw_trips", "trip_headsign")},
               CAST({c("raw_trips", "direction_id")} AS INTEGER), {c("raw_trips", "block_id")},
               {c("raw_trips", "shape_id")}
        FROM raw_trips
        """,
        """
        CREATE TABLE static_stops (
            stop_id VARCHAR PRIMARY KEY, stop_code VARCHAR, stop_name VARCHAR,
            stop_lat DOUBLE, stop_lon DOUBLE, zone_id VARCHAR, location_type INTEGER,
            parent_station VARCHAR, platform_code VARCHAR
        )
        """,
        f"""
        INSERT INTO static_stops
        SELECT stop_id, {c("raw_stops", "stop_code")}, {c("raw_stops", "stop_name")},
               CAST({c("raw_stops", "stop_lat")} AS DOUBLE),
               CAST({c("raw_stops", "stop_lon")} AS DOUBLE),
               {c("raw_stops", "zone_id")}, CAST({c("raw_stops", "location_type")} AS INTEGER),
               {c("raw_stops", "parent_station")}, {c("raw_stops", "platform_code")}
        FROM raw_stops
        """,
        """
        CREATE TABLE static_stop_times (
            trip_id VARCHAR NOT NULL, stop_sequence INTEGER NOT NULL, stop_id VARCHAR NOT NULL,
            arrival_time VARCHAR, departure_time VARCHAR,
            arrival_seconds INTEGER, departure_seconds INTEGER,
            pickup_type INTEGER, drop_off_type INTEGER,
            PRIMARY KEY (trip_id, stop_sequence)
        )
        """,
        f"""
        INSERT INTO static_stop_times
        SELECT trip_id, CAST(stop_sequence AS INTEGER), stop_id, arrival_time, departure_time,
               {_seconds_sql("arrival_time")}, {_seconds_sql("departure_time")},
               CAST({c("raw_stop_times", "pickup_type")} AS INTEGER),
               CAST({c("raw_stop_times", "drop_off_type")} AS INTEGER)
        FROM raw_stop_times
        """,
        f"""
        CREATE TABLE static_calendar (
            service_id VARCHAR PRIMARY KEY, {weekday_defs},
            start_date DATE NOT NULL, end_date DATE NOT NULL
        )
        """,
        f"""
        INSERT INTO static_calendar
        SELECT service_id, {weekday_cols},
               CAST(strptime(start_date, '%Y%m%d') AS DATE),
               CAST(strptime(end_date, '%Y%m%d') AS DATE)
        FROM raw_calendar
        """,
        """
        CREATE TABLE static_calendar_dates (
            service_id VARCHAR NOT NULL, date DATE NOT NULL, exception_type INTEGER NOT NULL,
            PRIMARY KEY (service_id, date)
        )
        """,
        """
        INSERT INTO static_calendar_dates
        SELECT service_id, CAST(strptime(date, '%Y%m%d') AS DATE),
               CAST(exception_type AS INTEGER)
        FROM raw_calendar_dates
        """,
    ]


def _seconds_sql(column: str) -> str:
    """GTFS time -> seconds after the service-day origin, e.g. '25:10:00' -> 90600.

    These are not wall-clock times: hours can exceed 23 for trips running past
    midnight, so they are never parsed as TIME values. The text is validated
    against GTFS_TIME_PATTERN first, so the split is safe.
    """
    return f"""
        CASE WHEN {column} IS NULL THEN NULL ELSE
            CAST(split_part({column}, ':', 1) AS INTEGER) * 3600
            + CAST(split_part({column}, ':', 2) AS INTEGER) * 60
            + CAST(split_part({column}, ':', 3) AS INTEGER)
        END
    """


# Every date each service runs: calendar weekday pattern within its range, plus
# calendar_dates additions (exception_type 1), minus removals (exception_type 2).
_SERVICE_DAYS_SQL = """
CREATE TABLE static_service_days AS
WITH weekly AS (
    SELECT c.service_id, CAST(d.day AS DATE) AS service_date
    FROM static_calendar c,
         generate_series(c.start_date, c.end_date, INTERVAL 1 DAY) AS d(day)
    WHERE CASE isodow(d.day)
        WHEN 1 THEN c.monday WHEN 2 THEN c.tuesday WHEN 3 THEN c.wednesday
        WHEN 4 THEN c.thursday WHEN 5 THEN c.friday WHEN 6 THEN c.saturday
        ELSE c.sunday END
),
added AS (
    SELECT service_id, date AS service_date FROM static_calendar_dates WHERE exception_type = 1
),
removed AS (
    SELECT service_id, date AS service_date FROM static_calendar_dates WHERE exception_type = 2
)
SELECT DISTINCT a.service_id, a.service_date
FROM (SELECT * FROM weekly UNION ALL SELECT * FROM added) a
ANTI JOIN removed r ON r.service_id = a.service_id AND r.service_date = a.service_date
ORDER BY a.service_id, a.service_date
"""


def _validate_raw(con) -> None:
    """Fail with a specific message (and example) for any malformed value or key."""
    checks = [
        ("routes.txt", "route_id", "raw_routes", "route_id IS NULL"),
        ("routes.txt", "route_type", "raw_routes", "TRY_CAST(route_type AS INTEGER) IS NULL"),
        ("trips.txt", "trip_id", "raw_trips", "trip_id IS NULL"),
        ("trips.txt", "route_id", "raw_trips", "route_id IS NULL"),
        ("trips.txt", "service_id", "raw_trips", "service_id IS NULL"),
        ("stops.txt", "stop_id", "raw_stops", "stop_id IS NULL"),
        ("stop_times.txt", "trip_id", "raw_stop_times", "trip_id IS NULL"),
        ("stop_times.txt", "stop_id", "raw_stop_times", "stop_id IS NULL"),
        (
            "stop_times.txt",
            "stop_sequence",
            "raw_stop_times",
            "TRY_CAST(stop_sequence AS INTEGER) IS NULL",
        ),
        ("calendar.txt", "service_id", "raw_calendar", "service_id IS NULL"),
        ("calendar_dates.txt", "service_id", "raw_calendar_dates", "service_id IS NULL"),
        (
            "calendar_dates.txt",
            "exception_type",
            "raw_calendar_dates",
            "exception_type IS NULL OR exception_type NOT IN ('1', '2')",
        ),
    ]
    for column in ("arrival_time", "departure_time"):
        checks.append(
            (
                "stop_times.txt",
                column,
                "raw_stop_times",
                f"{column} IS NOT NULL AND NOT regexp_matches({column}, '{GTFS_TIME_PATTERN}')",
            )
        )
    for day in WEEKDAYS:
        checks.append(
            ("calendar.txt", day, "raw_calendar", f"{day} IS NULL OR {day} NOT IN ('0', '1')")
        )
    for file, raw, column in [
        ("calendar.txt", "raw_calendar", "start_date"),
        ("calendar.txt", "raw_calendar", "end_date"),
        ("calendar_dates.txt", "raw_calendar_dates", "date"),
    ]:
        checks.append(
            (file, column, raw, f"{column} IS NULL OR try_strptime({column}, '%Y%m%d') IS NULL")
        )

    for file, column, raw, bad in checks:
        example = con.execute(f"SELECT {column} FROM {raw} WHERE {bad} LIMIT 1").fetchone()
        if example is not None:
            count = con.execute(f"SELECT count(*) FROM {raw} WHERE {bad}").fetchone()[0]
            raise StaticGTFSError(f"{file}: {count} invalid {column} value(s), e.g. {example[0]!r}")

    for file, raw, keys in [
        ("routes.txt", "raw_routes", ["route_id"]),
        ("trips.txt", "raw_trips", ["trip_id"]),
        ("stops.txt", "raw_stops", ["stop_id"]),
        ("stop_times.txt", "raw_stop_times", ["trip_id", "CAST(stop_sequence AS INTEGER)"]),
        ("calendar.txt", "raw_calendar", ["service_id"]),
        ("calendar_dates.txt", "raw_calendar_dates", ["service_id", "date"]),
    ]:
        key = ", ".join(keys)
        dup = con.execute(
            f"SELECT {key} FROM {raw} GROUP BY {key} HAVING count(*) > 1 LIMIT 1"
        ).fetchone()
        if dup is not None:
            raise StaticGTFSError(f"{file}: duplicate key {dup}")


def _referential_warnings(con) -> list[str]:
    """Broken references are reported, not fatal: the join-quality report shows the impact."""
    checks = [
        (
            "trips.txt route_id not in routes.txt",
            "SELECT count(*) FROM static_trips t "
            "WHERE NOT EXISTS (SELECT 1 FROM static_routes r WHERE r.route_id = t.route_id)",
        ),
        (
            "trips.txt service_id not in calendar.txt or calendar_dates.txt",
            "SELECT count(*) FROM static_trips t WHERE NOT EXISTS "
            "(SELECT 1 FROM static_service_days s WHERE s.service_id = t.service_id)",
        ),
        (
            "stop_times.txt trip_id not in trips.txt",
            "SELECT count(*) FROM static_stop_times st "
            "WHERE NOT EXISTS (SELECT 1 FROM static_trips t WHERE t.trip_id = st.trip_id)",
        ),
        (
            "stop_times.txt stop_id not in stops.txt",
            "SELECT count(*) FROM static_stop_times st "
            "WHERE NOT EXISTS (SELECT 1 FROM static_stops s WHERE s.stop_id = st.stop_id)",
        ),
    ]
    warnings = []
    for label, sql in checks:
        count = con.execute(sql).fetchone()[0]
        if count:
            warnings.append(f"{count} rows: {label}")
    return warnings
