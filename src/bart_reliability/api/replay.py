"""Historical replay: answer as of a past moment using only what had been collected by then.

At start-up the engine copies an allowlist of warehouse sources into an in-memory DuckDB.
Each time-stamped source is cut off at `as_of`. Then the warehouse is detached. Every
later query runs against those copies only. Labels, the observed-arrival proxy, the
modeling tables, alert visibility runs computed over the whole collection, and anything
collected after `as_of` cannot reach the inference path, because they are not in the
database the queries run on.

Features follow the training definitions in modeling/features.py exactly, but are
computed for every trip-stop listed in the latest snapshot at or before `as_of`, from
that trip-stop's listings up to the snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from bart_reliability.modeling.features import TRAILING_WINDOW_S
from bart_reliability.warehouse.eta_revision import (
    CANCELLED_TRIP_VALUES,
    EXCLUDED_ROUTE_IDS,
    EXCLUDED_STOP_PREFIXES,
    SKIPPED_STOP_VALUES,
)

PACIFIC = ZoneInfo("America/Los_Angeles")
# The feature schema this engine computes; must equal the bundle's.
FEATURE_SCHEMA_VERSION = "eta-revision-features-1"
SERVICE_DAY_START_HOUR = 3  # BART service days run from about 03:00 to 03:00


class WarehouseUnavailable(RuntimeError):
    """The warehouse is missing, incomplete, or does not cover the replay time."""


def _sql_list(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _ts(value: datetime) -> str:
    return f"TIMESTAMPTZ '{value.astimezone(UTC).isoformat()}'"


def service_date_of(ts: datetime) -> date:
    local = ts.astimezone(PACIFIC)
    return (local - timedelta(hours=SERVICE_DAY_START_HOUR)).date()


def allowed_sources(as_of: datetime, lookback_s: int, review_before: date) -> dict[str, str]:
    """name -> SQL over the attached warehouse `wh`. The only data the engine ever holds."""
    t, since = _ts(as_of), _ts(as_of - timedelta(seconds=lookback_s))
    seen = f"(SELECT alert_fingerprint FROM wh.rt_alert_observations WHERE collected_at <= {t})"
    return {
        # Real-time, cut off at as_of.
        "asof_predictions": (
            f"SELECT * FROM wh.rt_predictions_enriched "
            f"WHERE collected_at <= {t} AND collected_at > {since}"
        ),
        "asof_feed_snapshots": (
            f"SELECT feed_timestamp, collected_at FROM wh.rt_feed_snapshots "
            f"WHERE collected_at <= {t}"
        ),
        "asof_alert_snapshots": (
            f"SELECT feed_timestamp, collected_at, alert_count FROM wh.rt_alert_snapshots "
            f"WHERE collected_at <= {t}"
        ),
        "asof_alert_observations": (
            f"SELECT feed_timestamp, collected_at, entity_id, alert_fingerprint "
            f"FROM wh.rt_alert_observations WHERE collected_at <= {t}"
        ),
        # Alert content, only for versions already seen by as_of.
        "asof_alert_versions": (
            f"SELECT alert_fingerprint, header_text, description_text FROM wh.alert_versions "
            f"WHERE alert_fingerprint IN {seen}"
        ),
        "asof_alert_scope": (
            f"SELECT * FROM wh.alert_informed_entity_scope WHERE alert_fingerprint IN {seen}"
        ),
        # Manual categories, only if reviewed before the replay's Pacific date.
        "asof_alert_annotations": (
            f"SELECT alert_fingerprint, category, reviewed_on FROM wh.alert_annotations "
            f"WHERE reviewed_on < DATE '{review_before}'"
        ),
        # Published schedule (no time dimension; its retrieval date is checked).
        "static_stops": "SELECT * FROM wh.static_stops",
        "static_routes": "SELECT * FROM wh.static_routes",
        "static_trips": "SELECT * FROM wh.static_trips",
        "static_stop_times": "SELECT * FROM wh.static_stop_times",
        "static_calendar": "SELECT * FROM wh.static_calendar",
        "static_service_days": "SELECT * FROM wh.static_service_days",
        "static_feed_load": (
            "SELECT archive_label, archive_sha256, feed_version FROM wh.static_feed_load"
        ),
    }


# Columns of a board row that are model features, by their catalog names.
FEATURE_COLUMNS = (
    "published_horizon_s",
    "published_minus_scheduled_s",
    "stop_position",
    "stops_away",
    "seconds_since_first_seen",
    "eta_change_last_snapshot_s",
    "eta_change_last_5min_s",
    "eta_change_since_first_seen_s",
    "prior_change_count",
    "prior_abs_change_sum_s",
    "route_short_name",
    "stop_id",
    "hour_local",
    "service_day_type",
)


@dataclass(frozen=True)
class Snapshot:
    feed_timestamp: datetime
    collected_at: datetime


class ReplayEngine:
    def __init__(self, warehouse: Path, as_of: datetime, lookback_s: int):
        self.as_of = as_of.astimezone(UTC)
        self.service_date = service_date_of(self.as_of)
        if not Path(warehouse).is_file():
            raise WarehouseUnavailable(f"warehouse not found: {warehouse}")
        self.con = duckdb.connect()
        self.con.execute("SET TimeZone = 'UTC'")
        path = str(Path(warehouse).resolve()).replace("'", "''")
        self.con.execute(f"ATTACH '{path}' AS wh (READ_ONLY)")
        review_before = self.as_of.astimezone(PACIFIC).date()
        try:
            for name, sql in allowed_sources(self.as_of, lookback_s, review_before).items():
                self.con.execute(f"CREATE TABLE {name} AS {sql}")
        except duckdb.CatalogException as e:
            raise WarehouseUnavailable(f"warehouse is missing a required table: {e}") from e
        finally:
            self.con.execute("DETACH wh")
        self.tables = sorted(r[0] for r in self.con.execute("SHOW TABLES").fetchall())
        row = self.con.execute(
            "SELECT feed_timestamp, collected_at FROM asof_feed_snapshots "
            "ORDER BY collected_at DESC, feed_timestamp DESC LIMIT 1"
        ).fetchone()
        self.snapshot = Snapshot(*row) if row else None
        label = self.con.execute("SELECT min(archive_label) FROM static_feed_load").fetchone()[0]
        self.static_archive_label = label
        self.con.execute(_STOP_POSITIONS_SQL)
        self._stations: list[dict] | None = None

    # -- data checks ----------------------------------------------------------------

    def problems(self, stale_after_s: int) -> list[str]:
        out = []
        if self.snapshot is None:
            out.append("no trip-update snapshot at or before as_of")
        elif self.freshness_seconds() > stale_after_s:
            out.append(
                f"latest snapshot is {self.freshness_seconds()} s older than as_of "
                f"(stale after {stale_after_s} s)"
            )
        try:
            retrieved = date.fromisoformat(self.static_archive_label or "")
        except ValueError:
            out.append("static schedule retrieval date is unknown")
        else:
            if retrieved > self.as_of.astimezone(PACIFIC).date():
                out.append("static schedule was retrieved after as_of")
        return out

    def freshness_seconds(self) -> int | None:
        if self.snapshot is None:
            return None
        return int((self.as_of - self.snapshot.feed_timestamp).total_seconds())

    # -- stations -------------------------------------------------------------------

    def stations(self) -> list[dict]:
        """Parent stations with scheduled service on the replay service date (cached)."""
        if self._stations is None:
            self._stations = self._load_stations()
        return self._stations

    def _load_stations(self) -> list[dict]:
        rows = self.con.execute(
            """
            SELECT st.stop_id, st.stop_name, t.direction_id, list(DISTINCT t.trip_headsign
                   ORDER BY t.trip_headsign) AS destinations
            FROM static_stops st
            JOIN static_stops platform ON platform.parent_station = st.stop_id
            JOIN static_stop_times s ON s.stop_id = platform.stop_id
            JOIN static_trips t ON t.trip_id = s.trip_id
            JOIN static_service_days d ON d.service_id = t.service_id AND d.service_date = ?
            WHERE st.location_type = 1 AND t.direction_id IS NOT NULL
            GROUP BY st.stop_id, st.stop_name, t.direction_id
            ORDER BY st.stop_name, st.stop_id, t.direction_id
            """,
            [self.service_date],
        ).fetchall()
        stations: dict[str, dict] = {}
        for stop_id, name, direction, headsigns in rows:
            station = stations.setdefault(stop_id, {"id": stop_id, "name": name, "directions": []})
            dests = sorted({destination(h) for h in headsigns if h})
            station["directions"].append(
                {"id": str(direction), "label": _direction_label(dests), "destinations": dests}
            )
        return list(stations.values())

    # -- predictions board ----------------------------------------------------------

    def board(self, station_id: str, direction_id: str) -> tuple[list[dict], int]:
        """Trip-stops at the station and direction in the replay snapshot, with every
        model feature computed from listings up to that snapshot. Also returns how many
        listed trains at the station could not be placed (no static trip match)."""
        if self.snapshot is None:
            return [], 0
        s = self.snapshot
        params = {
            "feed": s.feed_timestamp,
            "collected": s.collected_at,
            "station": station_id,
            "direction": direction_id,
        }
        cur = self.con.execute(_BOARD_SQL, params)
        names = [d[0] for d in cur.description]
        rows = [dict(zip(names, r, strict=True)) for r in cur.fetchall()]
        unplaced = self.con.execute(
            """
            SELECT count(*) FROM asof_predictions p
            JOIN static_stops st ON st.stop_id = p.stop_id
            WHERE p.feed_timestamp = $feed AND p.collected_at = $collected
              AND st.parent_station = $station AND p.direction_id IS NULL
              AND epoch(p.predicted_arrival) - epoch(p.feed_timestamp) >= 0
            """,
            {"feed": s.feed_timestamp, "collected": s.collected_at, "station": station_id},
        ).fetchone()[0]
        return rows, int(unplaced)

    # -- alerts ---------------------------------------------------------------------

    def alerts(
        self, station_id: str, route_ids: list[str], trip_ids: list[str], max_age_s: int
    ) -> dict:
        """Alerts visible in the latest alert snapshot at or before the prediction
        snapshot (at most max_age_s old) that apply to the station or its routes."""
        if self.snapshot is None:
            return {"known": False, "snapshot": None, "age_seconds": None, "alerts": []}
        a = self.con.execute(
            "SELECT feed_timestamp, collected_at FROM asof_alert_snapshots "
            "WHERE feed_timestamp <= ? ORDER BY feed_timestamp DESC, collected_at DESC LIMIT 1",
            [self.snapshot.feed_timestamp],
        ).fetchone()
        if a is None:
            return {"known": False, "snapshot": None, "age_seconds": None, "alerts": []}
        age = int((self.snapshot.feed_timestamp - a[0]).total_seconds())
        if age > max_age_s:
            return {"known": False, "snapshot": a[0], "age_seconds": age, "alerts": []}
        rows = self.con.execute(
            _ALERTS_SQL,
            {
                "feed": a[0],
                "collected": a[1],
                "station": station_id,
                "routes": route_ids or [""],
                "trips": trip_ids or [""],
            },
        ).fetchall()
        alerts = [
            {
                "alert_id": entity_id,
                "scope": scope,
                "category": category,
                "header_text": header or "",
                "description_text": description,
                "visible_since": since,
            }
            for entity_id, scope, category, header, description, since in rows
        ]
        return {"known": True, "snapshot": a[0], "age_seconds": age, "alerts": alerts}

    # -- history --------------------------------------------------------------------

    def history(self, prediction_id: str) -> list[dict] | None:
        key = parse_prediction_id(prediction_id)
        if key is None:
            return None
        service_date, trip_id, stop_sequence = key
        rows = self.con.execute(
            """
            SELECT feed_timestamp, predicted_arrival,
                   CAST(epoch(predicted_arrival) - epoch(feed_timestamp) AS INTEGER)
            FROM asof_predictions
            WHERE coalesce(service_date, inferred_service_date) = ?
              AND trip_id = ? AND scheduled_stop_sequence = ?
              AND predicted_arrival IS NOT NULL
            ORDER BY collected_at, feed_timestamp
            """,
            [service_date, trip_id, stop_sequence],
        ).fetchall()
        if not rows:
            return None
        return [
            {"feed_timestamp": f, "published_eta_at": p, "published_eta_seconds": s}
            for f, p, s in rows
        ]


def destination(headsign: str | None) -> str:
    """BART headsigns list via points ("SFO / SF / Antioch"); the last part is where the
    train ends. Names that contain a slash ("Pittsburg/Bay Point") have no spaces."""
    return headsign.split(" / ")[-1].strip() if headsign else ""


def prediction_id(service_date: date, trip_id: str, stop_sequence: int) -> str:
    return f"{service_date}:{trip_id}:{stop_sequence}"


def parse_prediction_id(value: str) -> tuple[date, str, int] | None:
    try:
        day, rest = value.split(":", 1)
        trip_id, seq = rest.rsplit(":", 1)
        return date.fromisoformat(day), trip_id, int(seq)
    except ValueError:
        return None


def _direction_label(destinations: list[str]) -> str:
    if not destinations:
        return "Toward unlisted destinations"
    if len(destinations) == 1:
        return f"Toward {destinations[0]}"
    return f"Toward {', '.join(destinations[:-1])} and {destinations[-1]}"


_STOP_POSITIONS_SQL = """
CREATE TABLE static_stop_positions AS
SELECT trip_id, stop_sequence, stop_id,
       CAST(row_number() OVER (PARTITION BY trip_id ORDER BY stop_sequence) AS INTEGER)
           AS stop_position
