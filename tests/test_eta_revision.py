"""Synthetic tests for the ETA revision dataset and its observed-arrival proxy endpoint.

Each scenario simulates a BART-like feed: one snapshot every 60 s, stops listed until
shortly after the train reaches them, the trip's final stop never published, and
estimates that converge on the arrival time as the train approaches.
"""

from datetime import UTC, date, datetime, timedelta

import duckdb
import pytest
from google.transit import gtfs_realtime_pb2
from gtfs_fixtures import write_gtfs_zip

from bart_reliability.collector.storage import save_snapshot
from bart_reliability.transform.pipeline import run as run_transform
from bart_reliability.warehouse.build import build_warehouse
from bart_reliability.warehouse.eta_revision_config import ETARevisionConfig

SERVICE_DAY = date(2026, 10, 9)  # Friday, PDT (UTC-7)
PERSIST_S = 20  # stop stays listed this long after the train arrives


def local(h, m, s=0) -> datetime:
    """Local time on SERVICE_DAY (hours may exceed 23) as UTC."""
    midnight_utc = datetime(2026, 10, 9, 7, 0, tzinfo=UTC)
    return midnight_utc + timedelta(hours=h, minutes=m, seconds=s)


def gtfs_time(t: datetime) -> str:
    seconds = int((t - local(0, 0)).total_seconds())
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


STOP_IDS = ["A10-1", "A20-1", "A30-1", "A40-1", "A50-1", "A60-1"]
SEQUENCES = [1, 3, 4, 6, 7, 8]  # gaps, like BART's stop_sequence numbering
DAY_TIMES = [(8, 0), (8, 20), (8, 30), (8, 40), (8, 50), (9, 0)]
NIGHT_TIMES = [(23, 40), (23, 55), (24, 5), (24, 15), (24, 25), (24, 35)]
SFO_STOPS = [
    ("M10-1", 1, (8, 0)),
    ("Y10-1", 2, (8, 20)),
    ("Y10-1", 3, (8, 22)),
    ("W10-1", 4, (8, 40)),
    ("W20-1", 5, (8, 50)),
    ("W30-1", 6, (9, 0)),
]


def line(times):
    return [(s, q, local(*t)) for s, q, t in zip(STOP_IDS, SEQUENCES, times, strict=True)]


# trip_id -> stops [(stop_id, stop_sequence, scheduled)], plus simulation options.
TRIPS = {
    "P_NORMAL": {"stops": line(DAY_TIMES)},
    "P_FLICKER": {"stops": line(DAY_TIMES), "hide": {("A30-1", local(8, 15))}},
    "P_VANISH": {"stops": line(DAY_TIMES), "visible_until": local(8, 25)},
    "P_CANCEL": {"stops": line(DAY_TIMES), "trip_rel": "CANCELED"},
    "P_SKIP": {"stops": line(DAY_TIMES), "skip": {"A30-1"}},
    "P_UNSTABLE": {"stops": line(DAY_TIMES), "bump": {("A30-1", local(8, 29)): 120}},
    "P_SFO": {"stops": [(s, q, local(*t)) for s, q, t in SFO_STOPS]},
    "P_NIGHT": {"stops": line(NIGHT_TIMES)},
    # BART drops A30 5 minutes before its (stable, exact) estimated arrival.
    "P_EARLY_DROP": {"stops": line(DAY_TIMES), "exact": True, "drop_early": {"A30-1": 300}},
}
DELAY_S = 30  # every train arrives 30 s late, i.e. at :30 past the minute


