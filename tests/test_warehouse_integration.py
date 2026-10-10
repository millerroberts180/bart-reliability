"""End to end: synthetic GTFS ZIP + real-time snapshots -> transformer -> DuckDB warehouse."""

import json
from datetime import date

import duckdb
import pytest
from gtfs_fixtures import feed_bytes, utc, write_gtfs_zip

from bart_reliability.collector.storage import save_snapshot
from bart_reliability.transform.pipeline import run as run_transform
from bart_reliability.warehouse.build import build_warehouse
from bart_reliability.warehouse.main import main
from bart_reliability.warehouse.static_gtfs import StaticGTFSError

# (collected_at, [updates]). All local times are PDT (UTC-7).
SNAPSHOTS = [
    # Fri 2026-10-09 08:00 local.
    (
        utc(2026, 10, 9, 15, 0),
        [
            # T1 at Embarcadero: scheduled 08:10, predicted 08:12 (+120 s).
            {
                "trip_id": "T1",
                "stop_id": "M10-1",
                "arrival": utc(2026, 10, 9, 15, 12),
                "delay": 120,
            },
            # Trip unknown to static GTFS (like BART's Antioch extension).
            {"trip_id": "999", "stop_id": "M10-1", "arrival": utc(2026, 10, 9, 15, 5)},
            # Stop unknown to static GTFS.
            {"trip_id": "T1", "stop_id": "ZZZ-1", "arrival": utc(2026, 10, 9, 15, 6)},
            # Known stop that T1 is not scheduled to serve.
            {"trip_id": "T1", "stop_id": "Y10-1", "arrival": utc(2026, 10, 9, 15, 30)},
        ],
    ),
    # SFO twice: scheduled 07:30 (seq 2) and 07:32 (seq 3) local.
    (
        utc(2026, 10, 9, 14, 20),
        [{"trip_id": "T_SFO", "stop_id": "Y10-1", "arrival": utc(2026, 10, 9, 14, 32, 30)}],
    ),
    (
        utc(2026, 10, 9, 14, 21),
        [{"trip_id": "T_SFO", "stop_id": "Y10-1", "arrival": utc(2026, 10, 9, 14, 30, 10)}],
    ),
    # Sat 2026-10-10 03:15 local: provisional date says 10-10, but T_LATE belongs to
    # Friday's service (scheduled 27:20:00 = Sat 03:20 local).
    (
        utc(2026, 10, 10, 10, 15),
        [{"trip_id": "T_LATE", "stop_id": "M10-1", "arrival": utc(2026, 10, 10, 10, 21)}],
    ),
    # Sun 2026-10-11: SPECIAL service added by calendar_dates only, scheduled 10:00 local.
    (
        utc(2026, 10, 11, 16, 50),
        [{"trip_id": "T_SPECIAL", "stop_id": "M10-1", "arrival": utc(2026, 10, 11, 17, 1)}],
    ),
    # Mon 2026-10-12: WKDY removed. Tuesday's run exists but is 24h away.
    (
        utc(2026, 10, 12, 15, 0),
        [{"trip_id": "T1", "stop_id": "M10-1", "arrival": utc(2026, 10, 12, 15, 12)}],
    ),
    # Leading-zero trip ID, scheduled 09:00 local Friday.
    (
        utc(2026, 10, 9, 15, 30),
        [{"trip_id": "0042", "stop_id": "M10-1", "arrival": utc(2026, 10, 9, 16, 0)}],
    ),
]


@pytest.fixture
def warehouse(tmp_path):
    raw = tmp_path / "raw" / "gtfs_rt"
    processed = tmp_path / "processed"
    for collected_at, updates in SNAPSHOTS:
        save_snapshot(raw, "trip_updates", collected_at, feed_bytes(collected_at, updates))
    run_transform(raw, processed)
    gtfs_zip = write_gtfs_zip(tmp_path / "gtfs_static" / "2026-10-08" / "google_transit.zip")
    db = tmp_path / "warehouse" / "bart.duckdb"
    result = build_warehouse(gtfs_zip, processed, db)
    return {"result": result, "db": db, "zip": gtfs_zip, "processed": processed}


