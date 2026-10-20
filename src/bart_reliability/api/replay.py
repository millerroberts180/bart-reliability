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

Boards are grouped by boarding group, the way a train leaves the station, built from
the schedule (api/boarding.py, docs/boarding_groups.md), never by GTFS direction_id.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from bart_reliability.api.boarding import Boarding, group_boardings, group_label
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
        self._build_boarding_groups()
        self._stations: list[dict] | None = None

    def _build_boarding_groups(self) -> None:
        """Scheduled visits with the stations before and after them, and the boarding group
        of every way out of every station. Built over the whole feed, so a group's ID never
        depends on the service day."""
        self.con.execute(_VISITS_SQL)
        self.con.execute(
            "CREATE TABLE static_trip_station_visits AS "
            "SELECT trip_id, station_id, count(DISTINCT visit) AS visits, "
            "any_value(next_station_id) AS next_station_id "
            "FROM static_visits GROUP BY ALL"
        )
        boardings = self.con.execute(
            "SELECT DISTINCT station_id, previous_station_id, next_station_id "
            "FROM static_visits WHERE next_station_id IS NOT NULL"
        ).fetchall()
        mapping = group_boardings(Boarding(*b) for b in boardings)
        self.con.execute(
            "CREATE TABLE boarding_group_exits "
            "(station_id VARCHAR, next_station_id VARCHAR, group_id VARCHAR)"
        )
        if mapping:
            self.con.executemany(
                "INSERT INTO boarding_group_exits VALUES (?, ?, ?)",
                [(station, nxt, gid) for (station, nxt), gid in sorted(mapping.items())],
            )

    def _cursor(self) -> duckdb.DuckDBPyConnection:
        """A connection of its own for one call, used as `with self._cursor() as con:` so
        it is closed however the call ends. FastAPI runs the endpoints on a thread pool,
        and one DuckDB connection used by two threads at once mixes up their results. A
        cursor shares the in-memory tables but not session settings."""
        cur = self.con.cursor()
        try:
            cur.execute("SET TimeZone = 'UTC'")
        except BaseException:
            cur.close()
            raise
        return cur

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
        """Each station's boarding groups that have trains on the replay service date:
        destinations, platform and GTFS direction ids as served that day."""
        with self._cursor() as con:
            groups = con.execute(
                """
                WITH day AS (
                    SELECT DISTINCT v.trip_id, v.visit, v.station_id, v.previous_station_id,
                           v.next_station_id, v.departure_platform, t.trip_headsign,
                           CAST(t.direction_id AS VARCHAR) AS direction_id
                    FROM static_visits v
                    JOIN static_trips t ON t.trip_id = v.trip_id
                    JOIN static_service_days d
                      ON d.service_id = t.service_id AND d.service_date = ?
                )
                SELECT day.station_id, st.stop_name, g.group_id,
                       list(DISTINCT day.trip_headsign)
                           FILTER (WHERE day.trip_headsign IS NOT NULL),
                       list(DISTINCT day.departure_platform)
                           FILTER (WHERE day.departure_platform IS NOT NULL),
                       bool_or(day.departure_platform IS NULL),
                       list(DISTINCT day.direction_id) FILTER (WHERE day.direction_id IS NOT NULL)
                FROM day
                JOIN boarding_group_exits g
                  ON g.station_id = day.station_id AND g.next_station_id = day.next_station_id
                JOIN static_stops st ON st.stop_id = day.station_id AND st.location_type = 1
                GROUP BY ALL
                """,
                [self.service_date],
            ).fetchall()
            # A station is the end of the line when every train there starts or ends its
            # trip there: no train passes through.
            end_of_line = dict(
                con.execute(
                    """
                    SELECT v.station_id,
                           bool_and(v.previous_station_id IS NULL OR v.next_station_id IS NULL)
                    FROM (SELECT DISTINCT trip_id, visit, station_id, previous_station_id,
                                 next_station_id FROM static_visits) v
                    JOIN static_trips t ON t.trip_id = v.trip_id
                    JOIN static_service_days d
                      ON d.service_id = t.service_id AND d.service_date = ?
                    GROUP BY 1
                    """,
                    [self.service_date],
                ).fetchall()
            )
        stations: dict[str, dict] = {}
        for station_id, name, gid, headsigns, platforms, any_unknown, directions in groups:
            station = stations.setdefault(
                station_id,
                {
                    "id": station_id,
                    "name": name,
                    "end_of_line": bool(end_of_line.get(station_id)),
                    "boarding_groups": [],
                },
            )
            # list() over no rows is NULL.
            dests = sorted({destination(h) for h in headsigns or []} - {""})
            codes = sorted(platforms or [], key=_platform_order)
            station["boarding_groups"].append(
                {
                    "id": gid,
                    "label": group_label(dests),
                    "destinations": dests,
                    # A platform is named only when every train in the group that day
                    # leaves from it.
                    "platform": codes[0] if len(codes) == 1 and not any_unknown else None,
                    "platforms": codes,
                    "gtfs_direction_ids": sorted(directions or []),
                }
            )
        for station in stations.values():
            station["boarding_groups"].sort(
                key=lambda g: (
                    (_platform_order(g["platforms"][0]) if g["platforms"] else (1, "")) + (g["id"],)
                )
            )
            for g in station["boarding_groups"]:
                del g["platforms"]
        return sorted(stations.values(), key=lambda s: (s["name"], s["id"]))

    # -- predictions board ----------------------------------------------------------

    def board(self, station_id: str, group_id: str) -> tuple[list[dict], int, int]:
        """Trip-stops leaving the station in the boarding group in the replay snapshot,
        with every model feature computed from listings up to that snapshot. Also counts
        the trains listed at the station that cannot be placed (no scheduled visit to
        place them by) and those whose trips end here (they cannot be boarded)."""
        if self.snapshot is None:
            return [], 0, 0
        s = self.snapshot
        params = {"feed": s.feed_timestamp, "collected": s.collected_at, "station": station_id}
        with self._cursor() as con:
            cur = con.execute(_BOARD_SQL, params | {"group": group_id})
            names = [d[0] for d in cur.description]
            rows = [dict(zip(names, r, strict=True)) for r in cur.fetchall()]
            unplaced, terminating = con.execute(
                f"""
                WITH {_PLACED_SQL}
                SELECT count(*) FILTER (WHERE group_id IS NULL AND NOT ends_here),
                       count(*) FILTER (WHERE ends_here)
                FROM placed
                """,
                params,
            ).fetchone()
        return rows, int(unplaced), int(terminating)

    # -- alerts ---------------------------------------------------------------------

    def alerts(
        self, station_id: str, route_ids: list[str], trip_ids: list[str], max_age_s: int
    ) -> dict:
        """Alerts visible in the latest alert snapshot at or before the prediction
        snapshot (at most max_age_s old) that apply to the station or its routes."""
        if self.snapshot is None:
            return {"known": False, "snapshot": None, "age_seconds": None, "alerts": []}
        with self._cursor() as con:
            a = con.execute(
                "SELECT feed_timestamp, collected_at FROM asof_alert_snapshots "
                "WHERE feed_timestamp <= ? ORDER BY feed_timestamp DESC, collected_at DESC LIMIT 1",
                [self.snapshot.feed_timestamp],
            ).fetchone()
            if a is None:
                return {"known": False, "snapshot": None, "age_seconds": None, "alerts": []}
            age = int((self.snapshot.feed_timestamp - a[0]).total_seconds())
            if age > max_age_s:
                return {"known": False, "snapshot": a[0], "age_seconds": age, "alerts": []}
            rows = con.execute(
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
        with self._cursor() as con:
            rows = con.execute(
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


def _platform_order(code: str) -> tuple:
    """Platform "2" before "10"; codes that are not numbers after those that are."""
    return (0, int(code)) if code.isdigit() else (1, code)


# A visit is a trip's consecutive scheduled stops at one station (SFO lists two: the
# train arrives, reverses and leaves). One row per scheduled rail stop, with its visit's
# previous and next stations and the platform the train leaves from.
_VISITS_SQL = """
CREATE TABLE static_visits AS
WITH stops AS (
    SELECT st.trip_id, st.stop_sequence, p.parent_station AS station_id, p.platform_code,
           lag(p.parent_station) OVER w AS station_before
    FROM static_stop_times st
    JOIN static_stops p ON p.stop_id = st.stop_id
    JOIN static_trips t ON t.trip_id = st.trip_id
    JOIN static_routes r ON r.route_id = t.route_id
    WHERE r.route_type = 1 AND p.parent_station IS NOT NULL  -- trains, not bus bridges
    WINDOW w AS (PARTITION BY st.trip_id ORDER BY st.stop_sequence)
),
numbered AS (
    SELECT *, sum(CASE WHEN station_before IS DISTINCT FROM station_id THEN 1 ELSE 0 END)
                  OVER (PARTITION BY trip_id ORDER BY stop_sequence) AS visit
    FROM stops
),
visits AS (
    SELECT trip_id, visit, station_id,
           arg_max_null(platform_code, stop_sequence) AS departure_platform
    FROM numbered GROUP BY ALL
),
linked AS (
    SELECT *, lag(station_id) OVER w AS previous_station_id,
              lead(station_id) OVER w AS next_station_id
    FROM visits WINDOW w AS (PARTITION BY trip_id ORDER BY visit)
)
SELECT n.trip_id, n.stop_sequence, n.station_id, n.visit, l.previous_station_id,
       l.next_station_id, l.departure_platform
FROM numbered n JOIN linked l USING (trip_id, visit, station_id)
"""

# Every upcoming train the replay snapshot lists at $station, placed by its schedule:
# the matched scheduled stop gives its visit, and so where it goes next. A train listed
# at a platform its schedule does not use at this station is placed by its only visit
# to the station; with no such visit it is unplaced. GTFS direction_id is not used.
_PLACED_SQL = """
placed_rows AS (
    SELECT p.*, coalesce(p.service_date, p.inferred_service_date) AS event_service_date,
           st.parent_station AS station_id,
           -- The listed platform is the scheduled one exactly when the stop matched.
           CASE WHEN v.trip_id IS NOT NULL THEN st.platform_code END AS platform,
           coalesce(v.next_station_id, u.next_station_id) AS next_station_id,
           v.trip_id IS NOT NULL OR u.trip_id IS NOT NULL AS has_visit
    FROM asof_predictions p
    JOIN static_stops st ON st.stop_id = p.stop_id
    LEFT JOIN static_visits v
      ON v.trip_id = p.trip_id AND v.stop_sequence = p.scheduled_stop_sequence
    LEFT JOIN static_trip_station_visits u
      ON u.trip_id = p.trip_id AND u.station_id = st.parent_station AND u.visits = 1
    WHERE p.feed_timestamp = $feed AND p.collected_at = $collected
      AND st.parent_station = $station
      AND epoch(p.predicted_arrival) - epoch(p.feed_timestamp) >= 0  -- upcoming only
),
placed AS (
    SELECT r.*, g.group_id, r.has_visit AND r.next_station_id IS NULL AS ends_here
    FROM placed_rows r
    LEFT JOIN boarding_group_exits g
      ON g.station_id = r.station_id AND g.next_station_id = r.next_station_id
)
"""

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
WITH {_PLACED_SQL},
obs AS (
    SELECT coalesce(service_date, inferred_service_date) AS event_service_date,
           trip_id, stop_id, scheduled_stop_sequence AS stop_sequence,
           collected_at, feed_timestamp, predicted_arrival,
           trip_schedule_relationship, stop_schedule_relationship
    FROM asof_predictions
),
cur AS (
    SELECT * FROM placed WHERE group_id = $group
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
       c.trip_headsign, CAST(c.direction_id AS VARCHAR) AS gtfs_direction_id, c.platform,
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