def static_overrides():
    stops = [["stop_id", "stop_name", "stop_lat", "stop_lon", "location_type", "parent_station"]]
    for stop_id in [*STOP_IDS, "M10-1", "Y10-1", "W10-1", "W20-1", "W30-1"]:
        stops.append([stop_id, stop_id, "37.7", "-122.4", "0", stop_id[:3]])
    trips = [["route_id", "service_id", "trip_id", "trip_headsign", "direction_id"]]
    stop_times = [["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]]
    for trip_id, spec in TRIPS.items():
        trips.append(["1", "WKDY", trip_id, "Somewhere", "0"])
        for stop_id, seq, scheduled in spec["stops"]:
            t = gtfs_time(scheduled)
            stop_times.append([trip_id, t, t, stop_id, str(seq)])
    return {"stops.txt": stops, "trips.txt": trips, "stop_times.txt": stop_times}


def estimate(arrival: datetime, now: datetime) -> datetime:
    """BART-like estimate: optimistic by horizon/15, exact within 3 minutes."""
    horizon = (arrival - now).total_seconds()
    bias = 0 if horizon <= 180 else min(horizon, 900) // 15
    return arrival - timedelta(seconds=bias)


def snapshot(now: datetime, trips=TRIPS) -> bytes:
    message = gtfs_realtime_pb2.FeedMessage()
    message.header.gtfs_realtime_version = "1.0"
    message.header.timestamp = int(now.timestamp())
    rel = gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship
    stop_rel = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.ScheduleRelationship
    for trip_id, spec in trips.items():
        stops = spec["stops"]
        first, last = stops[0][2], stops[-1][2]
        if not (first - timedelta(minutes=50) <= now <= last):
            continue
        if "visible_until" in spec and now > spec["visible_until"]:
            continue
        listed = []
        for stop_id, _seq, scheduled in stops[:-1]:  # final stop is never published
            arrival = scheduled + timedelta(seconds=DELAY_S)
            if now >= arrival + timedelta(seconds=PERSIST_S):
                continue  # train has passed: stop drops off the list
            if now >= arrival - timedelta(seconds=spec.get("drop_early", {}).get(stop_id, -1e9)):
                continue
            if (stop_id, now) in spec.get("hide", set()):
                continue
            if any(s == stop_id for s, _ in listed):
                continue  # BART lists a repeated stop once
            predicted = arrival if spec.get("exact") else estimate(arrival, now)
            predicted += timedelta(seconds=spec.get("bump", {}).get((stop_id, now), 0))
            listed.append((stop_id, predicted))
        if not listed:
            continue
        entity = message.entity.add(id=trip_id)
        entity.trip_update.trip.trip_id = trip_id
        entity.trip_update.trip.schedule_relationship = rel.Value(spec.get("trip_rel", "SCHEDULED"))
        for stop_id, predicted in listed:
            stu = entity.trip_update.stop_time_update.add(stop_id=stop_id)
            stu.arrival.time = int(predicted.timestamp())
            if stop_id in spec.get("skip", set()):
                stu.schedule_relationship = stop_rel.SKIPPED
    return message.SerializeToString()


def snapshot_times(skip_local=()):
    times = []
    for start, end in [(local(7, 25), local(9, 10)), (local(23, 0), local(24, 40))]:
        t = start
        while t <= end:
            if not any(a <= t <= b for a, b in skip_local):
                times.append(t)
            t += timedelta(minutes=1)
    return times


def build(tmp_path, times, trips=TRIPS):
    raw = tmp_path / "raw" / "gtfs_rt"
    for t in times:
        save_snapshot(raw, "trip_updates", t, snapshot(t, trips))
    processed = tmp_path / "processed"
    run_transform(raw, processed)
    gtfs_zip = write_gtfs_zip(tmp_path / "gtfs" / "google_transit.zip", static_overrides())
    db = tmp_path / "warehouse" / "bart.duckdb"
    result = build_warehouse(gtfs_zip, processed, db)
    return db, result


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory):
    return build(tmp_path_factory.mktemp("proxy"), snapshot_times())


def query(db, sql, params=None):
    with duckdb.connect(str(db), read_only=True) as con:
        cursor = con.execute(sql, params or [])
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]


def event(db, trip_id, stop_id):
    (row,) = query(
        db,
        "SELECT *, epoch(proxy_arrival)::BIGINT AS proxy_epoch FROM observed_arrival_proxy "
        "WHERE trip_id = ? AND stop_id = ?",
        [trip_id, stop_id],
    )
    return row


