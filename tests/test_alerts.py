"""Synthetic tests for service-alert normalization and the point-in-time alert join.

Vocabulary under test: an alert can be *visible* (in the latest non-stale snapshot at
publication) and *applicable* (structured informed entities match) without any evidence
of an *operational disruption*, which needs a structured active period.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest
from google.transit import gtfs_realtime_pb2

from bart_reliability.collector.storage import save_snapshot
from bart_reliability.transform.alerts import alert_fingerprint, flatten_alert, run_alerts
from bart_reliability.warehouse.alerts import (
    AlertAnnotationError,
    alert_report,
    build_alert_tables,
    create_alert_views,
    load_alert_annotations,
    run_staleness_sensitivity,
)

T0 = datetime(2026, 10, 9, 15, 0, tzinfo=UTC)
REPO_ANNOTATIONS = Path(__file__).resolve().parents[1] / "config" / "alert_annotations.csv"


def at(minutes, seconds=0):
    return T0 + timedelta(minutes=minutes, seconds=seconds)


def make_alert(header, cause=None, effect=None, periods=(), entities=({"agency_id": "BART"},)):
    alert = gtfs_realtime_pb2.Alert()
    alert.header_text.translation.add(text=header, language="en")
    alert.description_text.translation.add(text=f"{header} details", language="en")
    alert.url.translation.add(text="https://www.bart.gov/schedules/advisories", language="en")
    if cause:
        alert.cause = gtfs_realtime_pb2.Alert.Cause.Value(cause)
    if effect:
        alert.effect = gtfs_realtime_pb2.Alert.Effect.Value(effect)
    for start, end in periods:
        p = alert.active_period.add()
        if start is not None:
            p.start = int(start.timestamp())
        if end is not None:
            p.end = int(end.timestamp())
    for e in entities:
        ie = alert.informed_entity.add()
        for key, value in e.items():
            if key == "trip_id":
                ie.trip.trip_id = value
            else:
                setattr(ie, key, value)
    return alert


SYS = make_alert("System delay", cause="TECHNICAL_PROBLEM", effect="SIGNIFICANT_DELAYS")
ROUTE07 = make_alert("Route 07 only", entities=({"route_id": "07"},))
STOPS = make_alert(
    "Stop work",
    cause="CONSTRUCTION",
    effect="DETOUR",
    entities=({"route_id": "1", "stop_id": "A30-1"}, {"stop_id": "PARENT_A40"}),
)
TRIP = make_alert("Trip T1 held", entities=({"trip_id": "T1"},))
PERIODS = make_alert("Two periods", periods=((at(2), at(3)), (at(8), None)))
OPEN_END = make_alert("Until further notice", periods=((at(5), None),))
CHANGE_V1 = make_alert("Version one")
CHANGE_V2 = make_alert("Version two")
UNSPECIFIED = make_alert("No selector", entities=({},))
# Route PX belongs to another agency, so only this alert can apply to it.
PX_WORK = make_alert(
    "PX planned work", periods=((at(9), at(9, 30)),), entities=({"route_id": "PX"},)
)

ANNOTATIONS = [
    ("SYS", SYS, "incident_like"),
    ("PERIODS", PERIODS, "planned_notice"),
    ("PX", PX_WORK, "planned_notice"),
]


def alerts_at(k: int) -> list[tuple[str, gtfs_realtime_pb2.Alert]]:
    """Alert entities in the snapshot at minute k (k=0 is an empty, valid feed)."""
    if k == 0:
        return []
    out = [
        ("ROUTE07", ROUTE07),
        ("STOPS", STOPS),
        ("TRIP", TRIP),
        ("PERIODS", PERIODS),
        ("OPEN_END", OPEN_END),
        ("UNSPEC", UNSPECIFIED),
        ("PX", PX_WORK),
        ("CHG", CHANGE_V1 if k <= 5 else CHANGE_V2),
    ]
    if k != 5:
        out.append(("SYS", SYS))  # disappears for one snapshot, then returns
    return out


def feed(feed_time: datetime, alerts) -> bytes:
    message = gtfs_realtime_pb2.FeedMessage()
    message.header.gtfs_realtime_version = "1.0"
    message.header.timestamp = int(feed_time.timestamp())
    for entity_id, alert in alerts:
        e = message.entity.add(id=entity_id)
        e.alert.CopyFrom(alert)
    if alerts:
        junk = message.entity.add(id="not-an-alert")  # malformed for this feed
        junk.trip_update.trip.trip_id = "X"
    return message.SerializeToString()


def write_snapshots(raw):
    for k in range(11):
        save_snapshot(raw, "alerts", at(k), feed(at(k), alerts_at(k)))
    # Re-download of the same publication 30 s later: a duplicate feed timestamp.
    save_snapshot(raw, "alerts", at(10, 30), feed(at(10), alerts_at(10)))


# (event_id, target, prediction feed time, trip, route, stop)
EXAMPLES = [
    ("E1", 300, at(2), "T1", "1", "A30-1"),
    ("E1", 600, at(4), "T1", "1", "A30-1"),
    ("E1", 900, at(5), "T1", "1", "A30-1"),
    ("E2", 300, at(3), "T2", "1", "A40-1"),
    ("E3", 100, at(-1), "T3", "1", "A50-1"),  # before any alert snapshot
    ("E3", 200, at(0), "T3", "1", "A50-1"),  # empty feed
    ("E3", 300, at(0, 59), "T3", "1", "A50-1"),  # just before minute 1: no future info
    ("E3", 400, at(10, 200), "T3", "1", "A50-1"),  # 200 s after the last snapshot
    ("E3", 500, at(10, 150), "T3", "1", "A50-1"),  # 150 s after the last snapshot
    ("E4", 300, at(5, 0), "T4", "07", "A50-1"),  # route 07, at the open-ended start
    ("E5", 300, at(3), "T5", "PX", "A50-1"),  # only PX_WORK applies; outside its period
]


def write_annotations(path: Path, rows: list[list[str]]) -> Path:
    header = "entity_id,alert_fingerprint,category,basis,reviewed_on"
    lines = ["# test annotations", header] + [",".join(r) for r in rows]
    path.write_text("\n".join(lines) + "\n")
    return path


def build(tmp_path, max_age_s=120, db_path=None):
    raw = tmp_path / "raw"
    if not raw.exists():
        write_snapshots(raw)
    processed = tmp_path / "processed"
    summary = run_alerts(raw, processed)
    ann = write_annotations(
        tmp_path / "ann.csv",
        [[eid, alert_fingerprint(a)[0], c, "test", "2026-10-12"] for eid, a, c in ANNOTATIONS],
    )
    con = duckdb.connect(str(db_path) if db_path else ":memory:")
    con.execute("CREATE TABLE static_agency AS SELECT 'BART' AS agency_id")
    con.execute("""CREATE TABLE static_routes AS SELECT * FROM (VALUES
        ('1', CAST(NULL AS VARCHAR), 1), ('07', NULL, 1), ('PX', 'OTHER', 1))
        t(route_id, agency_id, route_type)""")
    con.execute("""CREATE TABLE static_stops AS SELECT * FROM (VALUES
        ('A30-1', 'PARENT_A30'), ('A40-1', 'PARENT_A40'), ('A50-1', 'PARENT_A50'))
        t(stop_id, parent_station)""")
    con.execute(
        "CREATE TABLE eta_revision_examples (event_id VARCHAR, target_horizon_s INT, "
        "prediction_feed_timestamp TIMESTAMPTZ)"
    )
    con.execute(
        "CREATE TABLE observed_arrival_proxy (event_id VARCHAR, trip_id VARCHAR, "
        "route_id VARCHAR, direction_id INT, stop_id VARCHAR, quality_tier VARCHAR)"
    )
    for event_id, target, t, *_ in EXAMPLES:
        con.execute("INSERT INTO eta_revision_examples VALUES (?, ?, ?)", [event_id, target, t])
    for event_id, trip, route, stop in sorted({(e[0], e[3], e[4], e[5]) for e in EXAMPLES}):
        con.execute(
            "INSERT INTO observed_arrival_proxy VALUES (?, ?, ?, 0, ?, 'A')",
            [event_id, trip, route, stop],
        )
    create_alert_views(con, processed)
    load_alert_annotations(con, ann)
    build_alert_tables(con, max_age_s)
    return con, summary


@pytest.fixture
def wh(tmp_path):
    con, summary = build(tmp_path)
    yield con, summary
    con.close()


def rows(con, sql, params=None):
    cur = con.execute(sql, params or [])
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]


def context(con, event_id, target):
    (row,) = rows(
        con,
        "SELECT * FROM eta_revision_alert_context WHERE event_id = ? AND target_horizon_s = ?",
        [event_id, target],
    )
    return row


def bridge(con, event_id, target, entity_id):
    (row,) = rows(
        con,
        "SELECT * FROM eta_revision_example_alerts WHERE event_id = ? AND "
        "target_horizon_s = ? AND entity_id = ?",
        [event_id, target, entity_id],
    )
    return row


# --- normalization --------------------------------------------------------------------


def test_fingerprint_is_deterministic_and_content_based():
    again = make_alert("System delay", cause="TECHNICAL_PROBLEM", effect="SIGNIFICANT_DELAYS")
    assert alert_fingerprint(SYS)[0] == alert_fingerprint(again)[0]
    assert alert_fingerprint(CHANGE_V1)[0] != alert_fingerprint(CHANGE_V2)[0]


def test_flatten_keeps_fields_periods_and_entities_separate():
    version, periods, _ = flatten_alert(PERIODS)
    assert version["header_text"] == "Two periods"
    assert version["url"] == "https://www.bart.gov/schedules/advisories"
    assert (version["cause"], version["effect"]) == (None, None)  # absent, not defaulted
    assert [(p["active_start"], p["active_end"]) for p in periods] == [
        (int(at(2).timestamp()), int(at(3).timestamp())),
        (int(at(8).timestamp()), None),
    ]
    _, _, stop_entities = flatten_alert(STOPS)
    assert [(e["route_id"], e["stop_id"]) for e in stop_entities] == [
        ("1", "A30-1"),
        (None, "PARENT_A40"),
    ]
    assert flatten_alert(TRIP)[2][0]["trip_id"] == "T1"


def test_transform_summary_and_snapshot_manifest(tmp_path):
    con, summary = build(tmp_path)
    assert (summary.files_found, summary.files_duplicate_feed, summary.files_used) == (12, 1, 11)
    assert summary.empty_snapshots == 1
    assert summary.non_alert_entities_skipped == 10
    assert summary.versions == 10  # 9 distinct contents + the changed one
    manifest = rows(con, "SELECT alert_count FROM rt_alert_snapshots ORDER BY feed_timestamp")
    assert [r["alert_count"] for r in manifest] == [0, 9, 9, 9, 9, 8, 9, 9, 9, 9, 9]
    # Normalized: periods and entities hang off content versions, not snapshots.
    assert rows(con, "SELECT count(*) AS n FROM alert_active_periods")[0]["n"] == 4
    assert rows(con, "SELECT count(*) AS n FROM alert_informed_entities")[0]["n"] == 11


def test_transform_is_idempotent(tmp_path):
    names = ("alert_versions", "alert_active_periods", "alert_informed_entities")
    build(tmp_path)
    first = {
        d: pq.read_table(tmp_path / "processed" / d / "part.parquet").to_pylist() for d in names
    }
    con, _ = build(tmp_path)
    assert {
        d: pq.read_table(tmp_path / "processed" / d / "part.parquet").to_pylist() for d in names
    } == first
    assert rows(con, "SELECT count(*) AS n FROM rt_alert_observations")[0]["n"] == 10 * 9 - 1


# --- visibility and versions ------------------------------------------------------------


def test_visibility_intervals_follow_snapshot_presence(wh):
    con, _ = wh
    assert rows(
        con,
        "SELECT visible_from, last_seen, visible_until, visible_at_end_of_data "
        "FROM alert_visibility WHERE entity_id = 'SYS' ORDER BY interval_number",
    ) == [
        {
            "visible_from": at(1),
            "last_seen": at(4),
            "visible_until": at(5),
            "visible_at_end_of_data": False,
        },
        {
            "visible_from": at(6),
            "last_seen": at(10),
            "visible_until": None,
            "visible_at_end_of_data": True,
        },
    ]


def test_content_change_keeps_entity_id_with_new_version(wh):
    con, _ = wh
    assert rows(
        con,
        "SELECT v.version_number, a.header_text, v.first_seen, v.last_seen "
        "FROM alert_entity_versions v JOIN alert_versions a USING "
        "(alert_fingerprint) WHERE entity_id = 'CHG' ORDER BY version_number",
    ) == [
        {
            "version_number": 1,
            "header_text": "Version one",
            "first_seen": at(1),
            "last_seen": at(5),
        },
        {
            "version_number": 2,
            "header_text": "Version two",
            "first_seen": at(6),
            "last_seen": at(10),
        },
    ]


def test_scope_classification(wh):
    con, _ = wh
    scopes = {
        (r["header_text"], r["scope"])
        for r in rows(
            con,
            "SELECT v.header_text, s.scope FROM alert_informed_entity_scope s "
            "JOIN alert_versions v USING (alert_fingerprint)",
        )
    }
    assert {
        ("System delay", "system_wide"),
        ("Route 07 only", "route"),
        ("Stop work", "stop"),
        ("Trip T1 held", "trip"),
        ("No selector", "unspecified"),
    } <= scopes


# --- visibility versus disruption -----------------------------------------------------------


def test_visible_applicable_alerts_and_scope(wh):
    con, _ = wh
    c = context(con, "E1", 300)  # minute 2
    assert c["alert_feed_status"] == "observed" and c["alert_state_known"] is True
    assert c["alert_snapshot_age_s"] == 0
    assert c["applicable_visible_alert_ids"] == [
        "CHG",
        "OPEN_END",
        "PERIODS",
        "STOPS",
        "SYS",
        "TRIP",
    ]
    assert c["has_applicable_visible_alert"] is True
    assert c["most_specific_visible_scope"] == "stop"
    assert (c["visible_system_wide"], c["visible_trip"], c["visible_stop"], c["visible_route"]) == (
        True,
        True,
        True,
        False,
    )
    assert c["visible_causes"] == ["CONSTRUCTION", "TECHNICAL_PROBLEM"]
    assert c["visible_effects"] == ["DETOUR", "SIGNIFICANT_DELAYS"]


def test_structured_period_fields_are_separate_from_visibility(wh):
    con, _ = wh
    sys_row = bridge(con, "E1", 300, "SYS")  # visible, no period supplied
    assert sys_row["has_structured_active_period"] is False
    assert sys_row["within_structured_active_period"] is None
    assert sys_row["operational_disruption_active"] is None  # unknown, not true
    periods_row = bridge(con, "E1", 300, "PERIODS")  # minute 2, inside first window
    assert periods_row["within_structured_active_period"] is True
    assert periods_row["operational_disruption_active"] is True
    open_end = bridge(con, "E1", 300, "OPEN_END")  # starts at minute 5
    assert open_end["within_structured_active_period"] is False
    c = context(con, "E1", 300)
    assert (
        c["with_structured_period_count"],
        c["within_structured_period_count"],
        c["outside_structured_period_count"],
    ) == (2, 1, 1)
    assert c["operational_disruption_active"] is True


def test_operational_disruption_is_unknown_without_structured_support(wh):
    con, _ = wh
    c = context(con, "E1", 600)  # minute 4: both period alerts outside, others period-less
    assert c["has_applicable_visible_alert"] is True
    assert c["within_structured_period_count"] == 0
    assert c["operational_disruption_active"] is None
    only_period = context(con, "E5", 300)  # only PX_WORK applies, outside its period
    assert only_period["applicable_visible_alert_ids"] == ["PX"]
    assert only_period["operational_disruption_active"] is False
    no_alert = context(con, "E3", 200)
    assert no_alert["has_applicable_visible_alert"] is False
    assert no_alert["operational_disruption_active"] is None  # absence is not evidence


def test_inclusive_period_bounds(wh):
    con, _ = wh
    assert bridge(con, "E2", 300, "PERIODS")["within_structured_active_period"] is True  # end
    assert bridge(con, "E4", 300, "OPEN_END")["within_structured_active_period"] is True  # start
    assert bridge(con, "E1", 600, "PERIODS")["within_structured_active_period"] is False


def test_applicability_route_stop_trip_and_parent_station(wh):
    con, _ = wh
    assert "ROUTE07" not in context(con, "E1", 300)["applicable_visible_alert_ids"]
    e4 = context(con, "E4", 300)
    assert "ROUTE07" in e4["applicable_visible_alert_ids"] and e4["visible_route"] is True
    e2 = context(con, "E2", 300)  # stop A40-1 whose parent is PARENT_A40
    assert "STOPS" in e2["applicable_visible_alert_ids"]
    assert "TRIP" not in e2["applicable_visible_alert_ids"]
    assert bridge(con, "E2", 300, "STOPS")["matched_scope"] == "stop"
    assert "SYS" not in context(con, "E5", 300)["applicable_visible_alert_ids"]  # other agency


def test_alert_context_groups_follow_manual_annotations(wh):
    con, _ = wh
    assert context(con, "E1", 300)["alert_context_group"] == "applicable_visible_incident_like"
    e1_900 = context(con, "E1", 900)  # SYS absent: PERIODS planned, the rest unannotated
    assert e1_900["applicable_visible_planned_count"] == 1
    assert e1_900["alert_context_group"] == "applicable_visible_unclassified"
    assert context(con, "E5", 300)["alert_context_group"] == "applicable_visible_planned_notice"
    assert context(con, "E3", 200)["alert_context_group"] == "no_applicable_visible_alert"
    assert context(con, "E3", 400)["alert_context_group"] == "unknown_alert_state"
    assert bridge(con, "E1", 300, "CHG")["alert_category"] == "unclassified"


# --- temporal rules -------------------------------------------------------------------------


def test_temporal_boundaries_and_unknown_state(wh):
    con, _ = wh
    before = context(con, "E3", 100)
    assert before["alert_feed_status"] == "no_alert_snapshot"
    assert before["has_applicable_visible_alert"] is None  # unknown, not "no alert"
    empty = context(con, "E3", 200)
    assert (empty["alert_feed_status"], empty["has_applicable_visible_alert"]) == (
        "observed",
        False,
    )
    just_before = context(con, "E3", 300)  # 15:00:59 must not see the 15:01 snapshot
    assert just_before["alert_snapshot_feed_timestamp"] == at(0)
    assert just_before["has_applicable_visible_alert"] is False
    stale = context(con, "E3", 400)
    assert (stale["alert_feed_status"], stale["alert_snapshot_age_s"]) == (
        "alert_snapshot_stale",
        200,
    )
    assert stale["has_applicable_visible_alert"] is None
    assert stale["alert_state_known"] is False


def test_context_never_duplicates_prediction_rows(wh):
    con, _ = wh
    n_examples = rows(con, "SELECT count(*) AS n FROM eta_revision_examples")[0]["n"]
    n_context = rows(con, "SELECT count(*) AS n FROM eta_revision_alert_context")[0]["n"]
    n_bridge = rows(
        con,
        "SELECT count(*) AS n FROM eta_revision_example_alerts "
        "WHERE event_id = 'E1' AND target_horizon_s = 300",
    )[0]["n"]
    assert n_context == n_examples == len(EXAMPLES)
    assert n_bridge == 6  # many alerts for one prediction live only in the bridge
    joined = rows(
        con,
        "SELECT count(*) AS n FROM eta_revision_examples e "
        "JOIN eta_revision_alert_context c USING (event_id, target_horizon_s)",
    )
    assert joined[0]["n"] == n_examples


def test_quality_checks_and_report(wh):
    con, _ = wh
    report = alert_report(con)
    assert all(v == 0 for v in report["quality_checks"].values())
    assert (report["empty_snapshots"], report["unique_alerts"], report["alert_versions"]) == (
        1,
        9,
        10,
    )
    assert report["unspecified_informed_entities"] == 1
    assert report["version_categories"] == {
        "incident_like": 1,
        "planned_notice": 2,
        "unclassified": 7,
    }
    assert report["example_alert_feed_status"] == {
        "alert_snapshot_stale": 2,
        "no_alert_snapshot": 1,
        "observed": 8,
    }
    assert report["tier_a_examples"]["unknown_alert_state"] == 3


def test_staleness_sensitivity_is_reproducible(tmp_path):
    db = tmp_path / "w.duckdb"
    con, _ = build(tmp_path, db_path=db)
    con.close()
    first = run_staleness_sensitivity(db, (60, 120, 180))
    assert first == run_staleness_sensitivity(db, (60, 120, 180))
    unknown = {r.max_age_s: r.groups["unknown_alert_state"]["examples"] for r in first}
    # 60 s: stale at 150 s and 200 s; 120 s: same; 180 s: only the 200 s one, plus "no snapshot".
    assert unknown == {60: 3, 120: 3, 180: 2}
    assert all(r.quality_check_failures == 0 for r in first)


# --- annotation file ------------------------------------------------------------------------


def test_repository_annotation_file_is_valid_and_manual():
    con = duckdb.connect()
    assert load_alert_annotations(con, REPO_ANNOTATIONS) == 6
    assert dict(
        con.execute("SELECT category, count(*) FROM alert_annotations GROUP BY 1").fetchall()
    ) == {"incident_like": 5, "planned_notice": 1}
    assert "NOT an automated classifier" in REPO_ANNOTATIONS.read_text()


@pytest.mark.parametrize(
    ("rows_", "message"),
    [
        ([["A", "f" * 64, "outage", "x", "2026-10-12"]], "category must be one of"),
        ([["A", "abc", "incident_like", "x", "2026-10-12"]], "SHA-256"),
        (
            [
                ["A", "f" * 64, "incident_like", "x", "2026-10-12"],
                ["B", "f" * 64, "planned_notice", "x", "2026-10-12"],
            ],
            "duplicate",
        ),
    ],
)
def test_invalid_annotations_fail_clearly(tmp_path, rows_, message):
    with pytest.raises(AlertAnnotationError, match=message):
        load_alert_annotations(duckdb.connect(), write_annotations(tmp_path / "a.csv", rows_))


def test_full_pipeline_joins_alerts_to_revision_examples_idempotently(tmp_path):
    import test_eta_revision as sim
    from gtfs_fixtures import write_gtfs_zip

    from bart_reliability.transform.pipeline import run as run_trip_updates
    from bart_reliability.warehouse.build import build_warehouse

    raw = tmp_path / "raw" / "gtfs_rt"
    window = (sim.local(8, 10), sim.local(8, 20))
    for t in sim.snapshot_times():
        save_snapshot(raw, "trip_updates", t, sim.snapshot(t))
        visible = window[0] <= t <= window[1]
        save_snapshot(raw, "alerts", t, feed(t, [("SYS", SYS)] if visible else []))
    processed = tmp_path / "processed"
    run_trip_updates(raw, processed)
    run_alerts(raw, processed)
    gtfs_zip = write_gtfs_zip(tmp_path / "gtfs" / "google_transit.zip", sim.static_overrides())
    db = tmp_path / "w" / "bart.duckdb"

    def built():
        build_warehouse(gtfs_zip, processed, db, alert_annotations=REPO_ANNOTATIONS)
        with duckdb.connect(str(db), read_only=True) as con:
            return (
                rows(con, "SELECT * FROM eta_revision_alert_context ORDER BY ALL"),
                rows(con, "SELECT count(*) AS n FROM eta_revision_examples")[0]["n"],
                rows(con, "SELECT * FROM alert_quality_checks WHERE failures > 0"),
            )

    context_rows, n_examples, failed = built()
    assert len(context_rows) == n_examples > 0 and failed == []
    inside = [r for r in context_rows if window[0] <= r["prediction_feed_timestamp"] <= window[1]]
    outside = [r for r in context_rows if r not in inside]
    assert inside and all(
        r["has_applicable_visible_alert"] and r["visible_system_wide"] for r in inside
    )
    # SYS is not in the repository annotations, so it is "unclassified" here.
    assert {r["alert_context_group"] for r in inside} == {"applicable_visible_unclassified"}
    assert all(r["operational_disruption_active"] is None for r in context_rows)
    assert outside and not any(r["has_applicable_visible_alert"] for r in outside)
    assert built()[0] == context_rows
