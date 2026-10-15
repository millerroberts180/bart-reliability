"""Chronological, event-grouped split assignment and its integrity checks."""

from datetime import UTC, date, datetime, timedelta

import duckdb
import pandas as pd
import pytest

from bart_reliability.modeling.config import LeakageError
from bart_reliability.modeling.splits import build_model_frame, check_split_integrity

SPLIT = {
    "train": (date(2026, 10, 6), date(2026, 10, 7)),
    "validation": (date(2026, 10, 8), date(2026, 10, 8)),
    "test": (date(2026, 10, 9), date(2026, 10, 9)),
}


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


def examples(con, events):
    """events: [(event_id, service_day, tier, first_prediction, label_known_at)]"""
    rows = []
    for event_id, day, tier, first, known in events:
        for i, bucket in enumerate((900, 600, 300)):
            rows.append(
                (
                    event_id,
                    bucket,
                    date(2026, 10, day),
                    tier,
                    first + timedelta(minutes=5 * i),
                    known,
                )
            )
    con.execute(
        "CREATE TABLE eta_model_examples (event_id VARCHAR, published_horizon_bucket_s INTEGER, "
        "service_date DATE, quality_tier VARCHAR, prediction_collected_at TIMESTAMPTZ, "
        "label_known_at TIMESTAMPTZ)"
    )
    con.executemany("INSERT INTO eta_model_examples VALUES (?, ?, ?, ?, ?, ?)", rows)


def frame(con):
    return con.execute(
        "SELECT * FROM eta_model_frame ORDER BY event_id, published_horizon_bucket_s"
    ).df()


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute("SET TimeZone = 'UTC'")
    yield c
    c.close()


def test_events_are_split_by_service_date_with_every_horizon_together(con):
    examples(
        con,
        [
            ("e_train", 6, "A", at(6, 15), at(6, 16)),
            ("e_train2", 7, "A", at(7, 15), at(7, 16)),
            ("e_val", 8, "A", at(8, 15), at(8, 16)),
            ("e_test", 9, "A", at(9, 15), at(9, 16)),
        ],
    )
    build_model_frame(con, SPLIT, ("A",))
    f = frame(con)
    assert f.groupby("event_id")["split"].nunique().eq(1).all()
    assert dict(f.groupby("event_id")["split"].first()) == {
        "e_train": "train",
        "e_train2": "train",
        "e_val": "validation",
        "e_test": "test",
    }
    assert f["exclusion_reason"].isna().all()
    assert len(f) == 12


def test_exclusions_outside_dates_and_tier(con):
    examples(
        con,
        [
            ("e_before", 5, "A", at(5, 15), at(5, 16)),
            ("e_after", 10, "A", at(10, 15), at(10, 16)),
            ("e_tier_b", 6, "B", at(6, 15), at(6, 16)),
            ("e_ok", 6, "A", at(6, 17), at(6, 18)),
            ("e_val", 8, "A", at(8, 15), at(8, 16)),
            ("e_test", 9, "A", at(9, 15), at(9, 16)),
        ],
    )
    build_model_frame(con, SPLIT, ("A",))
    reasons = dict(frame(con).groupby("event_id")["exclusion_reason"].first())
    assert reasons["e_before"] == "outside_split_dates"
    assert reasons["e_after"] == "outside_split_dates"
    assert reasons["e_tier_b"] == "quality_tier_B"
    assert pd.isna(reasons["e_ok"])
    excluded = frame(con).query("exclusion_reason.notna()")
    assert excluded["split"].isna().all()


def test_training_label_confirmed_after_validation_starts_is_purged(con):
    examples(
        con,
        [
            # Service day 10-07, but its label is only confirmed after the first
            # validation prediction (10-08 04:00 UTC).
            ("e_late_label", 7, "A", at(8, 3), at(8, 5)),
            ("e_train", 7, "A", at(7, 15), at(7, 16)),
            ("e_val", 8, "A", at(8, 4), at(8, 6)),
            ("e_test", 9, "A", at(9, 15), at(9, 16)),
        ],
    )
    build_model_frame(con, SPLIT, ("A",))
    f = frame(con)
    reasons = dict(f.groupby("event_id")["exclusion_reason"].first())
    assert reasons["e_late_label"] == "crosses_split_boundary"
    assert pd.isna(reasons["e_train"]) and pd.isna(reasons["e_val"])
    kept = f[f["split"].notna()]
    bounds = check_split_integrity(kept)
    assert bounds["train"]["last_label_known"] < bounds["validation"]["first_prediction"]


def test_integrity_check_rejects_event_in_two_splits():
    f = pd.DataFrame(
        {
            "event_id": ["e1", "e1", "e2", "e3"],
            "split": ["train", "validation", "validation", "test"],
            "prediction_collected_at": [at(6, 1), at(8, 1), at(8, 2), at(9, 1)],
            "label_known_at": [at(6, 2), at(8, 2), at(8, 3), at(9, 2)],
        }
    )
    with pytest.raises(LeakageError, match="more than one split"):
        check_split_integrity(f)


def test_integrity_check_rejects_overlapping_time():
    f = pd.DataFrame(
        {
            "event_id": ["e1", "e2", "e3"],
            "split": ["train", "validation", "test"],
            "prediction_collected_at": [at(6, 1), at(8, 1), at(9, 1)],
            "label_known_at": [at(8, 1), at(8, 2), at(9, 2)],  # train label at val start
        }
    )
    with pytest.raises(LeakageError, match="train label"):
        check_split_integrity(f)


def test_integrity_check_requires_every_split():
    f = pd.DataFrame(
        {
            "event_id": ["e1"],
            "split": ["train"],
            "prediction_collected_at": [at(6, 1)],
            "label_known_at": [at(6, 2)],
        }
    )
    with pytest.raises(LeakageError, match="no rows"):
        check_split_integrity(f)