def rows(db, where="true"):
    with duckdb.connect(str(db), read_only=True) as con:
        cursor = con.execute(
            f"""
            SELECT trip_id, stop_id, match_status, match_method, match_candidate_count,
                   match_time_difference_seconds, scheduled_stop_sequence, service_date,
                   inferred_service_date, service_date_offset_days, is_ambiguous_match,
                   include_in_primary_metrics, route_id, stop_name,
                   epoch(scheduled_arrival)::BIGINT AS scheduled_arrival_epoch
            FROM rt_predictions_enriched WHERE {where}
            ORDER BY collected_at, trip_id, stop_id
            """
        )
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]


def one(db, where):
    (row,) = rows(db, where)
    return row


def test_unique_match_has_schedule_route_and_stop(warehouse):
    row = one(
        warehouse["db"], "trip_id = 'T1' AND stop_id = 'M10-1' AND collected_at < '2026-10-10'"
    )
    assert row["match_status"] == "matched"
    assert row["match_method"] == "unique_stop_time"
    assert row["match_candidate_count"] == 1
    assert row["match_time_difference_seconds"] == 120
    assert row["scheduled_arrival_epoch"] == int(utc(2026, 10, 9, 15, 10).timestamp())
    assert row["service_date"] == date(2026, 10, 9)
    assert row["route_id"] == "1"
    assert row["stop_name"] == "Embarcadero"
    assert row["include_in_primary_metrics"] is True
    assert row["is_ambiguous_match"] is False


def test_sfo_double_visit_picks_closest_occurrence_and_is_ambiguous(warehouse):
    later, earlier = rows(warehouse["db"], "trip_id = 'T_SFO'")
    # Predicted 07:32:30 -> second visit (07:32), 30 s late.
    assert later["scheduled_stop_sequence"] == 3
    assert later["match_time_difference_seconds"] == 30
    # Predicted 07:30:10 -> first visit (07:30), 10 s late.
    assert earlier["scheduled_stop_sequence"] == 2
    assert earlier["match_time_difference_seconds"] == 10
    for row in (later, earlier):
        assert row["match_status"] == "matched"
        assert row["match_method"] == "nearest_scheduled_time"
        assert row["match_candidate_count"] == 2
        assert row["is_ambiguous_match"] is True
        assert row["include_in_primary_metrics"] is False


def test_after_midnight_trip_resolves_to_previous_service_date(warehouse):
    row = one(warehouse["db"], "trip_id = 'T_LATE'")
    assert row["inferred_service_date"] == date(2026, 10, 10)
    assert row["service_date"] == date(2026, 10, 9)
    assert row["service_date_offset_days"] == -1
    # 27:20:00 on 2026-10-09 is Sat 03:20 PDT.
    assert row["scheduled_arrival_epoch"] == int(utc(2026, 10, 10, 10, 20).timestamp())
    assert row["match_time_difference_seconds"] == 60


def test_calendar_dates_addition_is_used(warehouse):
    row = one(warehouse["db"], "trip_id = 'T_SPECIAL'")
    assert row["match_status"] == "matched"
    assert row["service_date"] == date(2026, 10, 11)


def test_removed_service_day_does_not_match_a_run_24h_away(warehouse):
    row = one(warehouse["db"], "trip_id = 'T1' AND collected_at > '2026-10-12'")
    assert row["match_status"] == "no_active_service_in_window"
    assert row["service_date"] is None
    assert row["include_in_primary_metrics"] is False


def test_leading_zero_trip_id_matches_exactly(warehouse):
    row = one(warehouse["db"], "trip_id = '0042'")
    assert row["match_status"] == "matched"
    assert row["route_id"] == "07"


