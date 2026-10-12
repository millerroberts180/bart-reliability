"""Service alerts in the warehouse: visibility, scope, and point-in-time alert context.

Vocabulary (kept separate on purpose):

- **visible**: the alert appeared in the most recent non-stale alert snapshot available at
  the prediction's publication time T (latest snapshot with feed timestamp <= T, at most
  ALERT_SNAPSHOT_MAX_AGE_S old). Nothing published after T is used.
- **applicable visible alert**: a visible alert whose structured informed entities apply
  to the prediction's agency, route, trip, and stop.
- **structured active period**: whether BART supplied one, and whether T falls inside it
  (start <= T <= end, missing bounds open). NULL when no period was supplied.
- **operational disruption active**: TRUE or FALSE only when supported by a structured
  active period; otherwise NULL (unknown). Being visible is not evidence of a disruption.
- **alert category** (planned notice / incident-like / unclassified): from a
  version-controlled **manual** annotation file, not an automated classifier.

These describe what riders could see, not what caused any ETA revision.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pyarrow as pa

from bart_reliability.transform.alerts import (
    ENTITIES_DIR,
    ENTITY_SCHEMA,
    OBSERVATION_DIR,
    OBSERVATION_SCHEMA,
    PERIOD_SCHEMA,
    PERIODS_DIR,
    SNAPSHOT_DIR,
    SNAPSHOT_SCHEMA,
    VERSION_SCHEMA,
    VERSIONS_DIR,
)

# Alert snapshots are polled every 60 s; an older one is too stale to describe time T.
ALERT_SNAPSHOT_MAX_AGE_S = 120

DEFAULT_ANNOTATIONS_PATH = Path("config/alert_annotations.csv")
ALERT_CATEGORIES = ("planned_notice", "incident_like")


class AlertAnnotationError(ValueError):
    """Raised when the manual alert-annotation file is malformed."""


ANNOTATION_COLUMNS = ["entity_id", "alert_fingerprint", "category", "basis", "reviewed_on"]

# Most specific first. An informed entity's scope is its most specific populated field.
SCOPES = ["stop", "trip", "route", "route_type", "system_wide"]


def _duck_type(t: pa.DataType) -> str:
    if pa.types.is_timestamp(t):
        return "TIMESTAMPTZ"
    if pa.types.is_int32(t):
        return "INTEGER"
    if pa.types.is_list(t):
        return "STRUCT(language VARCHAR, text VARCHAR)[]"
    return "VARCHAR"


def _source(path_glob: Path, schema: pa.Schema, hive: bool) -> str:
    root = path_glob.parent if not hive else path_glob
    files = (
        list(root.glob("date=*/hour=*/*.parquet"))
        if hive
        else ([path_glob] if path_glob.is_file() else [])
    )
    if files:
        glob = (root / "**" / "*.parquet").as_posix() if hive else path_glob.as_posix()
        glob = glob.replace("'", "''")
        if hive:
            return (
                f"SELECT * EXCLUDE (date, hour) FROM read_parquet('{glob}', "
                "hive_partitioning = true, hive_types = {'date': DATE, 'hour': INTEGER})"
            )
        return f"SELECT * FROM read_parquet('{glob}')"
    cols = ", ".join(f"CAST(NULL AS {_duck_type(f.type)}) AS {f.name}" for f in schema)
    return f"SELECT {cols} WHERE false"


def create_alert_views(con: duckdb.DuckDBPyConnection, processed_dir: Path) -> None:
    """Views over the alert Parquet (empty, correctly typed views if none exists yet)."""
    root = processed_dir.resolve()
    con.execute(
        "CREATE VIEW rt_alert_snapshots AS "
        + _source(root / SNAPSHOT_DIR, SNAPSHOT_SCHEMA, hive=True)
    )
    con.execute(
        "CREATE VIEW rt_alert_observations AS "
        + _source(root / OBSERVATION_DIR, OBSERVATION_SCHEMA, hive=True)
    )
    for view, directory, schema in [
        ("alert_versions", VERSIONS_DIR, VERSION_SCHEMA),
        ("alert_active_periods", PERIODS_DIR, PERIOD_SCHEMA),
        ("alert_informed_entities", ENTITIES_DIR, ENTITY_SCHEMA),
    ]:
        con.execute(
            f"CREATE VIEW {view} AS "
            + _source(root / directory / "part.parquet", schema, hive=False)
        )


def build_alert_tables(
    con: duckdb.DuckDBPyConnection, max_age_s: int = ALERT_SNAPSHOT_MAX_AGE_S
) -> None:
    for statement in _statements(max_age_s):
        con.execute(statement)


def _statements(max_age_s: int) -> list[str]:
    scope_rank = " ".join(f"WHEN '{s}' THEN {i + 1}" for i, s in enumerate(SCOPES))
    return [
        """
        CREATE TABLE alert_snapshot_timeline AS
        SELECT feed_timestamp, collected_at, source_file, alert_count,
               row_number() OVER (ORDER BY feed_timestamp, collected_at) AS alert_snapshot_index
        FROM rt_alert_snapshots
        """,
        # Contiguous runs of snapshots in which each alert version appeared.
        """
        CREATE TABLE alert_visibility AS
        WITH obs AS (
            SELECT o.entity_id, o.alert_fingerprint, t.alert_snapshot_index AS k,
                   t.feed_timestamp
            FROM rt_alert_observations o
            JOIN alert_snapshot_timeline t ON t.feed_timestamp = o.feed_timestamp
        ),
        runs AS (
            SELECT *, k - row_number() OVER (
                PARTITION BY entity_id, alert_fingerprint ORDER BY k) AS run_key
            FROM obs
        ),
        grouped AS (
            SELECT entity_id, alert_fingerprint, min(k) AS first_index, max(k) AS last_index,
                   min(feed_timestamp) AS visible_from, max(feed_timestamp) AS last_seen,
                   count(*) AS snapshot_count
            FROM runs GROUP BY entity_id, alert_fingerprint, run_key
        )
        SELECT g.*,
               nx.feed_timestamp AS visible_until,  -- first later snapshot without it
               nx.feed_timestamp IS NULL AS visible_at_end_of_data,
               row_number() OVER (PARTITION BY g.entity_id ORDER BY g.first_index)
                   AS interval_number
        FROM grouped g
        LEFT JOIN alert_snapshot_timeline nx ON nx.alert_snapshot_index = g.last_index + 1
        ORDER BY g.entity_id, g.first_index
        """,
        # One row per (entity_id, content version), numbered by first appearance.
        """
        CREATE VIEW alert_entity_versions AS
        SELECT entity_id, alert_fingerprint, min(visible_from) AS first_seen,
               max(last_seen) AS last_seen, sum(snapshot_count) AS snapshot_count,
               count(*) AS visibility_intervals,
               row_number() OVER (PARTITION BY entity_id ORDER BY min(visible_from))
                   AS version_number
        FROM alert_visibility GROUP BY entity_id, alert_fingerprint
        """,
        f"""
        CREATE VIEW alert_informed_entity_scope AS
        SELECT *, CASE scope {scope_rank} END AS scope_rank
        FROM (
            SELECT ie.*,
                   CASE WHEN stop_id IS NOT NULL THEN 'stop'
                        WHEN trip_id IS NOT NULL THEN 'trip'
                        WHEN route_id IS NOT NULL OR trip_route_id IS NOT NULL THEN 'route'
                        WHEN route_type IS NOT NULL THEN 'route_type'
                        WHEN agency_id IS NOT NULL THEN 'system_wide'
                        ELSE 'unspecified' END AS scope
            FROM alert_informed_entities ie
        )
        """,
        """
        CREATE VIEW alert_version_scope AS
        SELECT v.alert_fingerprint, v.cause, v.effect, v.header_text,
               list(DISTINCT s.scope ORDER BY s.scope) AS scopes,
               arg_min(s.scope, s.scope_rank) AS most_specific_scope,
               coalesce(bool_or(s.scope = 'system_wide'), false) AS is_system_wide
        FROM alert_versions v
        LEFT JOIN alert_informed_entity_scope s USING (alert_fingerprint)
        GROUP BY ALL
        """,
        # Point-in-time alert state for every revision example (one row each).
        f"""
        CREATE TEMP TABLE _example_alert_snapshot AS
        WITH ex AS (
            SELECT h.event_id, h.target_horizon_s, h.prediction_feed_timestamp,
                   p.trip_id, p.route_id, p.direction_id, p.stop_id, s.parent_station,
                   coalesce(r.agency_id, (SELECT min(agency_id) FROM static_agency))
                       AS agency_id,
                   r.route_type
            FROM eta_revision_examples h
            JOIN observed_arrival_proxy p USING (event_id)
            LEFT JOIN static_stops s ON s.stop_id = p.stop_id
            LEFT JOIN static_routes r ON r.route_id = p.route_id
        )
        SELECT ex.*, t.feed_timestamp AS alert_snapshot_feed_timestamp,
               CAST(epoch(ex.prediction_feed_timestamp) - epoch(t.feed_timestamp) AS INTEGER)
                   AS alert_snapshot_age_s,
               CASE WHEN t.feed_timestamp IS NULL THEN 'no_alert_snapshot'
                    WHEN epoch(ex.prediction_feed_timestamp) - epoch(t.feed_timestamp)
                         > {max_age_s} THEN 'alert_snapshot_stale'
                    ELSE 'observed' END AS alert_feed_status
        FROM ex
        ASOF LEFT JOIN alert_snapshot_timeline t
          ON ex.prediction_feed_timestamp >= t.feed_timestamp
        """,
        # One row per (example, applicable visible alert version). One-to-many by design.
        """
        CREATE TABLE eta_revision_example_alerts AS
        WITH visible AS (
            SELECT x.*, o.entity_id, o.alert_fingerprint
            FROM _example_alert_snapshot x
            JOIN rt_alert_observations o
              ON o.feed_timestamp = x.alert_snapshot_feed_timestamp
            WHERE x.alert_feed_status = 'observed'
        ),
        applicable AS (
            SELECT v.event_id, v.target_horizon_s, v.prediction_feed_timestamp,
                   v.alert_snapshot_feed_timestamp, v.entity_id, v.alert_fingerprint,
                   arg_min(ie.scope, ie.scope_rank) AS matched_scope
            FROM visible v
            JOIN alert_informed_entity_scope ie USING (alert_fingerprint)
            WHERE ie.scope <> 'unspecified'
              AND (ie.agency_id IS NULL OR ie.agency_id = v.agency_id)
              AND (ie.route_id IS NULL OR ie.route_id = v.route_id)
              AND (ie.trip_route_id IS NULL OR ie.trip_route_id = v.route_id)
              AND (ie.route_type IS NULL OR ie.route_type = v.route_type)
              AND (ie.direction_id IS NULL OR ie.direction_id = v.direction_id)
              AND (ie.trip_id IS NULL OR ie.trip_id = v.trip_id)
              AND (ie.stop_id IS NULL OR ie.stop_id IN (v.stop_id, v.parent_station))
            GROUP BY ALL
        ),
        periods AS (
            SELECT a.event_id, a.target_horizon_s, a.alert_fingerprint,
                   bool_or((ap.active_start IS NULL
                            OR ap.active_start <= a.prediction_feed_timestamp)
                           AND (ap.active_end IS NULL
                                OR a.prediction_feed_timestamp <= ap.active_end))
                       AS within_period
            FROM applicable a
            JOIN alert_active_periods ap USING (alert_fingerprint)
            GROUP BY ALL
        )
        SELECT a.*, ver.cause, ver.effect,
               ver.active_period_count > 0 AS has_structured_active_period,
               -- NULL when BART supplied no active period.
               CASE WHEN ver.active_period_count > 0 THEN p.within_period END
                   AS within_structured_active_period,
               -- Supported only by a structured period; otherwise unknown.
               CASE WHEN ver.active_period_count > 0 THEN p.within_period END
                   AS operational_disruption_active,
               coalesce(ann.category, 'unclassified') AS alert_category
        FROM applicable a
        JOIN alert_versions ver USING (alert_fingerprint)
        LEFT JOIN periods p USING (event_id, target_horizon_s, alert_fingerprint)
        LEFT JOIN alert_annotations ann USING (alert_fingerprint)
        ORDER BY a.event_id, a.target_horizon_s, a.entity_id
        """,
        # Exactly one row per eta_revision_examples row.
        """
        CREATE TABLE eta_revision_alert_context AS
        WITH agg AS (
            SELECT event_id, target_horizon_s,
                   count(*) AS applicable_visible_alert_count,
                   count(*) FILTER (WHERE alert_category = 'planned_notice')
                       AS applicable_visible_planned_count,
                   count(*) FILTER (WHERE alert_category = 'incident_like')
                       AS applicable_visible_incident_like_count,
                   count(*) FILTER (WHERE alert_category = 'unclassified')
                       AS applicable_visible_unclassified_count,
                   count(*) FILTER (WHERE has_structured_active_period)
                       AS with_structured_period_count,
                   count(*) FILTER (WHERE within_structured_active_period)
                       AS within_structured_period_count,
                   count(*) FILTER (WHERE within_structured_active_period = false)
                       AS outside_structured_period_count,
                   bool_or(operational_disruption_active) AS any_disruption_true,
                   bool_and(operational_disruption_active IS NOT NULL) AS all_disruption_known,
                   arg_min(matched_scope, CASE matched_scope WHEN 'stop' THEN 1
                       WHEN 'trip' THEN 2 WHEN 'route' THEN 3 WHEN 'route_type' THEN 4
                       ELSE 5 END) AS most_specific_visible_scope,
                   bool_or(matched_scope = 'system_wide') AS visible_system_wide,
                   bool_or(matched_scope IN ('route', 'route_type')) AS visible_route,
                   bool_or(matched_scope = 'trip') AS visible_trip,
                   bool_or(matched_scope = 'stop') AS visible_stop,
                   list(DISTINCT entity_id ORDER BY entity_id) AS applicable_visible_alert_ids,
                   list(DISTINCT cause ORDER BY cause) FILTER (WHERE cause IS NOT NULL)
                       AS visible_causes,
                   list(DISTINCT effect ORDER BY effect) FILTER (WHERE effect IS NOT NULL)
                       AS visible_effects
            FROM eta_revision_example_alerts GROUP BY 1, 2
        )
        SELECT x.event_id, x.target_horizon_s, x.prediction_feed_timestamp,
               x.alert_snapshot_feed_timestamp, x.alert_snapshot_age_s, x.alert_feed_status,
               x.alert_feed_status = 'observed' AS alert_state_known,
               CASE WHEN x.alert_feed_status = 'observed'
                    THEN coalesce(a.applicable_visible_alert_count, 0) END
                   AS applicable_visible_alert_count,
               -- NULL, not false, when alert state at publication is unknown.
               CASE WHEN x.alert_feed_status = 'observed'
                    THEN coalesce(a.applicable_visible_alert_count, 0) > 0 END
                   AS has_applicable_visible_alert,
               CASE WHEN x.alert_feed_status = 'observed'
                    THEN coalesce(a.applicable_visible_planned_count, 0) END
                   AS applicable_visible_planned_count,
               CASE WHEN x.alert_feed_status = 'observed'
                    THEN coalesce(a.applicable_visible_incident_like_count, 0) END
                   AS applicable_visible_incident_like_count,
               CASE WHEN x.alert_feed_status = 'observed'
                    THEN coalesce(a.applicable_visible_unclassified_count, 0) END
                   AS applicable_visible_unclassified_count,
               -- Reporting group; precedence: incident-like > unclassified > planned.
               CASE WHEN x.alert_feed_status <> 'observed' THEN 'unknown_alert_state'
                    WHEN coalesce(a.applicable_visible_alert_count, 0) = 0
                        THEN 'no_applicable_visible_alert'
                    WHEN a.applicable_visible_incident_like_count > 0
                        THEN 'applicable_visible_incident_like'
                    WHEN a.applicable_visible_unclassified_count > 0
                        THEN 'applicable_visible_unclassified'
                    ELSE 'applicable_visible_planned_notice' END AS alert_context_group,
               CASE WHEN x.alert_feed_status = 'observed'
                    THEN coalesce(a.with_structured_period_count, 0) END
                   AS with_structured_period_count,
               CASE WHEN x.alert_feed_status = 'observed'
                    THEN coalesce(a.within_structured_period_count, 0) END
                   AS within_structured_period_count,
               CASE WHEN x.alert_feed_status = 'observed'
                    THEN coalesce(a.outside_structured_period_count, 0) END
                   AS outside_structured_period_count,
               -- TRUE if any applicable visible alert's structured period covers T; FALSE
               -- only if every one has a structured period and none covers T; otherwise
               -- unknown. No visible alert is not evidence of no disruption.
               CASE WHEN a.any_disruption_true THEN true
                    WHEN a.all_disruption_known THEN false END
                   AS operational_disruption_active,
               a.most_specific_visible_scope,
               CASE WHEN x.alert_feed_status = 'observed'
                    THEN coalesce(a.visible_system_wide, false) END AS visible_system_wide,
               CASE WHEN x.alert_feed_status = 'observed'
                    THEN coalesce(a.visible_route, false) END AS visible_route,
               CASE WHEN x.alert_feed_status = 'observed'
                    THEN coalesce(a.visible_trip, false) END AS visible_trip,
               CASE WHEN x.alert_feed_status = 'observed'
                    THEN coalesce(a.visible_stop, false) END AS visible_stop,
               coalesce(a.applicable_visible_alert_ids, []) AS applicable_visible_alert_ids,
               coalesce(a.visible_causes, []) AS visible_causes,
               coalesce(a.visible_effects, []) AS visible_effects
        FROM _example_alert_snapshot x
        LEFT JOIN agg a USING (event_id, target_horizon_s)
        ORDER BY x.event_id, x.target_horizon_s
        """,
        "DROP TABLE _example_alert_snapshot",
        f"""
        CREATE VIEW alert_quality_checks AS
        SELECT 'context_one_row_per_example' AS check_name,
               abs((SELECT count(*) FROM eta_revision_alert_context)
                   - (SELECT count(*) FROM eta_revision_examples)) AS failures
        UNION ALL SELECT 'context_key_unique',
               (SELECT count(*) - count(DISTINCT (event_id, target_horizon_s))
                  FROM eta_revision_alert_context)
        UNION ALL SELECT 'no_future_alert_snapshot',
               (SELECT count(*) FROM eta_revision_alert_context
                 WHERE alert_snapshot_feed_timestamp > prediction_feed_timestamp)
        UNION ALL SELECT 'bridge_snapshot_within_max_age',
               (SELECT count(*) FROM eta_revision_example_alerts
                 WHERE epoch(prediction_feed_timestamp) - epoch(alert_snapshot_feed_timestamp)
                       > {max_age_s} OR alert_snapshot_feed_timestamp > prediction_feed_timestamp)
        UNION ALL SELECT 'observed_alerts_have_versions',
               (SELECT count(*) FROM rt_alert_observations o
                 WHERE NOT EXISTS (SELECT 1 FROM alert_versions v
                                   WHERE v.alert_fingerprint = o.alert_fingerprint))
        UNION ALL SELECT 'period_counts_consistent',
               (SELECT count(*) FROM alert_versions v
                 WHERE v.active_period_count <> (SELECT count(*) FROM alert_active_periods p
                                                 WHERE p.alert_fingerprint = v.alert_fingerprint))
        UNION ALL SELECT 'entity_counts_consistent',
               (SELECT count(*) FROM alert_versions v
                 WHERE v.informed_entity_count <> (SELECT count(*) FROM alert_informed_entities e
                                                   WHERE e.alert_fingerprint = v.alert_fingerprint))
        UNION ALL SELECT 'disruption_requires_structured_period',
               (SELECT count(*) FROM eta_revision_example_alerts
                 WHERE operational_disruption_active IS NOT NULL
                   AND NOT has_structured_active_period)
        UNION ALL SELECT 'annotation_entity_matches_observations',
               (SELECT count(*) FROM alert_annotations a
                 WHERE EXISTS (SELECT 1 FROM rt_alert_observations o
                               WHERE o.alert_fingerprint = a.alert_fingerprint)
                   AND NOT EXISTS (SELECT 1 FROM rt_alert_observations o
                                   WHERE o.alert_fingerprint = a.alert_fingerprint
                                     AND o.entity_id = a.entity_id))
        UNION ALL SELECT 'one_version_per_entity_per_snapshot',
               (SELECT count(*) FROM (SELECT feed_timestamp, entity_id FROM rt_alert_observations
                                      GROUP BY ALL HAVING count(*) > 1))
        """,
    ]


def load_alert_annotations(con: duckdb.DuckDBPyConnection, path: Path | None) -> int:
    """Create alert_annotations from a manually reviewed CSV (empty table if path is None).

    The file records a human reviewer's reading of each alert version's text. It is not an
    automated classifier: versions not listed stay 'unclassified'.
    """
    con.execute(
        "CREATE TABLE alert_annotations (entity_id VARCHAR, alert_fingerprint VARCHAR "
        "PRIMARY KEY, category VARCHAR NOT NULL, basis VARCHAR, reviewed_on DATE)"
    )
    if path is None:
        return 0
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(line for line in f if not line.startswith("#"))
        if reader.fieldnames != ANNOTATION_COLUMNS:
            raise AlertAnnotationError(
                f"{path}: expected columns {ANNOTATION_COLUMNS}, got {reader.fieldnames}"
            )
        rows = list(reader)
    for i, row in enumerate(rows, start=2):
        if row["category"] not in ALERT_CATEGORIES:
            raise AlertAnnotationError(
                f"{path} row {i}: category must be one of {ALERT_CATEGORIES}"
            )
        if len(row["alert_fingerprint"]) != 64:
            raise AlertAnnotationError(
                f"{path} row {i}: alert_fingerprint must be a SHA-256 hex digest"
            )
    fingerprints = [r["alert_fingerprint"] for r in rows]
    if len(set(fingerprints)) != len(fingerprints):
        raise AlertAnnotationError(f"{path}: duplicate alert_fingerprint")
    con.executemany(
        "INSERT INTO alert_annotations VALUES (?, ?, ?, ?, ?)",
        [[r[c] or None for c in ANNOTATION_COLUMNS] for r in rows],
    )
    return len(rows)


def alert_report(con: duckdb.DuckDBPyConnection) -> dict:
    """Counts for the build log and validation report."""

    def one(sql):
        cur = con.execute(sql)
        return dict(zip([d[0] for d in cur.description], cur.fetchone(), strict=True))

    def pairs(sql):
        return {str(k): v for k, v in con.execute(sql).fetchall()}

    report = one("""
        SELECT (SELECT count(*) FROM alert_snapshot_timeline) AS alert_snapshots,
               (SELECT count(*) FILTER (WHERE alert_count = 0) FROM alert_snapshot_timeline)
                   AS empty_snapshots,
               (SELECT count(DISTINCT entity_id) FROM rt_alert_observations) AS unique_alerts,
               (SELECT count(*) FROM alert_entity_versions) AS alert_versions,
               (SELECT count(*) FROM alert_visibility) AS visibility_intervals,
               (SELECT count(*) FROM rt_alert_observations) AS alert_observations
    """)
    report["cause"] = pairs(
        "SELECT coalesce(cause, '(not set)'), count(*) FROM alert_versions GROUP BY 1 ORDER BY 1"
    )
    report["effect"] = pairs(
        "SELECT coalesce(effect, '(not set)'), count(*) FROM alert_versions GROUP BY 1 ORDER BY 1"
    )
    report["informed_entity_scope"] = pairs(
        "SELECT scope, count(*) FROM alert_informed_entity_scope GROUP BY 1 ORDER BY 1"
    )
    report["versions_with_structured_active_period"] = one(
        "SELECT count(*) FILTER (WHERE active_period_count > 0) AS n FROM alert_versions"
    )["n"]
    report["version_categories"] = pairs("""
        SELECT coalesce(a.category, 'unclassified'), count(*)
        FROM alert_versions v LEFT JOIN alert_annotations a USING (alert_fingerprint)
        GROUP BY 1 ORDER BY 1
    """)
    report["example_alert_feed_status"] = pairs(
        "SELECT alert_feed_status, count(*) FROM eta_revision_alert_context GROUP BY 1 ORDER BY 1"
    )
    report["all_examples_unknown_alert_state_pct"] = one(
        "SELECT round(100 * avg((NOT alert_state_known)::INT), 2) AS p "
        "FROM eta_revision_alert_context"
    )["p"]
    report["tier_a_examples"] = one("""
        SELECT count(*) AS examples,
               count(*) FILTER (WHERE c.has_applicable_visible_alert)
                   AS with_applicable_visible_alert,
               round(100 * avg(c.has_applicable_visible_alert::INT), 2)
                   AS pct_with_applicable_visible_alert,
               count(*) FILTER (WHERE NOT c.alert_state_known) AS unknown_alert_state,
               round(100 * avg((NOT c.alert_state_known)::INT), 2) AS pct_unknown_alert_state,
               count(*) FILTER (WHERE c.operational_disruption_active) AS disruption_true,
               count(*) FILTER (WHERE c.operational_disruption_active = false)
                   AS disruption_false,
               count(*) FILTER (WHERE c.operational_disruption_active IS NULL)
                   AS disruption_unknown,
               count(*) FILTER (WHERE c.visible_system_wide) AS visible_system_wide,
               count(*) FILTER (WHERE c.visible_route) AS visible_route,
               count(*) FILTER (WHERE c.visible_trip) AS visible_trip,
               count(*) FILTER (WHERE c.visible_stop) AS visible_stop
        FROM eta_revision_alert_context c
        JOIN observed_arrival_proxy p USING (event_id)
        WHERE p.quality_tier = 'A'
    """)
    report["tier_a_alert_context_groups"] = {
        group: {"examples": n, "pct": pct}
        for group, n, pct in con.execute("""
            SELECT alert_context_group, count(*),
                   round(100 * count(*) / sum(count(*)) OVER (), 2)
            FROM eta_revision_alert_context c JOIN observed_arrival_proxy p USING (event_id)
            WHERE p.quality_tier = 'A' GROUP BY 1 ORDER BY 1
        """).fetchall()
    }
    report["unspecified_informed_entities"] = one(
        "SELECT count(*) AS n FROM alert_informed_entity_scope WHERE scope = 'unspecified'"
    )["n"]
    report["quality_checks"] = pairs("SELECT * FROM alert_quality_checks")
    return report


_SENSITIVITY_INPUTS = [
    "rt_alert_snapshots",
    "rt_alert_observations",
    "alert_versions",
    "alert_active_periods",
    "alert_informed_entities",
    "alert_annotations",
    "eta_revision_examples",
    "observed_arrival_proxy",
    "static_stops",
    "static_routes",
    "static_agency",
]
_ALERT_OBJECTS = [
    ("VIEW", "alert_quality_checks"),
    ("TABLE", "eta_revision_alert_context"),
    ("TABLE", "eta_revision_example_alerts"),
    ("VIEW", "alert_version_scope"),
    ("VIEW", "alert_informed_entity_scope"),
    ("VIEW", "alert_entity_versions"),
    ("TABLE", "alert_visibility"),
    ("TABLE", "alert_snapshot_timeline"),
]


@dataclass(frozen=True)
class StalenessResult:
    max_age_s: int
    tier_a_examples: int
    pct_unknown_alert_state: float
    groups: dict
    quality_check_failures: int


def staleness_main(argv: list[str] | None = None) -> int:
    import argparse
    import dataclasses
    import json

    parser = argparse.ArgumentParser(description="Alert-state staleness sensitivity.")
    parser.add_argument("--db", type=Path, default=Path("data/warehouse/bart.duckdb"))
    parser.add_argument("--ages", type=int, nargs="+", default=[60, 120, 180])
    args = parser.parse_args(argv)
    for result in run_staleness_sensitivity(args.db, tuple(args.ages)):
        print(json.dumps(dataclasses.asdict(result)))
    return 0


def run_staleness_sensitivity(db_path: Path, ages=(60, 120, 180)) -> list[StalenessResult]:
    """Rebuild the alert context in memory, from a read-only warehouse, for each max age."""
    con = duckdb.connect()
    try:
        escaped = str(db_path).replace("'", "''")
        con.execute(f"ATTACH '{escaped}' AS warehouse (READ_ONLY)")
        for name in _SENSITIVITY_INPUTS:
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM warehouse.{name}")
        results = []
        for age in ages:
            build_alert_tables(con, age)
            report = alert_report(con)
            results.append(
                StalenessResult(
                    max_age_s=age,
                    tier_a_examples=report["tier_a_examples"]["examples"],
                    pct_unknown_alert_state=report["tier_a_examples"]["pct_unknown_alert_state"],
                    groups=report["tier_a_alert_context_groups"],
                    quality_check_failures=sum(report["quality_checks"].values()),
                )
            )
            for kind, name in _ALERT_OBJECTS:
                con.execute(f"DROP {kind} IF EXISTS {name}")
        return results
    finally:
        con.close()
