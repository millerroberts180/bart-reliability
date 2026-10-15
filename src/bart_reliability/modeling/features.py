"""Point-in-time modeling examples and features, built in DuckDB SQL.

Runs in a separate DuckDB file with the warehouse attached read-only. Unqualified names
resolve first to the modeling database, then to the warehouse.

An example is one eligible stop-arrival event at one *published* horizon: the snapshot
in which BART's own ETA said the train was about 300, 600 or 900 s away. The horizon is
chosen from information available at that snapshot. The descriptive table
`eta_revision_examples` chooses horizons by time to the final estimate instead, which
uses the outcome (docs/modeling_plan.md).

Every feature uses only the prediction snapshot, earlier snapshots, or the static
schedule. `eta_model_feature_checks` verifies this on every build.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

import duckdb

from bart_reliability.warehouse.alerts import (
    ALERT_SNAPSHOT_MAX_AGE_S,
    example_alert_context_statements,
)

# Trailing window for recent ETA movement, and the look-back for recent collection gaps.
TRAILING_WINDOW_S = 300
GAP_LOOKBACK_S = 900
GTFS_TIMEZONE = "America/Los_Angeles"

KEY_COLUMNS = ("event_id", "published_horizon_bucket_s")


@dataclass(frozen=True)
class Feature:
    name: str
    kind: str  # "numeric" or "categorical"
    known_because: str


# The only columns a model may use. The config selects from this catalog.
FEATURES = (
    Feature("published_horizon_bucket_s", "categorical", "bucket of the current published ETA"),
    Feature("published_horizon_s", "numeric", "current published ETA minus snapshot time"),
    Feature(
        "published_minus_scheduled_s", "numeric", "current published ETA minus static schedule"
    ),
    Feature("route_short_name", "categorical", "static trip attribute"),
    Feature("stop_id", "categorical", "static stop"),
    Feature("stop_position", "numeric", "static position of the stop in the trip"),
    Feature("stops_away", "numeric", "stops the trip lists ahead of this one in the snapshot"),
    Feature("hour_local", "categorical", "Pacific clock hour of the snapshot"),
    Feature("service_day_type", "categorical", "static service calendar of the trip"),
    Feature("seconds_since_first_seen", "numeric", "earlier snapshots of this trip-stop"),
    Feature("missing_snapshots_so_far", "numeric", "earlier snapshots of this trip-stop"),
    Feature("eta_change_last_snapshot_s", "numeric", "previous listing of this trip-stop"),
    Feature("eta_change_last_5min_s", "numeric", "listings in the trailing 300 s"),
    Feature("eta_change_since_first_seen_s", "numeric", "first listing of this trip-stop"),
    Feature("prior_change_count", "numeric", "earlier listings of this trip-stop"),
    Feature("prior_abs_change_sum_s", "numeric", "earlier listings of this trip-stop"),
    Feature("snapshot_gap_before_s", "numeric", "collection gap before this snapshot"),
    Feature("max_snapshot_gap_last_15min_s", "numeric", "collection gaps in the last 900 s"),
    Feature("has_applicable_visible_alert", "categorical", "latest alert snapshot at or before"),
    Feature("alert_context_group", "categorical", "latest alert snapshot at or before"),
)
FEATURE_KINDS = {f.name: f.kind for f in FEATURES}

# Columns that encode the outcome, observations after the snapshot, label quality, or
# the completed event. A model must never use them (docs/modeling_plan.md).
PROHIBITED_COLUMNS = frozenset(
    {
        # The endpoint
        "final_stable_estimate",
        "proxy_arrival",
        "last_estimate_arrival",
        "final_estimates",
        "final_estimate_spread_s",
        "uncertainty_s",
        # The target and its derivatives
        "eta_revision_seconds",
        "absolute_eta_revision_seconds",
        "revision_direction",
        "large_revision",
        "time_to_proxy_s",
        # Horizon chosen by time to the final estimate
        "target_horizon_s",
        # Observed after the prediction snapshot
        "last_seen_at",
        "confirmed_absent_at",
        "confirmed_absent_feed_timestamp",
        "label_known_at",
        "next_snapshot_min_stop_position",
        "observation_count",
        "snapshots_in_span",
        "stop_missing_snapshots",
        "trip_missing_snapshots",
        "max_collection_gap_s",
        "listed_after_estimate_s",
        "confirmed_absent_after_estimate_s",
        "disappearance_window_s",
        "observation_rank_from_end",
        "horizons_available",
        # Label-quality flags
        "quality_tier",
        "is_eligible",
        "exclusion_reason",
        # Identifiers and raw time
        "event_id",
        "trip_id",
        "snapshot_index",
        "prediction_collected_at",
        "prediction_feed_timestamp",
        "service_date",
        "split",
    }
)

# Non-feature columns kept in eta_model_features so the checks can audit each row.
AUDIT_COLUMNS = (
    "prediction_collected_at",
    "prediction_feed_timestamp",
    "observations_so_far",
    "history_first_collected_at",
    "history_last_collected_at",
    "trailing_window_start_collected_at",
    "alert_snapshot_feed_timestamp",
)


@dataclass(frozen=True)
class HorizonSettings:
    targets_s: tuple[int, ...]
    tolerance_s: int
    stability_window: int


def warehouse_horizon_settings(con: duckdb.DuckDBPyConnection) -> HorizonSettings:
    """Horizon targets, tolerance and final window, as recorded by the warehouse build."""
    values = dict(con.execute("SELECT parameter, value FROM eta_revision_config").fetchall())
    return HorizonSettings(
        targets_s=tuple(int(t) for t in ast.literal_eval(values["horizon_targets_s"])),
        tolerance_s=int(values["horizon_tolerance_s"]),
        stability_window=int(values["stability_window"]),
    )


def build_feature_tables(con: duckdb.DuckDBPyConnection) -> dict:
    """Create the example, alert-context, feature and check tables. Returns a report."""
    settings = warehouse_horizon_settings(con)
    for statement in _statements(settings):
        con.execute(statement)
    for statement in example_alert_context_statements(
        ALERT_SNAPSHOT_MAX_AGE_S,
        examples="eta_model_examples",
        horizon="published_horizon_bucket_s",
        bridge="eta_model_example_alerts",
        context="eta_model_alert_context",
    ):
        con.execute(statement)
    con.execute(_FEATURES_SQL)
    con.execute(_checks_sql(settings))
    for name in ("_model_obs", "_model_candidates"):
        con.execute(f"DROP TABLE {name}")
    return feature_report(con, settings)


def _statements(s: HorizonSettings) -> list[str]:
    targets = ", ".join(str(t) for t in s.targets_s)
    return [
        # Every published estimate of every eligible event, with the change since the
        # previous listing (lag() only looks backward). rank_from_end needs the whole
        # event, so it is used only to exclude the estimates that define the endpoint.
        """
        CREATE TEMP TABLE _model_obs AS
        SELECT p.event_id, r.collected_at, r.feed_timestamp, t.snapshot_index,
               r.predicted_arrival,
               CAST(epoch(r.predicted_arrival) - epoch(r.collected_at) AS INTEGER)
                   AS published_horizon_s,
               CAST(epoch(r.predicted_arrival)
                    - epoch(lag(r.predicted_arrival) OVER w) AS INTEGER) AS change_s,
               row_number() OVER (PARTITION BY p.event_id ORDER BY t.snapshot_index DESC)
                   AS rank_from_end
        FROM observed_arrival_proxy p
        JOIN rt_trip_updates r
          ON r.trip_id = p.trip_id AND r.stop_id = p.stop_id
         AND r.collected_at BETWEEN p.first_seen_at AND p.last_seen_at
        JOIN proxy_snapshot_timeline t ON t.feed_timestamp = r.feed_timestamp
        WHERE p.is_eligible
        WINDOW w AS (PARTITION BY p.event_id ORDER BY t.snapshot_index)
        """,
        # Estimates whose published-time horizon is within tolerance of a bucket.
        f"""
        CREATE TEMP TABLE _model_candidates AS
        SELECT o.*, b.published_horizon_bucket_s
        FROM _model_obs o, (SELECT unnest([{targets}]) AS published_horizon_bucket_s) b
        WHERE abs(o.published_horizon_s - b.published_horizon_bucket_s) <= {s.tolerance_s}
        """,
        # One example per event and bucket: the estimate whose published-time horizon is
        # closest to the bucket, within tolerance, outside the final window. Ties go to
        # the earlier snapshot.
        f"""
        CREATE TABLE eta_model_examples AS
        SELECT c.event_id, c.published_horizon_bucket_s,
               c.collected_at AS prediction_collected_at,
               c.feed_timestamp AS prediction_feed_timestamp, c.snapshot_index,
               c.predicted_arrival AS published_estimate, c.published_horizon_s,
               p.service_date, p.trip_id, p.quality_tier,
               p.confirmed_absent_at AS label_known_at,
               p.proxy_arrival AS final_stable_estimate,
               CAST(epoch(p.proxy_arrival) - epoch(c.collected_at) AS INTEGER)
                   AS time_to_proxy_s,
               CAST(epoch(p.proxy_arrival) - epoch(c.predicted_arrival) AS INTEGER)
                   AS eta_revision_seconds,
               CAST(abs(epoch(p.proxy_arrival) - epoch(c.predicted_arrival)) AS INTEGER)
                   AS absolute_eta_revision_seconds
        FROM _model_candidates c
        JOIN observed_arrival_proxy p USING (event_id)
        WHERE c.rank_from_end > {s.stability_window}
        QUALIFY row_number() OVER (
            PARTITION BY c.event_id, c.published_horizon_bucket_s
            ORDER BY abs(c.published_horizon_s - c.published_horizon_bucket_s), c.snapshot_index
        ) = 1
        ORDER BY c.event_id, c.published_horizon_bucket_s
        """,
        # Why an eligible event has no example at a bucket.
        f"""
        CREATE TABLE eta_model_example_coverage AS
        WITH within AS (
            SELECT event_id, published_horizon_bucket_s,
                   bool_or(rank_from_end > {s.stability_window}) AS outside_final_window
            FROM _model_candidates
            GROUP BY ALL
        )
        SELECT p.event_id, b.published_horizon_bucket_s, p.service_date, p.quality_tier,
               CASE WHEN w.event_id IS NULL THEN 'no_estimate_within_tolerance'
                    WHEN NOT w.outside_final_window THEN 'only_in_final_window'
               END AS missing_reason
        FROM observed_arrival_proxy p
        CROSS JOIN (SELECT unnest([{targets}]) AS published_horizon_bucket_s) b
        LEFT JOIN within w USING (event_id, published_horizon_bucket_s)
        WHERE p.is_eligible
        ORDER BY p.event_id, b.published_horizon_bucket_s
        """,
    ]


_FEATURES_SQL = f"""
CREATE TABLE eta_model_features AS
WITH hist AS (
    -- Listings of this trip-stop up to and including the prediction snapshot.
    SELECT e.event_id, e.published_horizon_bucket_s,
           count(*) AS observations_so_far,
           min(o.snapshot_index) AS first_snapshot_index,
           min(o.collected_at) AS history_first_collected_at,
           max(o.collected_at) AS history_last_collected_at,
           arg_min(o.predicted_arrival, o.snapshot_index) AS first_estimate,
           count(*) FILTER (WHERE o.change_s <> 0) AS prior_change_count,
           coalesce(sum(abs(o.change_s)), 0) AS prior_abs_change_sum_s
    FROM eta_model_examples e
    JOIN _model_obs o ON o.event_id = e.event_id AND o.snapshot_index <= e.snapshot_index
    GROUP BY ALL
),
recent AS (
    -- Earliest listing in the trailing window [t - {TRAILING_WINDOW_S} s, t].
    SELECT e.event_id, e.published_horizon_bucket_s,
           arg_min(o.predicted_arrival, o.snapshot_index) AS window_start_estimate,
           min(o.collected_at) AS trailing_window_start_collected_at
    FROM eta_model_examples e
    JOIN _model_obs o
      ON o.event_id = e.event_id AND o.snapshot_index <= e.snapshot_index
     AND o.collected_at >= e.prediction_collected_at - INTERVAL {TRAILING_WINDOW_S} SECOND
    GROUP BY ALL
),
listed AS (
    -- The first stop position the trip lists in the prediction snapshot.
    SELECT e.event_id, e.published_horizon_bucket_s, min(sp.stop_position) AS first_listed
    FROM eta_model_examples e
    JOIN observed_arrival_proxy p USING (event_id)
    JOIN rt_trip_updates r
      ON r.feed_timestamp = e.prediction_feed_timestamp AND r.trip_id = p.trip_id
    JOIN static_stop_positions sp ON sp.trip_id = r.trip_id AND sp.stop_id = r.stop_id
    GROUP BY ALL
),
gaps AS (
    SELECT e.event_id, e.published_horizon_bucket_s,
           max(t.gap_before_s) FILTER (WHERE t.snapshot_index = e.snapshot_index)
               AS snapshot_gap_before_s,
           max(t.gap_before_s) AS max_snapshot_gap_last_15min_s
    FROM eta_model_examples e
    JOIN proxy_snapshot_timeline t
      ON t.snapshot_index <= e.snapshot_index
     AND t.collected_at > e.prediction_collected_at - INTERVAL {GAP_LOOKBACK_S} SECOND
    GROUP BY ALL
),
day_type AS (
    SELECT tr.trip_id,
           CASE WHEN c.service_id IS NULL THEN 'calendar_dates_only'
                WHEN (c.monday OR c.tuesday OR c.wednesday OR c.thursday OR c.friday)
                     AND NOT (c.saturday OR c.sunday) THEN 'weekday'
                WHEN c.saturday AND NOT c.sunday
                     AND NOT (c.monday OR c.tuesday OR c.wednesday OR c.thursday OR c.friday)
                    THEN 'saturday'
                WHEN c.sunday AND NOT c.saturday
                     AND NOT (c.monday OR c.tuesday OR c.wednesday OR c.thursday OR c.friday)
                    THEN 'sunday'
                ELSE 'mixed' END AS service_day_type
    FROM static_trips tr
    LEFT JOIN static_calendar c USING (service_id)
)
SELECT e.event_id, e.published_horizon_bucket_s,
       e.prediction_collected_at, e.prediction_feed_timestamp,
       e.published_horizon_s,
       CAST(epoch(e.published_estimate) - epoch(p.scheduled_arrival) AS INTEGER)
           AS published_minus_scheduled_s,
       p.route_short_name, p.stop_id, p.stop_position,
       p.stop_position - l.first_listed AS stops_away,
       CAST(hour(timezone('{GTFS_TIMEZONE}', e.prediction_collected_at)) AS INTEGER)
           AS hour_local,
       coalesce(d.service_day_type, 'unknown') AS service_day_type,
       CAST(epoch(e.prediction_collected_at) - epoch(h.history_first_collected_at) AS INTEGER)
           AS seconds_since_first_seen,
       CAST(e.snapshot_index - h.first_snapshot_index + 1 - h.observations_so_far AS INTEGER)
           AS missing_snapshots_so_far,
       -- 0 when the snapshot is the first listing (no earlier ETA to compare).
       coalesce(cur.change_s, 0) AS eta_change_last_snapshot_s,
       CAST(epoch(e.published_estimate) - epoch(tw.window_start_estimate) AS INTEGER)
           AS eta_change_last_5min_s,
       CAST(epoch(e.published_estimate) - epoch(h.first_estimate) AS INTEGER)
           AS eta_change_since_first_seen_s,
       CAST(h.prior_change_count AS INTEGER) AS prior_change_count,
       CAST(h.prior_abs_change_sum_s AS INTEGER) AS prior_abs_change_sum_s,
       CAST(g.snapshot_gap_before_s AS INTEGER) AS snapshot_gap_before_s,
       CAST(g.max_snapshot_gap_last_15min_s AS INTEGER) AS max_snapshot_gap_last_15min_s,
       CAST(a.has_applicable_visible_alert AS VARCHAR) AS has_applicable_visible_alert,
       a.alert_context_group,
       -- Audit columns, never features.
       h.observations_so_far, h.history_first_collected_at, h.history_last_collected_at,
       tw.trailing_window_start_collected_at, a.alert_snapshot_feed_timestamp
