"""Chronological, event-grouped train/validation/test assignment."""

from __future__ import annotations

from datetime import date

import duckdb
import pandas as pd

from bart_reliability.modeling.config import SPLITS, LeakageError


def build_model_frame(
    con: duckdb.DuckDBPyConnection,
    split: dict[str, tuple[date, date]],
    quality_tiers: tuple[str, ...],
) -> None:
    """Create eta_model_frame: every example with its split or its exclusion reason.

    The split is decided by the event's service date, so every horizon of an event lands
    in the same split and rows are never split at random. An event whose label is
    confirmed at or after the first prediction of the next split is purged: training on
    it would use an outcome that was not yet known when the next period began.
    """
    cases = " ".join(
        f"WHEN e.service_date BETWEEN DATE '{split[name][0]}' AND DATE '{split[name][1]}' "
        f"THEN '{name}'"
        for name in SPLITS
    )
    tiers = ", ".join(f"'{t}'" for t in quality_tiers)
    order = " ".join(f"WHEN '{name}' THEN {i}" for i, name in enumerate(SPLITS))
    con.execute(
        f"""
        CREATE TABLE eta_model_frame AS
        WITH base AS (
            SELECT e.event_id, e.published_horizon_bucket_s, e.service_date, e.quality_tier,
                   e.prediction_collected_at, e.label_known_at,
                   CASE {cases} END AS assigned_split
            FROM eta_model_examples e
        ),
        kept AS (
            SELECT *, CASE assigned_split {order} END AS split_order
            FROM base WHERE assigned_split IS NOT NULL AND quality_tier IN ({tiers})
        ),
        next_start AS (
            -- First prediction time of the split that follows each split.
            SELECT k.split_order, min(n.prediction_collected_at) AS next_split_starts_at
            FROM (SELECT DISTINCT split_order FROM kept) k
            JOIN kept n ON n.split_order = k.split_order + 1
            GROUP BY 1
        ),
        crossing AS (
            SELECT DISTINCT k.event_id
            FROM kept k JOIN next_start s USING (split_order)
            WHERE k.label_known_at >= s.next_split_starts_at
        ),
        reasons AS (
            SELECT b.*,
                   CASE WHEN b.assigned_split IS NULL THEN 'outside_split_dates'
                        WHEN b.quality_tier NOT IN ({tiers})
                            THEN 'quality_tier_' || b.quality_tier
                        WHEN c.event_id IS NOT NULL THEN 'crosses_split_boundary'
                   END AS exclusion_reason
            FROM base b
            LEFT JOIN crossing c USING (event_id)
        )
        SELECT event_id, published_horizon_bucket_s, service_date, quality_tier,
               prediction_collected_at, label_known_at, assigned_split, exclusion_reason,
               CASE WHEN exclusion_reason IS NULL THEN assigned_split END AS split
        FROM reasons
        ORDER BY event_id, published_horizon_bucket_s
        """
    )


def check_split_integrity(frame: pd.DataFrame) -> dict:
    """Raise LeakageError unless every event sits in one split, in time order.

    `frame` holds the kept rows: event_id, split, prediction_collected_at, label_known_at.
    """
    per_event = frame.groupby("event_id")["split"].nunique()
    if (per_event > 1).any():
        raise LeakageError(f"{int((per_event > 1).sum())} events appear in more than one split")
    bounds = {}
    for name in SPLITS:
        rows = frame[frame["split"] == name]
        if rows.empty:
            raise LeakageError(f"split {name} has no rows")
        bounds[name] = {
            "first_prediction": rows["prediction_collected_at"].min(),
            "last_prediction": rows["prediction_collected_at"].max(),
            "last_label_known": rows["label_known_at"].max(),
        }
    for earlier, later in zip(SPLITS, SPLITS[1:], strict=False):
        if bounds[earlier]["last_label_known"] >= bounds[later]["first_prediction"]:
            raise LeakageError(
                f"a {earlier} label is confirmed at or after the first {later} prediction"
            )
    return bounds
