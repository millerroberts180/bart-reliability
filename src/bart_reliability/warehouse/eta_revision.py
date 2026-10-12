"""ETA revision dataset: how BART's published arrival estimates change as a train approaches.

For each trip-stop, the reference endpoint is `observed_arrival_proxy`: BART's own final
stable published estimate before the stop disappears while the same trip stays visible
with downstream stops. It is NOT an observed arrival. BART publishes no independent
vehicle-position or actual-arrival feed, so the reference comes from the same system
being studied. Values measured against it are ETA revisions, not arrival-accuracy
errors. See docs/observed_arrival_proxy.md.
"""

from __future__ import annotations

import duckdb

from bart_reliability.warehouse.eta_revision_config import ETARevisionConfig

PROXY_METHOD = "last_stable_estimate_before_downstream_progression"

# Lines excluded from the proxy regardless of matching (PROJECT_SPEC.md):
# Antioch extension stations and the Oakland Airport Connector.
EXCLUDED_STOP_PREFIXES = ("E20", "E30", "H10", "H40")
EXCLUDED_ROUTE_IDS = ("19", "20")
CANCELLED_TRIP_VALUES = ("CANCELED", "DELETED")
SKIPPED_STOP_VALUES = ("SKIPPED", "NO_DATA")

TABLES = [
    "proxy_snapshot_timeline",
    "static_stop_positions",
    "observed_arrival_proxy",
    "eta_revision_examples",
    "eta_revision_config",
]
VIEWS = ["observed_arrival_proxy_eligible", "eta_revision_history", "eta_revision_quality_checks"]
_TEMP = ["_arrival_obs", "_trip_snapshots", "_events", "_events_pre"]