FROM eta_model_examples e
JOIN observed_arrival_proxy p USING (event_id)
JOIN hist h USING (event_id, published_horizon_bucket_s)
JOIN recent tw USING (event_id, published_horizon_bucket_s)
JOIN _model_obs cur
  ON cur.event_id = e.event_id AND cur.snapshot_index = e.snapshot_index
LEFT JOIN listed l USING (event_id, published_horizon_bucket_s)
LEFT JOIN gaps g USING (event_id, published_horizon_bucket_s)
LEFT JOIN day_type d ON d.trip_id = p.trip_id
LEFT JOIN eta_model_alert_context a USING (event_id, published_horizon_bucket_s)
ORDER BY e.event_id, e.published_horizon_bucket_s
"""


def _checks_sql(s: HorizonSettings) -> str:
    # A table, not a view: some checks read temporary tables dropped after the build.
    return f"""
    CREATE TABLE eta_model_feature_checks AS
    SELECT 'one_feature_row_per_example' AS check_name,
           abs((SELECT count(*) FROM eta_model_features)
               - (SELECT count(*) FROM eta_model_examples)) AS failures
    UNION ALL SELECT 'example_key_unique',
           (SELECT count(*) - count(DISTINCT (event_id, published_horizon_bucket_s))
              FROM eta_model_examples)
    UNION ALL SELECT 'history_ends_at_prediction_snapshot',
           (SELECT count(*) FROM eta_model_features
             WHERE history_last_collected_at IS DISTINCT FROM prediction_collected_at)
    UNION ALL SELECT 'trailing_window_within_bounds',
           (SELECT count(*) FROM eta_model_features
             WHERE trailing_window_start_collected_at
                       < prediction_collected_at - INTERVAL {TRAILING_WINDOW_S} SECOND
                OR trailing_window_start_collected_at > prediction_collected_at
                OR trailing_window_start_collected_at IS NULL)
    UNION ALL SELECT 'no_future_alert_snapshot',
           (SELECT count(*) FROM eta_model_features
             WHERE alert_snapshot_feed_timestamp > prediction_feed_timestamp)
    UNION ALL SELECT 'alert_context_one_row_per_example',
           abs((SELECT count(*) FROM eta_model_alert_context)
               - (SELECT count(*) FROM eta_model_examples))
    UNION ALL SELECT 'history_matches_observation_count',
           (SELECT count(*) FROM observed_arrival_proxy_eligible p
              LEFT JOIN (SELECT event_id, count(*) AS n FROM _model_obs GROUP BY 1) o
                USING (event_id)
             WHERE o.n IS DISTINCT FROM p.observation_count)
    UNION ALL SELECT 'prediction_not_in_final_window',
           (SELECT count(*) FROM eta_model_examples e
              JOIN _model_obs o
                ON o.event_id = e.event_id AND o.snapshot_index = e.snapshot_index
             WHERE o.rank_from_end <= {s.stability_window})
    UNION ALL SELECT 'published_horizon_within_tolerance',
           (SELECT count(*) FROM eta_model_examples
             WHERE abs(published_horizon_s - published_horizon_bucket_s) > {s.tolerance_s})
    UNION ALL SELECT 'published_horizon_matches_estimate',
           (SELECT count(*) FROM eta_model_examples
             WHERE published_horizon_s
                   <> epoch(published_estimate) - epoch(prediction_collected_at))
    UNION ALL SELECT 'examples_only_for_eligible_events',
           (SELECT count(*) FROM eta_model_examples e
              JOIN observed_arrival_proxy p USING (event_id) WHERE NOT p.is_eligible)
    UNION ALL SELECT 'label_confirmed_after_prediction',
           (SELECT count(*) FROM eta_model_examples
             WHERE label_known_at <= prediction_collected_at)
    """


def feature_report(con: duckdb.DuckDBPyConnection, settings: HorizonSettings) -> dict:
    def pairs(sql):
        return {str(k): v for k, v in con.execute(sql).fetchall()}

    return {
        "horizon_targets_s": list(settings.targets_s),
        "horizon_tolerance_s": settings.tolerance_s,
        "stability_window": settings.stability_window,
        "eligible_events": con.execute(
            "SELECT count(*) FROM observed_arrival_proxy_eligible"
        ).fetchone()[0],
        "examples": con.execute("SELECT count(*) FROM eta_model_examples").fetchone()[0],
        "examples_by_bucket": pairs(
            "SELECT published_horizon_bucket_s, count(*) FROM eta_model_examples "
            "GROUP BY 1 ORDER BY 1"
        ),
        "missing_by_reason": pairs(
            "SELECT missing_reason, count(*) FROM eta_model_example_coverage "
            "WHERE missing_reason IS NOT NULL GROUP BY 1 ORDER BY 1"
        ),
        "checks": pairs("SELECT check_name, failures FROM eta_model_feature_checks"),
    }
