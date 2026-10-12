"""Views over processed real-time Parquet, and the static-GTFS enrichment join."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pyarrow as pa

from bart_reliability.transform.flatten import SCHEMA

# How far either side of the provisional 03:00-derived date to look for the real one.
SERVICE_DATE_SEARCH_DAYS = 1
# A scheduled time further than this from the prediction is never a match. Without it,
# a trip whose service is removed today (holiday) could match tomorrow's run, 24h away.
MAX_MATCH_DIFFERENCE_SECONDS = 3 * 3600
GTFS_TIMEZONE = "America/Los_Angeles"

_DUCKDB_TYPES = {
    pa.string(): "VARCHAR",
    pa.int8(): "TINYINT",
    pa.int32(): "INTEGER",
    pa.int64(): "BIGINT",
    pa.date32(): "DATE",
    pa.timestamp("s", tz="UTC"): "TIMESTAMPTZ",
}


def create_realtime_view(con: duckdb.DuckDBPyConnection, processed_dir: Path) -> int:
    """Create rt_trip_updates over the hourly Parquet files. Returns the file count.

    This is a view, not a copy: DuckDB reads the Parquet files at query time, so
    the database stays small and always reflects the latest bart-transform run.
    """
    root = (processed_dir / "trip_updates").resolve()
    files = sorted(root.glob("date=*/hour=*/*.parquet"))
    if files:
        glob = (root / "**" / "*.parquet").as_posix().replace("'", "''")
        source = f"""
            SELECT * EXCLUDE (date, hour), date AS collection_date_utc,
                   hour AS collection_hour_utc
            FROM read_parquet('{glob}', hive_partitioning = true,
                              hive_types = {{'date': DATE, 'hour': INTEGER}})
        """
    else:
        # Same columns, zero rows, so downstream views still work before any data exists.
        cols = ", ".join(f"CAST(NULL AS {_DUCKDB_TYPES[f.type]}) AS {f.name}" for f in SCHEMA)
        source = f"""
            SELECT {cols}, CAST(NULL AS DATE) AS collection_date_utc,
                   CAST(NULL AS INTEGER) AS collection_hour_utc
            WHERE false
        """
    con.execute(f"CREATE VIEW rt_trip_updates AS {source}")
    create_feed_snapshots_view(con, processed_dir)
    return len(files)


def create_feed_snapshots_view(con: duckdb.DuckDBPyConnection, processed_dir: Path) -> str:
    """Create rt_feed_snapshots: one row per processed snapshot, including empty feeds.

    Reads the transformer's trip_update_snapshots manifest. Processed data written
    before the manifest existed falls back to the snapshots that produced rows, which
    cannot show empty feeds. Returns which source was used.
    """
    root = (processed_dir / "trip_update_snapshots").resolve()
    if any(root.glob("date=*/hour=*/*.parquet")):
        glob = (root / "**" / "*.parquet").as_posix().replace("'", "''")
        source, kind = (
            f"""
            SELECT feed_timestamp, collected_at, source_file, entity_count, row_count,
                   'manifest' AS snapshot_source
            FROM read_parquet('{glob}', hive_partitioning = true,
                              hive_types = {{'date': DATE, 'hour': INTEGER}})
            """,
            "manifest",
        )
    else:
        source, kind = (
            """
            SELECT feed_timestamp, any_value(collected_at) AS collected_at,
                   any_value(source_file) AS source_file, CAST(NULL AS INTEGER) AS entity_count,
                   CAST(count(*) AS INTEGER) AS row_count, 'derived_from_rows' AS snapshot_source
            FROM rt_trip_updates GROUP BY feed_timestamp
            """,
            "derived_from_rows",
        )
    con.execute(f"CREATE VIEW rt_feed_snapshots AS {source}")
    return kind


ENRICHED_VIEW_SQL = f"""
CREATE VIEW rt_predictions_enriched AS
WITH rt AS (
    SELECT r.*,
           coalesce(r.predicted_arrival, r.predicted_departure) AS match_time,
           CASE WHEN r.predicted_arrival IS NOT NULL THEN 'arrival'
                WHEN r.predicted_departure IS NOT NULL THEN 'departure' END AS match_time_source
    FROM rt_trip_updates r
),
occurrences AS (
    -- How many times each trip is scheduled at each stop (2 for SFO on some trips).
    SELECT trip_id, stop_id, count(*) AS n
    FROM static_stop_times
    GROUP BY trip_id, stop_id
),
candidates AS (
    -- Every (service date, scheduled occurrence) pair the prediction could refer to:
    -- dates near the provisional date on which the trip's service actually runs.
    SELECT rt.feed_timestamp, rt.trip_id, rt.stop_id,
           d.service_date, st.stop_sequence, st.arrival_seconds, st.departure_seconds,
           -- GTFS times count from "noon minus 12h" local time, which handles DST days.
           CAST(epoch(timezone('{GTFS_TIMEZONE}', d.service_date + INTERVAL 12 HOUR))
                AS BIGINT) - 43200 AS origin_epoch,
           CAST(epoch(rt.match_time) AS BIGINT) AS match_epoch,
           rt.match_time_source
    FROM rt
    JOIN static_trips t ON t.trip_id = rt.trip_id
    JOIN static_stop_times st ON st.trip_id = rt.trip_id AND st.stop_id = rt.stop_id
    JOIN static_service_days d
      ON d.service_id = t.service_id
     AND d.service_date BETWEEN rt.inferred_service_date - {SERVICE_DATE_SEARCH_DAYS}
                            AND rt.inferred_service_date + {SERVICE_DATE_SEARCH_DAYS}
    WHERE rt.match_time IS NOT NULL
),
scored AS (
    SELECT *,
           origin_epoch + CASE WHEN match_time_source = 'arrival'
                               THEN coalesce(arrival_seconds, departure_seconds)
                               ELSE coalesce(departure_seconds, arrival_seconds) END
               AS scheduled_epoch
    FROM candidates
),
best AS (
    -- Nearest scheduled time wins. Candidate dates are 24h apart, so this resolves the
    -- service date first, then picks the closest occurrence on that date.
    SELECT * FROM scored
    WHERE abs(match_epoch - scheduled_epoch) <= {MAX_MATCH_DIFFERENCE_SECONDS}
    QUALIFY row_number() OVER (
        PARTITION BY feed_timestamp, trip_id, stop_id
        ORDER BY abs(match_epoch - scheduled_epoch), service_date, stop_sequence
    ) = 1
),
joined AS (
    SELECT rt.*,
           t.trip_id AS static_trip_id, t.route_id AS static_route_id, t.service_id,
           t.trip_headsign, t.direction_id AS static_direction_id,
           r.route_short_name, r.route_long_name,
           s.stop_id AS static_stop_id, s.stop_name, s.parent_station, s.platform_code,
           o.n AS occurrences,
           b.service_date, b.stop_sequence AS scheduled_stop_sequence,
           b.arrival_seconds AS scheduled_arrival_seconds,
           b.departure_seconds AS scheduled_departure_seconds,
           b.origin_epoch, b.match_epoch - b.scheduled_epoch AS time_difference
    FROM rt
    LEFT JOIN static_trips t ON t.trip_id = rt.trip_id
    LEFT JOIN static_routes r ON r.route_id = t.route_id
    LEFT JOIN static_stops s ON s.stop_id = rt.stop_id
    LEFT JOIN occurrences o ON o.trip_id = rt.trip_id AND o.stop_id = rt.stop_id
    LEFT JOIN best b
      ON b.feed_timestamp = rt.feed_timestamp AND b.trip_id = rt.trip_id
     AND b.stop_id = rt.stop_id
),
classified AS (
    SELECT *,
           CASE WHEN static_trip_id IS NULL THEN 'trip_not_found'
                WHEN static_stop_id IS NULL THEN 'stop_not_found'
                WHEN occurrences IS NULL THEN 'stop_time_not_found'
                WHEN match_time IS NULL THEN 'no_prediction_time'
                WHEN service_date IS NULL THEN 'no_active_service_in_window'
                ELSE 'matched' END AS match_status
    FROM joined
)
SELECT
    -- Real-time prediction (from bart-transform)
    feed_timestamp, collected_at, trip_id, stop_id,
    predicted_arrival, predicted_departure, arrival_delay_s, departure_delay_s,
    arrival_uncertainty_s, trip_schedule_relationship, stop_schedule_relationship,
    prediction_horizon_seconds, source_file, collection_date_utc, collection_hour_utc,
    route_id AS rt_route_id, direction_id AS rt_direction_id, stop_sequence AS rt_stop_sequence,
    -- Static trip, route, and stop
    static_route_id AS route_id, route_short_name, route_long_name, service_id, trip_headsign,
    static_direction_id AS direction_id, stop_name, parent_station, platform_code,
    -- Service date
    inferred_service_date,
    service_date,
    CASE WHEN service_date IS NOT NULL THEN 'static_calendar' END AS service_date_source,
    service_date - inferred_service_date AS service_date_offset_days,
    -- Scheduled stop time on that service date
    scheduled_stop_sequence, scheduled_arrival_seconds, scheduled_departure_seconds,
    to_timestamp(origin_epoch + scheduled_arrival_seconds) AS scheduled_arrival,
    to_timestamp(origin_epoch + scheduled_departure_seconds) AS scheduled_departure,
    -- Match diagnostics
    static_trip_id IS NOT NULL AS trip_found,
    static_stop_id IS NOT NULL AS stop_found,
    match_status,
    CASE WHEN match_status <> 'matched' THEN NULL
         WHEN occurrences = 1 THEN 'unique_stop_time'
         ELSE 'nearest_scheduled_time' END AS match_method,
    CASE WHEN match_status = 'matched' THEN occurrences END AS match_candidate_count,
    CASE WHEN match_status = 'matched' THEN match_time_source END AS match_time_source,
    CAST(time_difference AS INTEGER) AS match_time_difference_seconds,
    coalesce(match_status = 'matched' AND occurrences > 1, false) AS is_ambiguous_match,
    coalesce(match_status = 'matched' AND occurrences = 1, false) AS include_in_primary_metrics
FROM classified
"""


def create_enriched_view(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(ENRICHED_VIEW_SQL)