def arrival(trip_id, stop_id):
    scheduled = next(s for sid, _, s in TRIPS[trip_id]["stops"] if sid == stop_id)
    return int((scheduled + timedelta(seconds=DELAY_S)).timestamp())


def test_normal_progression_is_eligible_tier_a(warehouse):
    db, _ = warehouse
    row = event(db, "P_NORMAL", "A30-1")
    assert row["is_eligible"] is True
    assert row["exclusion_reason"] is None
    assert row["quality_tier"] == "A"
    assert row["proxy_method"] == "last_stable_estimate_before_downstream_progression"
    assert row["proxy_epoch"] == arrival("P_NORMAL", "A30-1")
    assert row["service_date"] == SERVICE_DAY
    assert (row["stop_sequence"], row["stop_position"]) == (4, 3)
    assert row["last_seen_at"] == local(8, 30)
    assert row["confirmed_absent_at"] == local(8, 31)
    assert row["next_snapshot_min_stop_position"] == 4  # downstream stop A40 still listed
    assert row["final_estimate_spread_s"] == 0
    assert len(row["final_estimates"]) == ETARevisionConfig().stability_window
    assert row["max_collection_gap_s"] == 60
    assert row["listed_after_estimate_s"] == -30
    assert row["disappearance_window_s"] == 60
    assert row["uncertainty_s"] == 60  # the 60 s snapshot spacing dominates
    assert row["horizons_available"] == [300, 600, 900]


def test_origin_and_last_published_stop_are_excluded(warehouse):
    db, _ = warehouse
    assert event(db, "P_NORMAL", "A10-1")["exclusion_reason"] == "trip_origin"
    # A50 is the last stop BART lists (A60, the terminal, is never published), so the
    # whole trip leaves the feed when A50 drops off: no downstream confirmation.
    assert event(db, "P_NORMAL", "A50-1")["exclusion_reason"] == "trip_left_feed"
    assert not query(db, "SELECT 1 FROM observed_arrival_proxy WHERE stop_id = 'A60-1'")


def test_temporary_disappearance_uses_final_disappearance_and_lowers_tier(warehouse):
    db, _ = warehouse
    row = event(db, "P_FLICKER", "A30-1")
    assert row["is_eligible"] is True
    assert row["stop_missing_snapshots"] == 1
    assert row["last_seen_at"] == local(8, 30)  # not 08:14, before the brief gap
    assert row["quality_tier"] == "B"


def test_whole_trip_disappearing_is_not_an_arrival(warehouse):
    db, _ = warehouse
    for stop_id in ("A30-1", "A40-1"):
        assert event(db, "P_VANISH", stop_id)["exclusion_reason"] == "trip_left_feed"
    assert event(db, "P_VANISH", "A20-1")["is_eligible"] is True


def test_cancelled_trip_and_skipped_stop_are_excluded(warehouse):
    db, _ = warehouse
    reasons = {
        r["exclusion_reason"]
        for r in query(
            db, "SELECT exclusion_reason FROM observed_arrival_proxy WHERE trip_id = 'P_CANCEL'"
        )
    }
    assert reasons == {"cancelled_trip"}
    assert event(db, "P_SKIP", "A30-1")["exclusion_reason"] == "skipped_or_no_data_stop"
    assert event(db, "P_SKIP", "A40-1")["is_eligible"] is True


def test_ambiguous_repeated_stop_is_excluded(warehouse):
    db, _ = warehouse
    rows = query(
        db, "SELECT * FROM observed_arrival_proxy WHERE trip_id = 'P_SFO' AND stop_id = 'Y10-1'"
    )
    assert rows
    assert {r["exclusion_reason"] for r in rows} == {"ambiguous_repeated_stop"}
    assert event(db, "P_SFO", "W10-1")["is_eligible"] is True