def _sql_list(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def build_eta_revision_dataset(
    con: duckdb.DuckDBPyConnection, config: ETARevisionConfig | None = None
) -> None:
    """Create the proxy, revision examples, and views. Rebuilt from scratch with the warehouse."""
    config = config or ETARevisionConfig()
    for statement in _statements(config):
        con.execute(statement)
    con.execute(
        "CREATE TABLE eta_revision_config AS SELECT * FROM (VALUES "
        + ", ".join(f"('{k}', '{v}')" for k, v in config.as_dict().items())
        + ") AS t(parameter, value)"
    )
    for name in _TEMP:
        con.execute(f"DROP TABLE IF EXISTS {name}")


def drop_eta_revision_dataset(con: duckdb.DuckDBPyConnection) -> None:
    """Remove everything build_eta_revision_dataset creates (used by sensitivity runs)."""
    for name in VIEWS:
        con.execute(f"DROP VIEW IF EXISTS {name}")
    for name in [*TABLES, *_TEMP]:
        con.execute(f"DROP TABLE IF EXISTS {name}")


def _statements(cfg: ETARevisionConfig) -> list[str]:
    excluded_stops = " OR ".join(f"stop_id LIKE '{p}%'" for p in EXCLUDED_STOP_PREFIXES)
    lo, hi = cfg.tier_a_persistence_s
    targets = ", ".join(str(t) for t in cfg.horizon_targets_s)
    window = cfg.stability_window
    origin_rule = "WHEN stop_position = 1 THEN 'trip_origin'" if cfg.exclude_origin_stops else ""
    return [
        # Every feed snapshot in order (empty feeds included), with the gap since the
        # previous one.
        """
        CREATE TABLE proxy_snapshot_timeline AS
        SELECT feed_timestamp, collected_at,
               row_number() OVER (ORDER BY collected_at, feed_timestamp) AS snapshot_index,
               epoch(collected_at)
                 - lag(epoch(collected_at)) OVER (ORDER BY collected_at, feed_timestamp)
                 AS gap_before_s
        FROM rt_feed_snapshots
        """,
        # Position of each stop within its trip. stop_sequence has gaps (0, 2, 3, ...),
        # so progression is judged by position, not by sequence number.
        """
        CREATE TABLE static_stop_positions AS
        SELECT trip_id, stop_sequence, stop_id,
               CAST(row_number() OVER (PARTITION BY trip_id ORDER BY stop_sequence) AS INTEGER)
                   AS stop_position,
               CAST(count(*) OVER (PARTITION BY trip_id) AS INTEGER) AS trip_stop_count
        FROM static_stop_times
        """,
        # One row per real-time prediction, keyed to a candidate event.
        """
        CREATE TEMP TABLE _arrival_obs AS
        SELECT coalesce(e.service_date, e.inferred_service_date) AS event_service_date,
               e.trip_id, e.stop_id, e.scheduled_stop_sequence AS stop_sequence,
               p.stop_position, p.trip_stop_count,
               e.route_id, e.route_short_name, e.direction_id, e.match_status,
               e.is_ambiguous_match, e.include_in_primary_metrics,
               e.trip_schedule_relationship, e.stop_schedule_relationship,
               e.predicted_arrival, e.scheduled_arrival, e.collected_at, e.feed_timestamp,
               s.snapshot_index
        FROM rt_predictions_enriched e
        JOIN proxy_snapshot_timeline s ON s.feed_timestamp = e.feed_timestamp
        LEFT JOIN static_stop_positions p
          ON p.trip_id = e.trip_id AND p.stop_sequence = e.scheduled_stop_sequence
        """,
        # Which stops each trip lists in each snapshot (matched rows only).
        """
        CREATE TEMP TABLE _trip_snapshots AS
        SELECT event_service_date, trip_id, snapshot_index,
               min(stop_position) AS min_stop_position
        FROM _arrival_obs
        GROUP BY ALL
        """,
        f"""
        CREATE TEMP TABLE _events AS
        SELECT event_service_date, trip_id, stop_id, stop_sequence,
               any_value(stop_position) AS stop_position,
               any_value(trip_stop_count) AS trip_stop_count,
               any_value(route_id) AS route_id,
               any_value(route_short_name) AS route_short_name,
               any_value(direction_id) AS direction_id,
               any_value(scheduled_arrival) AS scheduled_arrival,
               min(match_status) AS match_status,
               bool_or(is_ambiguous_match) AS ambiguous,
               bool_and(include_in_primary_metrics) AS primary_metrics,
               bool_or(trip_schedule_relationship = 'ADDED') AS added_trip,
               bool_or(trip_schedule_relationship IN ({_sql_list(CANCELLED_TRIP_VALUES)}))
                   AS cancelled_trip,
               bool_or(stop_schedule_relationship IN ({_sql_list(SKIPPED_STOP_VALUES)}))
                   AS skipped_stop,
               count(*) AS observation_count,
               min(snapshot_index) AS first_index,
               max(snapshot_index) AS last_index,
               min(collected_at) AS first_seen_at,
               max(collected_at) AS last_seen_at,
               arg_max(predicted_arrival, snapshot_index) AS last_estimate_arrival,
               list(predicted_arrival ORDER BY snapshot_index DESC)[1:{window}]
                   AS final_estimates
        FROM _arrival_obs
        GROUP BY event_service_date, trip_id, stop_id, stop_sequence
        """,
        f"""
        CREATE TEMP TABLE _events_pre AS
        WITH spans AS (
            SELECT ev.*,
                   nx.collected_at AS confirmed_absent_at,
                   nx.feed_timestamp AS confirmed_absent_feed_timestamp,
                   ts.min_stop_position AS next_snapshot_min_stop_position,
                   (SELECT max(s.gap_before_s) FROM proxy_snapshot_timeline s
                     WHERE s.snapshot_index > ev.first_index
                       AND s.snapshot_index <= ev.last_index + 1) AS max_collection_gap_s,
                   (SELECT count(*) FROM _trip_snapshots t
                     WHERE t.event_service_date = ev.event_service_date
                       AND t.trip_id = ev.trip_id
                       AND t.snapshot_index BETWEEN ev.first_index AND ev.last_index)
                       AS trip_visible_snapshots,
                   CAST(epoch(list_max(ev.final_estimates)) - epoch(list_min(ev.final_estimates))
                        AS INTEGER) AS final_estimate_spread_s
            FROM _events ev
            LEFT JOIN proxy_snapshot_timeline nx ON nx.snapshot_index = ev.last_index + 1
            LEFT JOIN _trip_snapshots ts
              ON ts.event_service_date = ev.event_service_date AND ts.trip_id = ev.trip_id
             AND ts.snapshot_index = ev.last_index + 1
        )
        SELECT *,
               last_index - first_index + 1 AS snapshots_in_span,
               trip_visible_snapshots - observation_count AS stop_missing_snapshots,
               last_index - first_index + 1 - trip_visible_snapshots AS trip_missing_snapshots,
               CASE
                   WHEN {excluded_stops}
                        OR route_id IN ({_sql_list(EXCLUDED_ROUTE_IDS)}) THEN 'excluded_line'
                   WHEN added_trip THEN 'added_trip'
                   WHEN cancelled_trip THEN 'cancelled_trip'
                   WHEN skipped_stop THEN 'skipped_or_no_data_stop'
                   WHEN match_status <> 'matched' THEN 'unmatched_' || match_status
                   WHEN ambiguous THEN 'ambiguous_repeated_stop'
                   WHEN NOT primary_metrics THEN 'not_primary_metrics'
                   {origin_rule}
                   WHEN observation_count < {window} THEN 'insufficient_observations'
                   WHEN confirmed_absent_at IS NULL THEN 'no_confirming_snapshot'
                   WHEN max_collection_gap_s > {cfg.max_collection_gap_s} THEN 'collection_gap'
                   WHEN next_snapshot_min_stop_position IS NULL THEN 'trip_left_feed'
                   WHEN next_snapshot_min_stop_position <= stop_position
                       THEN 'no_downstream_progression'
                   WHEN final_estimate_spread_s > {cfg.stable_spread_s}
                       THEN 'unstable_final_estimate'
               END AS pre_exclusion_reason
        FROM spans
        """,
        # Revision examples: for each eligible event and target, the published estimate
        # whose time to the final stable estimate is closest to the target, within
        # tolerance. The final estimates that define the endpoint are never used. Ties go
        # to the earlier snapshot.
        f"""
        CREATE TABLE eta_revision_examples AS
        WITH candidates AS (
            SELECT ev.event_service_date, ev.trip_id, ev.stop_id, ev.stop_sequence,
                   ev.last_estimate_arrival AS proxy_arrival,
                   o.collected_at, o.feed_timestamp, o.snapshot_index, o.predicted_arrival,
                   row_number() OVER (
                       PARTITION BY ev.event_service_date, ev.trip_id, ev.stop_id,
                                    ev.stop_sequence
                       ORDER BY o.snapshot_index DESC) AS rank_from_end
            FROM _events_pre ev
            JOIN _arrival_obs o
              ON o.event_service_date = ev.event_service_date AND o.trip_id = ev.trip_id
             AND o.stop_id = ev.stop_id AND o.stop_sequence = ev.stop_sequence
            WHERE ev.pre_exclusion_reason IS NULL
        ),
        scored AS (
            SELECT c.*, t.target_horizon_s,
                   CAST(epoch(c.proxy_arrival) - epoch(c.collected_at) AS INTEGER)
                       AS time_to_proxy_s
            FROM candidates c, (SELECT unnest([{targets}]) AS target_horizon_s) t
            WHERE c.rank_from_end > {window}
        )
        SELECT event_service_date || ':' || trip_id || ':' || stop_sequence AS event_id,
               target_horizon_s, collected_at AS prediction_collected_at,
               feed_timestamp AS prediction_feed_timestamp, snapshot_index,
               rank_from_end AS observation_rank_from_end,
               predicted_arrival AS published_estimate, proxy_arrival AS final_stable_estimate,
               time_to_proxy_s,
               CAST(epoch(predicted_arrival) - epoch(collected_at) AS INTEGER)
                   AS published_horizon_s,
               -- Positive: the ETA later moved later (the final stable estimate is later
               -- than this one). Negative: it later moved earlier.
               CAST(epoch(proxy_arrival) - epoch(predicted_arrival) AS INTEGER)
                   AS eta_revision_seconds,
               CAST(abs(epoch(proxy_arrival) - epoch(predicted_arrival)) AS INTEGER)
                   AS absolute_eta_revision_seconds,
               CASE WHEN proxy_arrival > predicted_arrival THEN 'revised_later'
                    WHEN proxy_arrival < predicted_arrival THEN 'revised_earlier'
                    ELSE 'unchanged' END AS revision_direction
        FROM scored
        WHERE abs(time_to_proxy_s - target_horizon_s) <= {cfg.horizon_tolerance_s}
        QUALIFY row_number() OVER (
            PARTITION BY event_service_date, trip_id, stop_id, stop_sequence, target_horizon_s
            ORDER BY abs(time_to_proxy_s - target_horizon_s), collected_at, feed_timestamp
        ) = 1
        ORDER BY event_id, target_horizon_s
        """,
        f"""
        CREATE TABLE observed_arrival_proxy AS
        WITH horizons AS (
            SELECT event_id, list(target_horizon_s ORDER BY target_horizon_s) AS targets
            FROM eta_revision_examples GROUP BY 1
        ),
        final AS (
            SELECT ev.*, h.targets,
                   event_service_date || ':' || trip_id || ':' || coalesce(
                       CAST(stop_sequence AS VARCHAR), stop_id) AS event_id_,
                   coalesce(pre_exclusion_reason,
                            CASE WHEN h.targets IS NULL THEN 'no_horizon_history' END)
                       AS exclusion_reason
            FROM _events_pre ev
            LEFT JOIN horizons h
              ON h.event_id = ev.event_service_date || ':' || ev.trip_id || ':'
                              || ev.stop_sequence
        )
        SELECT event_id_ AS event_id,
               event_service_date AS service_date, trip_id, route_id, route_short_name,
               direction_id, stop_id, stop_sequence, stop_position, trip_stop_count,
               scheduled_arrival, first_seen_at, last_seen_at,
               confirmed_absent_at, confirmed_absent_feed_timestamp,
               next_snapshot_min_stop_position,
               last_estimate_arrival, final_estimates, final_estimate_spread_s,
               observation_count, snapshots_in_span, stop_missing_snapshots,
               trip_missing_snapshots, CAST(max_collection_gap_s AS INTEGER)
                   AS max_collection_gap_s,
               exclusion_reason IS NULL AS is_eligible,
               exclusion_reason,
               CASE WHEN exclusion_reason IS NULL THEN last_estimate_arrival END
                   AS proxy_arrival,
               '{PROXY_METHOD}' AS proxy_method,
               CASE WHEN exclusion_reason IS NOT NULL THEN NULL
                    WHEN final_estimate_spread_s <= {cfg.tier_a_spread_s}
                         AND stop_missing_snapshots = 0 AND trip_missing_snapshots = 0
                         AND epoch(last_seen_at) - epoch(last_estimate_arrival)
                             BETWEEN {lo} AND {hi}
                        THEN 'A'
                    ELSE 'B' END AS quality_tier,
               CAST(epoch(last_seen_at) - epoch(last_estimate_arrival) AS INTEGER)
                   AS listed_after_estimate_s,
               CAST(epoch(confirmed_absent_at) - epoch(last_estimate_arrival) AS INTEGER)
                   AS confirmed_absent_after_estimate_s,
               CAST(epoch(confirmed_absent_at) - epoch(last_seen_at) AS INTEGER)
                   AS disappearance_window_s,
               -- Heuristic, not a confidence interval: the proxy is known no better than
               -- the final estimates agree, than the gap in which the stop disappeared,
               -- or than the conflict between the estimate and when the stop was last
               -- listed (an estimate can freeze while the stop stays listed for minutes).
               greatest(final_estimate_spread_s,
                        CAST(epoch(confirmed_absent_at) - epoch(last_seen_at) AS INTEGER),
                        CAST(abs(epoch(last_seen_at) - epoch(last_estimate_arrival)) AS INTEGER))
                   AS uncertainty_s,
               coalesce(targets, []) AS horizons_available
        FROM final
        ORDER BY service_date, trip_id, stop_position NULLS LAST, stop_id
        """,
        """
        CREATE VIEW observed_arrival_proxy_eligible AS
        SELECT * FROM observed_arrival_proxy WHERE is_eligible
        """,
        # Every published estimate of each eligible event, read from the Parquet views.
        """
        CREATE VIEW eta_revision_history AS
        SELECT p.event_id, p.service_date, p.trip_id, p.stop_id, p.stop_sequence,
               p.quality_tier, e.collected_at, e.feed_timestamp,
               e.predicted_arrival AS published_estimate,
               p.proxy_arrival AS final_stable_estimate,
               CAST(epoch(p.proxy_arrival) - epoch(e.collected_at) AS INTEGER)
                   AS time_to_proxy_s,
               CAST(epoch(p.proxy_arrival) - epoch(e.predicted_arrival) AS INTEGER)
                   AS eta_revision_seconds
        FROM observed_arrival_proxy p
        JOIN rt_predictions_enriched e
          ON e.trip_id = p.trip_id AND e.service_date = p.service_date
         AND e.scheduled_stop_sequence = p.stop_sequence AND e.stop_id = p.stop_id
        WHERE p.is_eligible
        """,
        f"""
        CREATE VIEW eta_revision_quality_checks AS
        SELECT 'event_id_unique' AS check_name,
               (SELECT count(*) - count(DISTINCT event_id) FROM observed_arrival_proxy)
                   AS failures
        UNION ALL SELECT 'eligible_iff_proxy_and_no_reason',
               (SELECT count(*) FROM observed_arrival_proxy
                 WHERE is_eligible <> (proxy_arrival IS NOT NULL)
                    OR is_eligible = (exclusion_reason IS NOT NULL))
        UNION ALL SELECT 'eligible_confirmed_downstream_progression',
               (SELECT count(*) FROM observed_arrival_proxy_eligible
                 WHERE confirmed_absent_at <= last_seen_at
                    OR next_snapshot_min_stop_position <= stop_position)
        UNION ALL SELECT 'eligible_no_collection_gap',
               (SELECT count(*) FROM observed_arrival_proxy_eligible
                 WHERE max_collection_gap_s > {cfg.max_collection_gap_s})
        UNION ALL SELECT 'eligible_stable_final_estimate',
               (SELECT count(*) FROM observed_arrival_proxy_eligible
                 WHERE final_estimate_spread_s > {cfg.stable_spread_s}
                    OR len(final_estimates) < {window}
                    OR proxy_arrival <> final_estimates[1])
        UNION ALL SELECT 'eligible_has_horizon',
               (SELECT count(*) FROM observed_arrival_proxy_eligible
                 WHERE len(horizons_available) = 0)
        UNION ALL SELECT 'horizon_unique_per_event_target',
               (SELECT count(*) - count(DISTINCT (event_id, target_horizon_s))
                  FROM eta_revision_examples)
        UNION ALL SELECT 'horizon_within_tolerance',
               (SELECT count(*) FROM eta_revision_examples
                 WHERE abs(time_to_proxy_s - target_horizon_s) > {cfg.horizon_tolerance_s})
        UNION ALL SELECT 'horizon_not_from_final_estimates',
               (SELECT count(*) FROM eta_revision_examples h
                  JOIN observed_arrival_proxy p USING (event_id)
                 WHERE h.observation_rank_from_end <= {window}
                    OR h.prediction_collected_at >= p.last_seen_at)
        UNION ALL SELECT 'horizon_only_for_eligible_events',
               (SELECT count(*) FROM eta_revision_examples h
                  JOIN observed_arrival_proxy p USING (event_id) WHERE NOT p.is_eligible)
        UNION ALL SELECT 'excluded_populations_never_eligible',
               (SELECT count(*) FROM observed_arrival_proxy_eligible
                 WHERE {excluded_stops}
                    OR route_id IN ({_sql_list(EXCLUDED_ROUTE_IDS)}))
        """,
    ]


def eta_revision_report(con: duckdb.DuckDBPyConnection, example_limit: int = 5) -> dict:
    """Counts and distributions for the validation report and the build log."""

    def one(sql):
        cursor = con.execute(sql)
        names = [d[0] for d in cursor.description]
        return dict(zip(names, cursor.fetchone(), strict=True))

    def rows(sql):
        return con.execute(sql).fetchall()

    counts = one(
        """
        SELECT count(*) AS candidate_events,
               count(*) FILTER (WHERE is_eligible) AS eligible_events,
               count(*) FILTER (WHERE quality_tier = 'A') AS tier_a,
               count(*) FILTER (WHERE quality_tier = 'B') AS tier_b
        FROM observed_arrival_proxy
        """
    )
    counts["exclusions"] = dict(
        rows(
            "SELECT exclusion_reason, count(*) FROM observed_arrival_proxy "
            "WHERE NOT is_eligible GROUP BY 1 ORDER BY 2 DESC"
        )
    )
    counts["horizon_coverage"] = {
        target: {"examples": n, "pct_of_eligible": pct}
        for target, n, pct in rows(
            """
            SELECT target_horizon_s, count(*),
                   round(100 * count(*) / nullif((SELECT count(*)
                       FROM observed_arrival_proxy_eligible), 0), 2)
            FROM eta_revision_examples GROUP BY 1 ORDER BY 1
            """
        )
    }
    for tier_filter, key in (
        ("p.quality_tier = 'A'", "eta_revision_by_horizon_tier_a"),
        ("p.is_eligible", "eta_revision_by_horizon_all_eligible"),
    ):
        counts[key] = {
            target: {
                "n": n,
                "mean_eta_revision_s": mean,
                "mean_absolute_eta_revision_s": mean_abs,
                "median_absolute_eta_revision_s": median_abs,
                "p90_absolute_eta_revision_s": p90,
                "pct_within_60s": within,
                "pct_revised_later": later,
            }
            for target, n, mean, mean_abs, median_abs, p90, within, later in rows(
                f"""
                SELECT target_horizon_s, count(*), round(avg(eta_revision_seconds), 1),
                       round(avg(absolute_eta_revision_seconds), 1),
                       quantile_cont(absolute_eta_revision_seconds, 0.5),
                       quantile_cont(absolute_eta_revision_seconds, 0.9),
                       round(100 * avg((absolute_eta_revision_seconds <= 60)::INT), 1),
                       round(100 * avg((revision_direction = 'revised_later')::INT), 1)
                FROM eta_revision_examples h
                JOIN observed_arrival_proxy p USING (event_id)
                WHERE {tier_filter}
                GROUP BY 1 ORDER BY 1
                """
            )
        }
    counts["final_estimate_spread_s"] = one(
        """
        SELECT quantile_cont(final_estimate_spread_s, [0.5, 0.9, 0.99]) AS p50_p90_p99,
               max(final_estimate_spread_s) AS max,
               round(100 * avg((final_estimate_spread_s = 0)::INT), 1) AS pct_zero
        FROM observed_arrival_proxy
        WHERE exclusion_reason IS NULL OR exclusion_reason = 'unstable_final_estimate'
        """
    )
    counts["listed_after_estimate_s"] = one(
        """
        SELECT quantile_cont(listed_after_estimate_s, [0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
                   AS p5_p25_p50_p75_p95_p99,
               min(listed_after_estimate_s) AS min, max(listed_after_estimate_s) AS max,
               quantile_cont(confirmed_absent_after_estimate_s, [0.5, 0.95])
                   AS confirmed_absent_after_p50_p95
        FROM observed_arrival_proxy_eligible
        """
    )
    counts["questionable_examples"] = [
        dict(
            zip(
                [
                    "event_id",
                    "route",
                    "stop_id",
                    "tier",
                    "listed_after_estimate_s",
                    "final_estimate_spread_s",
                    "stop_missing_snapshots",
                ],
                r,
                strict=True,
            )
        )
        for r in rows(
            f"""
            SELECT event_id, route_short_name, stop_id, quality_tier,
                   listed_after_estimate_s, final_estimate_spread_s, stop_missing_snapshots
            FROM observed_arrival_proxy_eligible
            WHERE quality_tier = 'B'
            ORDER BY abs(listed_after_estimate_s) DESC, event_id
            LIMIT {example_limit}
            """
        )
    ]
    counts["quality_checks"] = dict(rows("SELECT * FROM eta_revision_quality_checks"))
    return counts