@pytest.mark.parametrize(
    ("trip_id", "stop_id", "status"),
    [
        ("999", "M10-1", "trip_not_found"),
        ("T1", "ZZZ-1", "stop_not_found"),
        ("T1", "Y10-1", "stop_time_not_found"),
    ],
)
def test_unmatched_records_are_kept_and_labelled(warehouse, trip_id, stop_id, status):
    row = one(warehouse["db"], f"trip_id = '{trip_id}' AND stop_id = '{stop_id}'")
    assert row["match_status"] == status
    assert row["match_method"] is None
    assert row["include_in_primary_metrics"] is False


def test_join_quality_metrics(warehouse):
    q = warehouse["result"].quality
    assert q["predictions"] == 10
    assert q["trip_matched"] == 9
    assert q["stop_matched"] == 9
    assert q["stop_time_matched"] == 6
    assert q["ambiguous"] == 2
    assert q["primary_eligible"] == 4
    assert q["pct_trip_matched"] == 90.0
    assert q["pct_stop_time_matched"] == 60.0
    assert q["unmatched_by_status"] == {
        "trip_not_found": 1,
        "stop_not_found": 1,
        "stop_time_not_found": 1,
        "no_active_service_in_window": 1,
    }
    assert {e["trip_id"] for e in q["unmatched_examples"]} == {"999", "T1"}


def test_rerun_is_idempotent(warehouse):
    first = rows(warehouse["db"])
    again = build_warehouse(warehouse["zip"], warehouse["processed"], warehouse["db"])
    assert rows(warehouse["db"]) == first
    assert again.static.row_counts == warehouse["result"].static.row_counts
    leftovers = [p.name for p in warehouse["db"].parent.iterdir()]
    assert leftovers == ["bart.duckdb"]


def test_realtime_data_is_only_views_not_copied_tables(warehouse):
    with duckdb.connect(str(warehouse["db"]), read_only=True) as con:
        views = {
            r[0]
            for r in con.execute(
                "SELECT view_name FROM duckdb_views() WHERE NOT internal"
            ).fetchall()
        }
        copied = con.execute(
            "SELECT count(*) FROM duckdb_tables() WHERE table_name LIKE 'rt\\_%' ESCAPE '\\'"
        ).fetchone()[0]
    assert {
        "rt_trip_updates",
        "rt_predictions_enriched",
        "rt_join_quality",
        "rt_unmatched_summary",
    } <= views
    assert copied == 0


def test_failed_build_keeps_previous_warehouse(warehouse, tmp_path):
    before = rows(warehouse["db"])
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(StaticGTFSError):
        build_warehouse(bad, warehouse["processed"], warehouse["db"])
    assert rows(warehouse["db"]) == before
    assert [p.name for p in warehouse["db"].parent.iterdir()] == ["bart.duckdb"]


def test_builds_with_no_realtime_data(tmp_path):
    gtfs_zip = write_gtfs_zip(tmp_path / "gtfs.zip")
    result = build_warehouse(gtfs_zip, tmp_path / "processed", tmp_path / "w" / "bart.duckdb")
    assert result.parquet_files == 0
    assert result.quality["predictions"] == 0
    assert result.quality["pct_trip_matched"] is None


def test_cli_reports_quality_and_fails_clearly_on_missing_archive(warehouse, tmp_path, capsys):
    db = tmp_path / "cli" / "bart.duckdb"
    args = ["--gtfs-zip", str(warehouse["zip"]), "--processed-dir", str(warehouse["processed"])]
    assert main([*args, "--db", str(db)]) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    quality = next(e for e in events if e["event"] == "join_quality")
    assert quality["pct_trip_matched"] == 90.0

    missing = ["--gtfs-zip", str(tmp_path / "nope.zip"), "--db", str(db)]
    assert main(missing) == 2
    error = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert error["event"] == "static_gtfs_invalid"
    assert "not found" in error["reason"]