def test_service_crossing_midnight_stays_one_event(warehouse):
    db, _ = warehouse
    row = event(db, "P_NIGHT", "A30-1")  # scheduled 24:05:00 on 2026-10-09
    assert row["is_eligible"] is True
    assert row["service_date"] == SERVICE_DAY
    assert row["first_seen_at"] < local(24, 0) < row["last_seen_at"]
    assert row["proxy_epoch"] == arrival("P_NIGHT", "A30-1")
    assert row["horizons_available"] == [300, 600, 900]


def test_unstable_final_estimate_is_excluded(warehouse):
    db, _ = warehouse
    row = event(db, "P_UNSTABLE", "A30-1")
    assert row["exclusion_reason"] == "unstable_final_estimate"
    assert row["final_estimate_spread_s"] == 120
    assert row["proxy_arrival"] is None
    assert event(db, "P_UNSTABLE", "A40-1")["is_eligible"] is True


def test_horizon_selection_is_deterministic_and_excludes_final_estimates(warehouse):
    db, _ = warehouse
    rows = query(
        db,
        "SELECT h.*, epoch(prediction_collected_at)::BIGINT AS collected_epoch "
        "FROM eta_revision_examples h WHERE event_id = ? ORDER BY target_horizon_s",
        [f"{SERVICE_DAY}:P_NORMAL:4"],
    )
    proxy = arrival("P_NORMAL", "A30-1")
    # Snapshots fall 30 s off each target (270 s and 330 s for 300 s): the tie goes to
    # the earlier snapshot, so every target picks target + 30 s.
    assert [(r["target_horizon_s"], r["time_to_proxy_s"]) for r in rows] == [
        (300, 330),
        (600, 630),
        (900, 930),
    ]
    for r in rows:
        assert r["collected_epoch"] == proxy - r["time_to_proxy_s"]
        assert r["observation_rank_from_end"] > ETARevisionConfig().stability_window
    # The simulated estimate is optimistic by horizon/15 seconds, so the ETA is later
    # revised later: positive revision relative to the final stable estimate.
    assert [
        (r["eta_revision_seconds"], r["absolute_eta_revision_seconds"], r["revision_direction"])
        for r in rows
    ] == [(22, 22, "revised_later"), (42, 42, "revised_later"), (60, 60, "revised_later")]
    assert all(
        r["final_stable_estimate"] - r["published_estimate"]
        == timedelta(seconds=r["eta_revision_seconds"])
        for r in rows
    )


def test_final_estimates_are_never_reused_as_horizon_predictions(warehouse):
    db, _ = warehouse
    row = event(db, "P_EARLY_DROP", "A30-1")
    # The last three observations are 330, 390 and 450 s before the proxy, so without
    # the rule the 330 s one would be chosen for the 5-minute target.
    assert row["listed_after_estimate_s"] == -330
    assert row["uncertainty_s"] == 330  # estimate and disappearance disagree by 330 s
    assert row["quality_tier"] == "B"
    assert 300 not in row["horizons_available"]
    examples = query(
        db, "SELECT * FROM eta_revision_examples WHERE event_id = ?", [row["event_id"]]
    )
    assert examples
    assert all(
        e["observation_rank_from_end"] > ETARevisionConfig().stability_window for e in examples
    )
    assert all(e["time_to_proxy_s"] > 450 for e in examples)


def test_collection_gap_excludes_events_spanning_it(tmp_path):
    trips = {"P_NORMAL": TRIPS["P_NORMAL"]}
    db, _ = build(tmp_path, snapshot_times(skip_local=[(local(8, 10), local(8, 12))]), trips)
    row = event(db, "P_NORMAL", "A30-1")
    assert row["exclusion_reason"] == "collection_gap"
    assert row["max_collection_gap_s"] == 240


def test_quality_checks_pass(warehouse):
    _, result = warehouse
    assert result.eta_revision["quality_checks"]
    assert all(v == 0 for v in result.eta_revision["quality_checks"].values())


def test_eta_revision_history_view_lists_every_estimate(warehouse):
    db, _ = warehouse
    row = event(db, "P_NORMAL", "A30-1")
    history = query(
        db,
        "SELECT * FROM eta_revision_history WHERE event_id = ? ORDER BY collected_at",
        [row["event_id"]],
    )
    assert len(history) == row["observation_count"]
    assert history[-1]["eta_revision_seconds"] == 0
    assert history[0]["time_to_proxy_s"] > 900


