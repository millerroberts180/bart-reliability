"""End-to-end: raw snapshot files on disk -> Parquet partitions -> read back."""

import json
from datetime import UTC, datetime

import pyarrow.dataset as ds
import pyarrow.parquet as pq
import pytest
from google.transit import gtfs_realtime_pb2

from bart_reliability.collector.storage import save_snapshot
from bart_reliability.transform.main import main
from bart_reliability.transform.pipeline import run


def feed_bytes(feed_ts, trips):
    """trips: {trip_id: [stop_id, ...]}; every stop is predicted 10 min after feed_ts."""
    message = gtfs_realtime_pb2.FeedMessage()
    message.header.gtfs_realtime_version = "1.0"
    message.header.timestamp = feed_ts
    for trip_id, stops in trips.items():
        entity = message.entity.add(id=trip_id)
        entity.trip_update.trip.trip_id = trip_id
        for stop_id in stops:
            stu = entity.trip_update.stop_time_update.add(stop_id=stop_id)
            stu.arrival.time = feed_ts + 600
    return message.SerializeToString()


def at(hour, minute, second=0):
    return datetime(2026, 10, 9, hour, minute, second, tzinfo=UTC)


def ts(dt):
    return int(dt.timestamp())


@pytest.fixture
def dirs(tmp_path):
    raw = tmp_path / "raw" / "gtfs_rt"
    out = tmp_path / "processed"
    return raw, out


def save(raw, collected_at, content):
    # Use the collector's own writer so filenames match what's really on disk.
    return save_snapshot(raw, "trip_updates", collected_at, content)


def read_all(out):
    return ds.dataset(out / "trip_updates", format="parquet", partitioning="hive").to_table()


def keys(table):
    return sorted(
        zip(
            [t.timestamp() for t in table.column("feed_timestamp").to_pylist()],
            table.column("trip_id").to_pylist(),
            table.column("stop_id").to_pylist(),
            strict=True,
        )
    )


def test_multiple_snapshots_produce_expected_rows_and_partitions(dirs):
    raw, out = dirs
    save(raw, at(21, 58), feed_bytes(ts(at(21, 58)) - 3, {"T1": ["A", "B"], "T2": ["C"]}))
    save(raw, at(21, 59), feed_bytes(ts(at(21, 59)) - 3, {"T1": ["B"], "T2": ["C"]}))
    save(raw, at(22, 0), feed_bytes(ts(at(22, 0)) - 3, {"T2": ["C", "D"]}))

    summary = run(raw, out)

    assert summary.files_used == 3
    assert summary.rows_written == 7
    assert summary.partitions_written == 2
    part_21 = out / "trip_updates" / "date=2026-10-09" / "hour=21" / "part.parquet"
    part_22 = out / "trip_updates" / "date=2026-10-09" / "hour=22" / "part.parquet"
    assert pq.read_table(part_21).num_rows == 5
    assert pq.read_table(part_22).num_rows == 2

    table = read_all(out)
    assert table.num_rows == 7
    horizons = set(table.column("prediction_horizon_seconds").to_pylist())
    assert horizons == {597}  # arrival is feed_ts + 600, feed_ts is collected_at - 3
    sources = set(table.column("source_file").to_pylist())
    assert "trip_updates/2026-10-09/215800Z.pb" in sources


def test_rerun_produces_no_duplicates(dirs):
    raw, out = dirs
    save(raw, at(21, 58), feed_bytes(ts(at(21, 58)), {"T1": ["A", "B"]}))
    save(raw, at(21, 59), feed_bytes(ts(at(21, 59)), {"T1": ["B"]}))

    run(raw, out)
    first = read_all(out)
    run(raw, out)
    run(raw, out)
    second = read_all(out)

    assert first.num_rows == second.num_rows == 3
    assert keys(first) == keys(second)
    assert len(set(keys(second))) == second.num_rows


def test_rerun_after_new_snapshot_adds_only_new_rows(dirs):
    raw, out = dirs
    save(raw, at(21, 58), feed_bytes(ts(at(21, 58)), {"T1": ["A"]}))
    run(raw, out)
    save(raw, at(21, 59), feed_bytes(ts(at(21, 59)), {"T1": ["A"]}))
    run(raw, out)
    assert read_all(out).num_rows == 2


def test_same_feed_in_two_files_is_counted_once_even_across_hours(dirs):
    raw, out = dirs
    stale = feed_bytes(ts(at(21, 59, 0)), {"T1": ["A", "B"]})
    save(raw, at(21, 59, 30), stale)
    save(raw, at(22, 0, 30), stale)  # BART didn't refresh; identical publication

    summary = run(raw, out)

    assert summary.files_duplicate_feed == 1
    table = read_all(out)
    assert table.num_rows == 2
    assert set(table.column("source_file").to_pylist()) == {"trip_updates/2026-10-09/215930Z.pb"}


def test_empty_feed_is_processed_without_error(dirs):
    raw, out = dirs
    save(raw, at(21, 58), feed_bytes(ts(at(21, 58)), {}))
    summary = run(raw, out)
    assert summary.files_used == 1
    assert summary.rows_written == 0
    assert read_all(out).num_rows == 0


def test_malformed_inputs_are_quarantined_and_batch_continues(dirs):
    raw, out = dirs
    save(raw, at(21, 58), feed_bytes(ts(at(21, 58)), {"T1": ["A"]}))
    save(raw, at(21, 59), b"<html>not protobuf</html>")
    odd = raw / "trip_updates" / "2026-10-09" / "copy-of-snapshot.pb"
    odd.write_bytes(feed_bytes(ts(at(21, 57)), {"T9": ["Z"]}))
    (raw / "trip_updates" / "2026-10-09" / ".abc.tmp").write_bytes(b"partial")

    summary = run(raw, out)

    assert summary.files_found == 3  # hidden temp file is not an input
    assert summary.files_quarantined == 2
    assert read_all(out).num_rows == 1
    manifest = (out / "trip_updates" / "_quarantine.jsonl").read_text().splitlines()
    entries = [json.loads(line) for line in manifest]
    assert [e["source_file"] for e in entries] == [
        "trip_updates/2026-10-09/215900Z.pb",
        "trip_updates/2026-10-09/copy-of-snapshot.pb",
    ]
    assert "invalid feed" in entries[0]["reason"]
    assert "unrecognized snapshot filename" in entries[1]["reason"]
    # Raw inputs are recorded, never moved.
    assert odd.exists()


def test_quarantine_manifest_is_rewritten_not_appended(dirs):
    raw, out = dirs
    save(raw, at(21, 59), b"garbage")
    run(raw, out)
    run(raw, out)
    manifest = (out / "trip_updates" / "_quarantine.jsonl").read_text().splitlines()
    assert len(manifest) == 1


def test_missing_raw_directory_is_not_an_error(dirs):
    raw, out = dirs
    summary = run(raw, out)
    assert summary.files_found == 0


def test_cli_entry_point(dirs, capsys):
    raw, out = dirs
    save(raw, at(21, 58), feed_bytes(ts(at(21, 58)), {"T1": ["A"]}))
    assert main(["--raw-dir", str(raw), "--out-dir", str(out)]) == 0
    log_lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    complete = next(e for e in log_lines if e["event"] == "transform_complete")
    assert complete["rows_written"] == 1
    assert read_all(out).num_rows == 1
