"""Join-quality metrics for the enriched prediction view."""

from __future__ import annotations

import duckdb

# A matched row "agrees" with BART when predicted - scheduled is within this many
# seconds of BART's own published delay. Evidence for (not proof of) a correct match.
# BART's absolute times are ~1 min later than scheduled + delay (median +58 s on the
# first real batch), so 60 s is too strict. 120 s cannot tell apart two scheduled
# visits 2 min apart (SFO), so agreement does not validate ambiguous matches.
DELAY_AGREEMENT_TOLERANCE_S = 120

JOIN_QUALITY_VIEW_SQL = f"""
CREATE VIEW rt_join_quality AS
SELECT
    count(*) AS predictions,
    count(*) FILTER (WHERE trip_found) AS trip_matched,
    count(*) FILTER (WHERE stop_found) AS stop_matched,
    count(*) FILTER (WHERE match_status = 'matched') AS stop_time_matched,
    count(*) FILTER (WHERE include_in_primary_metrics) AS primary_eligible,
    count(*) FILTER (WHERE is_ambiguous_match) AS ambiguous,
    count(*) FILTER (WHERE match_status = 'matched' AND service_date_offset_days <> 0)
        AS service_date_differs_from_inferred,
    count(*) FILTER (WHERE match_status = 'matched' AND NOT is_ambiguous_match
                     AND arrival_delay_s IS NOT NULL) AS unique_with_delay,
    count(*) FILTER (WHERE match_status = 'matched' AND NOT is_ambiguous_match
                     AND abs(match_time_difference_seconds - arrival_delay_s)
                         <= {DELAY_AGREEMENT_TOLERANCE_S}) AS unique_delay_agrees,
    count(*) FILTER (WHERE is_ambiguous_match AND arrival_delay_s IS NOT NULL)
        AS ambiguous_with_delay,
    count(*) FILTER (WHERE is_ambiguous_match
                     AND abs(match_time_difference_seconds - arrival_delay_s)
                         <= {DELAY_AGREEMENT_TOLERANCE_S}) AS ambiguous_delay_agrees
FROM rt_predictions_enriched
"""

UNMATCHED_VIEW_SQL = """
CREATE VIEW rt_unmatched_summary AS
SELECT match_status, trip_id,
       count(*) AS predictions,
       count(DISTINCT stop_id) AS distinct_stops,
       list(DISTINCT stop_id ORDER BY stop_id) AS stop_ids,
       min(collected_at) AS first_collected_at,
       max(collected_at) AS last_collected_at,
       list(DISTINCT trip_schedule_relationship) AS trip_schedule_relationships
FROM rt_predictions_enriched
WHERE match_status <> 'matched'
GROUP BY match_status, trip_id
"""


def create_quality_views(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(JOIN_QUALITY_VIEW_SQL)
    con.execute(UNMATCHED_VIEW_SQL)


def join_quality(con: duckdb.DuckDBPyConnection, example_limit: int = 5) -> dict:
    """Return match rates, unmatched counts by status, and example unmatched trips."""
    cursor = con.execute("SELECT * FROM rt_join_quality")
    names = [d[0] for d in cursor.description]
    q = dict(zip(names, cursor.fetchone(), strict=True))

    total = q["predictions"]

    def pct(n: int, d: int = total) -> float | None:
        return round(100 * n / d, 2) if d else None

    by_status = dict(
        con.execute(
            "SELECT match_status, count(*) FROM rt_predictions_enriched GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
    )
    examples = [
        {
            "match_status": status,
            "trip_id": trip_id,
            "predictions": n,
            "stop_ids": stop_ids[:6],
        }
        for status, trip_id, n, stop_ids in con.execute(
            "SELECT match_status, trip_id, predictions, stop_ids FROM rt_unmatched_summary "
            "ORDER BY predictions DESC, trip_id LIMIT ?",
            [example_limit],
        ).fetchall()
    ]
    return {
        **q,
        "pct_trip_matched": pct(q["trip_matched"]),
        "pct_stop_matched": pct(q["stop_matched"]),
        "pct_stop_time_matched": pct(q["stop_time_matched"]),
        "pct_primary_eligible": pct(q["primary_eligible"]),
        "pct_unique_delay_agrees": pct(q["unique_delay_agrees"], q["unique_with_delay"]),
        "pct_ambiguous_delay_agrees": pct(q["ambiguous_delay_agrees"], q["ambiguous_with_delay"]),
        "unmatched_by_status": {k: v for k, v in by_status.items() if k != "matched"},
        "unmatched_examples": examples,
    }