def test_rerun_is_idempotent(warehouse, tmp_path):
    db, _ = warehouse
    sql = "SELECT * FROM observed_arrival_proxy ORDER BY event_id"
    hsql = "SELECT * FROM eta_revision_examples ORDER BY event_id, target_horizon_s"
    first, first_h = query(db, sql), query(db, hsql)
    again, _ = build(tmp_path, snapshot_times())
    assert query(again, sql) == first
    assert query(again, hsql) == first_h
    assert len({r["event_id"] for r in first}) == len(first)


def test_report_counts_match_tables(warehouse):
    db, result = warehouse
    report = result.eta_revision
    (n,) = query(db, "SELECT count(*) AS n FROM observed_arrival_proxy_eligible")
    assert report["eligible_events"] == n["n"]
    assert sum(report["exclusions"].values()) + n["n"] == report["candidate_events"]


def test_config_is_recorded_and_changes_results(tmp_path):
    from bart_reliability.warehouse.build import build_warehouse as build_wh

    loose = ETARevisionConfig(stable_spread_s=130)
    raw = tmp_path / "raw" / "gtfs_rt"
    for t in snapshot_times():
        save_snapshot(raw, "trip_updates", t, snapshot(t))
    run_transform(raw, tmp_path / "processed")
    gtfs_zip = write_gtfs_zip(tmp_path / "gtfs" / "google_transit.zip", static_overrides())
    db = tmp_path / "w" / "bart.duckdb"
    build_wh(gtfs_zip, tmp_path / "processed", db, loose)
    stored = dict(
        (r["parameter"], r["value"]) for r in query(db, "SELECT * FROM eta_revision_config")
    )
    assert stored["stable_spread_s"] == "130"
    # With a 130 s stability limit the 120 s unstable estimate is accepted.
    assert event(db, "P_UNSTABLE", "A30-1")["is_eligible"] is True


def test_sensitivity_is_reproducible_and_leaves_warehouse_unchanged(warehouse):
    import hashlib

    from bart_reliability.warehouse.eta_revision_sensitivity import Scenario, run_sensitivity

    db, result = warehouse
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    scenarios = [
        Scenario("default", "default", {}),
        Scenario("stable_spread_s=130", "stable_spread_s", {"stable_spread_s": 130}),
        Scenario("persistence wide", "tier_a_persistence_s", {"tier_a_persistence_s": (-400, 300)}),
        Scenario("tolerance=30", "horizon_tolerance_s", {"horizon_tolerance_s": 30}),
    ]
    first = run_sensitivity(db, scenarios=scenarios)
    second = run_sensitivity(db, scenarios=scenarios)
    assert first == second
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before

    default, loose, wide, tight = first
    assert default["eligible_events"] == result.eta_revision["eligible_events"]
    assert default["tier_a_events"] == result.eta_revision["tier_a"]
    assert all(r["quality_check_failures"] == 0 for r in first)
    # One-at-a-time changes move only what they should.
    assert loose["eligible_events"] == default["eligible_events"] + 1  # P_UNSTABLE A30
    assert wide["eligible_events"] == default["eligible_events"]
    assert wide["tier_a_events"] == default["tier_a_events"] + 1  # P_EARLY_DROP A30
    assert tight["coverage_pct"] == default["coverage_pct"]  # targets are hit within 30 s


def test_default_sensitivity_grid():
    from bart_reliability.warehouse.eta_revision_sensitivity import default_scenarios

    names = [s.name for s in default_scenarios(ETARevisionConfig())]
    assert names == [
        "default",
        "max_collection_gap_s=75",
        "max_collection_gap_s=120",
        "stable_spread_s=30",
        "stable_spread_s=90",
        "horizon_tolerance_s=30",
        "horizon_tolerance_s=90",
        "tier_a_persistence_s=-30..60",
        "tier_a_persistence_s=-120..300",
    ]
