from datetime import UTC, datetime, timedelta, timezone

import pytest

from bart_reliability.collector.storage import save_snapshot, snapshot_path

COLLECTED_AT = datetime(2026, 10, 9, 21, 15, 0, 123456, tzinfo=UTC)


def test_path_uses_feed_folder_date_folder_and_utc_time(tmp_path):
    path = snapshot_path(tmp_path, "alerts", COLLECTED_AT)
    assert path == tmp_path / "alerts" / "2026-10-09" / "211500Z.pb"


def test_path_rejects_naive_and_non_utc_times(tmp_path):
    with pytest.raises(ValueError):
        snapshot_path(tmp_path, "alerts", datetime(2026, 10, 9, 21, 15))
    pacific = timezone(timedelta(hours=-7))
    with pytest.raises(ValueError):
        snapshot_path(tmp_path, "alerts", COLLECTED_AT.astimezone(pacific))


def test_save_writes_exact_bytes(tmp_path, trip_update_bytes):
    path = save_snapshot(tmp_path, "trip_updates", COLLECTED_AT, trip_update_bytes)
    assert path.read_bytes() == trip_update_bytes


def test_save_never_overwrites_existing_snapshot(tmp_path):
    path = save_snapshot(tmp_path, "alerts", COLLECTED_AT, b"first")
    with pytest.raises(FileExistsError):
        save_snapshot(tmp_path, "alerts", COLLECTED_AT, b"second")
    assert path.read_bytes() == b"first"


def test_same_time_different_feeds_do_not_collide(tmp_path):
    a = save_snapshot(tmp_path, "trip_updates", COLLECTED_AT, b"trips")
    b = save_snapshot(tmp_path, "alerts", COLLECTED_AT, b"alerts")
    assert a != b
    assert a.read_bytes() == b"trips"
    assert b.read_bytes() == b"alerts"


def test_no_temp_files_left_behind(tmp_path):
    path = save_snapshot(tmp_path, "alerts", COLLECTED_AT, b"data")
    with pytest.raises(FileExistsError):
        save_snapshot(tmp_path, "alerts", COLLECTED_AT, b"data")
    assert [p.name for p in path.parent.iterdir()] == [path.name]