FROM static_stop_times
"""

_EXCLUDED_STOPS = " OR ".join(f"c.stop_id LIKE '{p}%'" for p in EXCLUDED_STOP_PREFIXES)

# Feature definitions mirror modeling/features.py (_statements and _FEATURES_SQL), with the
# event identified by (service date, trip, stop, stop sequence) as in the warehouse.
_BOARD_SQL = f"""
WITH obs AS (
    SELECT coalesce(service_date, inferred_service_date) AS event_service_date,
           trip_id, stop_id, scheduled_stop_sequence AS stop_sequence,
           collected_at, feed_timestamp, predicted_arrival,
           trip_schedule_relationship, stop_schedule_relationship
    FROM asof_predictions
),
cur AS (
    SELECT p.*, coalesce(p.service_date, p.inferred_service_date) AS event_service_date,
           st.parent_station AS station_id
    FROM asof_predictions p
    JOIN static_stops st ON st.stop_id = p.stop_id
    WHERE p.feed_timestamp = $feed AND p.collected_at = $collected
      AND st.parent_station = $station AND CAST(p.direction_id AS VARCHAR) = $direction
      AND p.predicted_arrival IS NOT NULL
      AND epoch(p.predicted_arrival) - epoch(p.feed_timestamp) >= 0  -- upcoming only
),
hist AS (
    SELECT o.*,
           CAST(epoch(o.predicted_arrival)
                - epoch(lag(o.predicted_arrival) OVER w) AS INTEGER) AS change_s
    FROM obs o
    JOIN cur c
      ON c.event_service_date = o.event_service_date AND c.trip_id = o.trip_id
     AND c.stop_id = o.stop_id AND c.scheduled_stop_sequence IS NOT DISTINCT FROM o.stop_sequence
    WINDOW w AS (PARTITION BY o.event_service_date, o.trip_id, o.stop_id, o.stop_sequence
                 ORDER BY o.collected_at, o.feed_timestamp)
),
agg AS (
    SELECT event_service_date, trip_id, stop_id, stop_sequence,
           min(collected_at) AS first_seen_at,
           arg_min(predicted_arrival, collected_at) AS first_estimate,
           arg_max_null(change_s, collected_at) AS change_at_snapshot_s,
           count(*) FILTER (WHERE change_s <> 0) AS prior_change_count,
           coalesce(sum(abs(change_s)), 0) AS prior_abs_change_sum_s,
           arg_min(predicted_arrival, collected_at) FILTER (
               WHERE collected_at >= $collected - INTERVAL {TRAILING_WINDOW_S} SECOND
           ) AS window_start_estimate,
           bool_or(trip_schedule_relationship = 'ADDED') AS added_trip,
           bool_or(trip_schedule_relationship IN ({_sql_list(CANCELLED_TRIP_VALUES)}))
               AS cancelled_trip,
           bool_or(stop_schedule_relationship IN ({_sql_list(SKIPPED_STOP_VALUES)}))
               AS skipped_stop
    FROM hist GROUP BY ALL
),
listed AS (
    SELECT p.trip_id, min(sp.stop_position) AS first_listed
    FROM asof_predictions p
    JOIN static_stop_positions sp ON sp.trip_id = p.trip_id AND sp.stop_id = p.stop_id
    WHERE p.feed_timestamp = $feed AND p.collected_at = $collected
      AND p.trip_id IN (SELECT trip_id FROM cur)
    GROUP BY 1
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
SELECT c.event_service_date, c.trip_id, c.stop_id, c.scheduled_stop_sequence AS stop_sequence,
       c.station_id, c.stop_name, c.route_id, c.route_short_name, c.route_long_name,
       c.trip_headsign, CAST(c.direction_id AS VARCHAR) AS direction_id,
       c.feed_timestamp, c.collected_at, c.predicted_arrival,
       CAST(epoch(c.predicted_arrival) - epoch(c.feed_timestamp) AS INTEGER)
           AS current_eta_seconds,
       -- model features (training definitions)
       CAST(epoch(c.predicted_arrival) - epoch(c.collected_at) AS INTEGER)
           AS published_horizon_s,
       CAST(epoch(c.predicted_arrival) - epoch(c.scheduled_arrival) AS INTEGER)
           AS published_minus_scheduled_s,
       sp.stop_position,
       sp.stop_position - l.first_listed AS stops_away,
       CAST(hour(timezone('America/Los_Angeles', c.collected_at)) AS INTEGER) AS hour_local,
       coalesce(d.service_day_type, 'unknown') AS service_day_type,
       CAST(epoch(c.collected_at) - epoch(a.first_seen_at) AS INTEGER)
           AS seconds_since_first_seen,
       coalesce(a.change_at_snapshot_s, 0) AS eta_change_last_snapshot_s,
       CAST(epoch(c.predicted_arrival) - epoch(a.window_start_estimate) AS INTEGER)
           AS eta_change_last_5min_s,
       CAST(epoch(c.predicted_arrival) - epoch(a.first_estimate) AS INTEGER)
           AS eta_change_since_first_seen_s,
       CAST(a.prior_change_count AS INTEGER) AS prior_change_count,
       CAST(a.prior_abs_change_sum_s AS INTEGER) AS prior_abs_change_sum_s,
       -- populations the models were never trained on, knowable at the snapshot
       CASE WHEN {_EXCLUDED_STOPS} OR c.route_id IN ({_sql_list(EXCLUDED_ROUTE_IDS)})
                THEN 'line not covered by the model (Antioch extension or Oakland Airport)'
            WHEN a.added_trip THEN 'added trip, not in the published schedule'
            WHEN a.cancelled_trip THEN 'trip cancelled or deleted in the feed'
            WHEN a.skipped_stop THEN 'stop marked skipped or without data in the feed'
            WHEN c.match_status <> 'matched' THEN 'no matching scheduled stop time'
            WHEN c.is_ambiguous_match THEN 'stop visited twice on this trip (ambiguous)'
            WHEN NOT c.include_in_primary_metrics THEN 'schedule match not usable'
            WHEN sp.stop_position = 1 THEN 'trip origin: a departure, not an approach'
       END AS population_reason
FROM cur c
LEFT JOIN agg a
  ON a.event_service_date = c.event_service_date AND a.trip_id = c.trip_id
 AND a.stop_id = c.stop_id AND a.stop_sequence IS NOT DISTINCT FROM c.scheduled_stop_sequence
LEFT JOIN static_stop_positions sp
  ON sp.trip_id = c.trip_id AND sp.stop_sequence = c.scheduled_stop_sequence
LEFT JOIN listed l ON l.trip_id = c.trip_id
LEFT JOIN day_type d ON d.trip_id = c.trip_id
ORDER BY current_eta_seconds, c.trip_id, c.stop_id
"""

_ALERTS_SQL = """
WITH snaps AS (
    SELECT feed_timestamp, collected_at,
           row_number() OVER (ORDER BY feed_timestamp, collected_at) AS k
    FROM asof_alert_snapshots
),
obs AS (
    SELECT o.entity_id, o.alert_fingerprint, s.k, s.feed_timestamp
    FROM asof_alert_observations o
    JOIN snaps s USING (feed_timestamp, collected_at)
),
runs AS (
    SELECT *, k - row_number() OVER (PARTITION BY entity_id, alert_fingerprint ORDER BY k)
               AS run_key
    FROM obs
),
current_run AS (
    SELECT r.entity_id, r.alert_fingerprint, r.run_key
    FROM runs r JOIN snaps s ON s.k = r.k
    WHERE s.feed_timestamp = $feed AND s.collected_at = $collected
),
since AS (
    SELECT c.entity_id, c.alert_fingerprint, min(r.feed_timestamp) AS visible_since
    FROM current_run c JOIN runs r USING (entity_id, alert_fingerprint, run_key)
    GROUP BY ALL
),
applies AS (
    SELECT c.entity_id, c.alert_fingerprint,
           arg_min(CASE ie.scope WHEN 'stop' THEN 'station' WHEN 'system_wide' THEN 'system'
                                 ELSE 'route' END, ie.scope_rank) AS scope
    FROM current_run c
    JOIN asof_alert_scope ie USING (alert_fingerprint)
    LEFT JOIN static_stops st ON st.stop_id = ie.stop_id
    WHERE (ie.scope = 'system_wide')
       OR (ie.scope = 'route'
           AND coalesce(ie.route_id, ie.trip_route_id) IN (SELECT unnest($routes)))
       OR (ie.scope = 'route_type' AND ie.route_type IN (
               SELECT route_type FROM static_routes WHERE route_id IN (SELECT unnest($routes))))
       OR (ie.scope = 'trip' AND ie.trip_id IN (SELECT unnest($trips)))
       OR (ie.scope = 'stop' AND (ie.stop_id = $station OR st.parent_station = $station))
    GROUP BY ALL
)
SELECT a.entity_id,
       a.scope,
       CASE ann.category WHEN 'planned_notice' THEN 'planned_work'
                         WHEN 'incident_like' THEN 'incident'
                         ELSE 'unclassified' END AS category,
       v.header_text,
       v.description_text,
       s.visible_since
FROM applies a
JOIN since s USING (entity_id, alert_fingerprint)
LEFT JOIN asof_alert_versions v USING (alert_fingerprint)
LEFT JOIN asof_alert_annotations ann USING (alert_fingerprint)
ORDER BY s.visible_since, a.entity_id
"""
