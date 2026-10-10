"""Unit tests for loading and validating static GTFS into DuckDB."""

from datetime import date

import duckdb
import pytest
from gtfs_fixtures import GTFS_FILES, write_gtfs_zip

from bart_reliability.warehouse.static_gtfs import StaticGTFSError, load_static


@pytest.fixture
def con():
    connection = duckdb.connect()
    yield connection
    connection.close()


def load(con, tmp_path, overrides=None):
    return load_static(con, write_gtfs_zip(tmp_path / "gtfs.zip", overrides))


def replace_row(name, index, row):
    rows = [list(r) for r in GTFS_FILES[name]]
    rows[index] = row
    return {name: rows}


def test_loads_all_tables_with_expected_counts(con, tmp_path):
    result = load(con, tmp_path)
    assert result.row_counts["static_routes"] == 2
    assert result.row_counts["static_trips"] == 5
    assert result.row_counts["static_stop_times"] == 9
    assert result.row_counts["static_calendar_dates"] == 2
    assert result.warnings == []


def test_identifiers_stay_strings_with_leading_zeros(con, tmp_path):
    load(con, tmp_path)
    route = con.execute("SELECT route_id FROM static_trips WHERE trip_id = '0042'").fetchone()
    assert route == ("07",)
    types = dict(
        con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'static_stop_times'"
        ).fetchall()
    )
    assert types["trip_id"] == "VARCHAR"
    assert types["stop_id"] == "VARCHAR"


def test_times_past_midnight_are_seconds_not_wall_clock(con, tmp_path):
    load(con, tmp_path)
    rows = con.execute(
        "SELECT arrival_time, arrival_seconds FROM static_stop_times "
        "WHERE trip_id = 'T_LATE' ORDER BY stop_sequence"
    ).fetchall()
    assert rows == [("24:20:00", 87600), ("27:20:00", 98400)]


def test_single_digit_hour_is_accepted(con, tmp_path):
    load(
        con, tmp_path, replace_row("stop_times.txt", 1, ["T1", "8:00:00", "8:00:00", "A10-1", "1"])
    )
    assert con.execute(
        "SELECT arrival_seconds FROM static_stop_times WHERE trip_id = 'T1' AND stop_sequence = 1"
    ).fetchone() == (28800,)


def test_service_days_apply_calendar_and_exceptions(con, tmp_path):
    load(con, tmp_path)

    def runs(service_id, day):
        sql = "SELECT count(*) FROM static_service_days WHERE service_id = ? AND service_date = ?"
        return con.execute(sql, [service_id, day]).fetchone()[0] == 1

    assert runs("WKDY", date(2026, 10, 9))  # Friday
    assert not runs("WKDY", date(2026, 10, 10))  # Saturday
    assert not runs("WKDY", date(2026, 10, 12))  # Monday removed by calendar_dates
    assert runs("WKDY", date(2026, 10, 13))
    assert runs("SPECIAL", date(2026, 10, 11))  # added by calendar_dates only
    assert con.execute("SELECT count(*) FROM static_service_days").fetchone() == (22 - 1 + 1,)


def test_missing_archive_fails_clearly(con, tmp_path):
    with pytest.raises(StaticGTFSError, match="not found"):
        load_static(con, tmp_path / "missing.zip")


def test_non_zip_fails_clearly(con, tmp_path):
    path = tmp_path / "gtfs.zip"
    path.write_text("<html>404</html>")
    with pytest.raises(StaticGTFSError, match="not a valid ZIP"):
        load_static(con, path)


def test_missing_required_file_fails_clearly(con, tmp_path):
    with pytest.raises(StaticGTFSError, match="calendar_dates.txt"):
        load(con, tmp_path, {"calendar_dates.txt": None})


def test_missing_required_column_fails_clearly(con, tmp_path):
    rows = [r[:4] for r in GTFS_FILES["stop_times.txt"]]  # drop stop_sequence
    with pytest.raises(StaticGTFSError, match="stop_times.txt is missing required columns"):
        load(con, tmp_path, {"stop_times.txt": rows})


@pytest.mark.parametrize("bad_time", ["25:61:00", "8:00", "noon", "08:00:00 PM"])
def test_invalid_time_fails_clearly(con, tmp_path, bad_time):
    overrides = replace_row("stop_times.txt", 1, ["T1", bad_time, "08:00:00", "A10-1", "1"])
    with pytest.raises(StaticGTFSError, match="invalid arrival_time"):
        load(con, tmp_path, overrides)


def test_invalid_date_fails_clearly(con, tmp_path):
    overrides = replace_row("calendar_dates.txt", 1, ["WKDY", "2026-10-12", "2"])
    with pytest.raises(StaticGTFSError, match="invalid date"):
        load(con, tmp_path, overrides)


def test_duplicate_trip_id_fails_clearly(con, tmp_path):
    rows = [*GTFS_FILES["trips.txt"], ["1", "WKDY", "T1", "Dup", "0"]]
    with pytest.raises(StaticGTFSError, match="trips.txt: duplicate key"):
        load(con, tmp_path, {"trips.txt": rows})


def test_ragged_row_fails_clearly(con, tmp_path):
    rows = [*GTFS_FILES["stops.txt"], ["X-1", "Too short"]]
    with pytest.raises(StaticGTFSError, match="stops.txt line 5"):
        load(con, tmp_path, {"stops.txt": rows})


def test_broken_references_are_warnings_not_failures(con, tmp_path):
    rows = [*GTFS_FILES["stop_times.txt"], ["T1", "08:20:00", "08:20:00", "NOPE-1", "3"]]
    result = load(con, tmp_path, {"stop_times.txt": rows})
    assert result.warnings == ["1 rows: stop_times.txt stop_id not in stops.txt"]


def test_provenance_is_recorded(con, tmp_path):
    result = load(con, tmp_path)
    p = result.provenance
    assert p["source_url"] == "https://example.test/google_transit.zip"
    assert p["resolved_url"].endswith("google_transit_v7.zip")
    assert p["archive_sha256"] == result.archive_sha256
    assert p["feed_version"] == "7"
    assert (p["feed_info_start_date"], p["feed_info_end_date"]) == (
        date(2026, 10, 1),
        date(2026, 10, 31),
    )
    assert (p["calendar_start_date"], p["calendar_end_date"]) == (
        date(2026, 10, 1),
        date(2026, 10, 30),
    )
    stored = con.execute("SELECT source_url, feed_version FROM static_feed_load").fetchall()
    assert stored == [("https://example.test/google_transit.zip", "7")]


def test_stale_feed_info_is_reported_not_ignored(con, tmp_path):
    rows = [list(r) for r in GTFS_FILES["feed_info.txt"]]
    rows[1][3:5] = ["20260112", "20260830"]  # like BART's current archive
    result = load(con, tmp_path, {"feed_info.txt": rows})
    assert result.warnings == [
        "feed_info.txt validity (2026-01-12 to 2026-08-30) does not cover the calendar's "
        "service dates (2026-10-01 to 2026-10-30); service dates come from the calendar"
    ]


def test_missing_feed_info_and_source_are_reported(con, tmp_path):
    zip_path = write_gtfs_zip(tmp_path / "gtfs.zip", {"feed_info.txt": None}, source=None)
    result = load_static(con, zip_path)
    assert result.warnings == [
        "no source.json beside the archive: download source and date unknown",
        "feed_info.txt validity dates are missing",
    ]


def test_source_json_for_a_different_archive_fails(con, tmp_path):
    zip_path = write_gtfs_zip(tmp_path / "gtfs.zip")
    (tmp_path / "source.json").write_text('{"sha256": "0000"}')
    with pytest.raises(StaticGTFSError, match="describes a different archive"):
        load_static(con, zip_path)
