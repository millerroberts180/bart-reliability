"""Multi-day synthetic BART-like feeds and warehouses for the modeling tests.

Service WKDY (gtfs_fixtures) runs Mon-Fri in October 2026 except Mon 10-12, so the four
service days Tue 10-06 to Fri 10-09 all run it (PDT, UTC-7). Each trip gains delay
steadily along its route. Like BART, each estimate assumes the delay so far persists,
so ETAs are revised later as a delayed train approaches: the farther out, the larger
the revision. Every stop stays listed until 20 s after the train reaches it, and the
trip's final stop is never published.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from google.transit import gtfs_realtime_pb2
from gtfs_fixtures import write_gtfs_zip

from bart_reliability.collector.storage import save_snapshot
from bart_reliability.modeling.config import ModelConfig, TreeConfig, load_model_config
from bart_reliability.transform.alerts import run_alerts
from bart_reliability.transform.pipeline import run as run_transform
from bart_reliability.warehouse.build import build_warehouse

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config" / "eta_model.toml"
DAYS = [date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)]
STOPS = ["A10-1", "A20-1", "A30-1", "A40-1", "A50-1", "A60-1"]
SEQUENCES = [1, 3, 4, 6, 7, 8]
STOP_SPACING = timedelta(minutes=10)
TRIP_DURATION_S = STOP_SPACING.total_seconds() * (len(STOPS) - 1)
PERSIST_S = 20
# trip_id -> (route_id, departure (h, m) local)
TRIPS = {
    "T1": ("1", (7, 40)),
    "T2": ("07", (7, 50)),
    "T3": ("1", (8, 0)),
    "T4": ("07", (8, 10)),
    "T5": ("1", (8, 20)),
    "T6": ("07", (8, 30)),
}
DELAYS_S = [0, 60, 120, 240, 360, 480]
# Snapshot window each day (local time).
FIRST_SNAPSHOT, LAST_SNAPSHOT = (7, 0), (9, 40)
ALERT_DAY, ALERT_FROM = DAYS[2], (8, 15)  # one system-wide alert appears here


def local(day: date, h: int, m: int, s: int = 0) -> datetime:
    """Pacific local time on `day` as UTC (October 2026 is PDT)."""
    return datetime(day.year, day.month, day.day, 7, tzinfo=UTC) + timedelta(
        hours=h, minutes=m, seconds=s
    )


def final_delay_s(day: date, trip_id: str) -> int:
    return DELAYS_S[(DAYS.index(day) * 5 + list(TRIPS).index(trip_id) * 2) % len(DELAYS_S)]


def scheduled(day: date, trip_id: str, k: int) -> datetime:
    return local(day, *TRIPS[trip_id][1]) + k * STOP_SPACING


def delay_so_far(day, trip_id, now) -> float:
    elapsed = (now - local(day, *TRIPS[trip_id][1])).total_seconds()
    return final_delay_s(day, trip_id) * min(max(elapsed / TRIP_DURATION_S, 0.0), 1.0)


def arrival(day, trip_id, k) -> datetime:
    return scheduled(day, trip_id, k) + timedelta(
        seconds=final_delay_s(day, trip_id) * k / (len(STOPS) - 1)
    )


def estimate(day, trip_id, k, now, perturb=None) -> datetime:
    """BART-like ETA: schedule plus the delay accumulated so far, to the second."""
    eta = scheduled(day, trip_id, k) + timedelta(seconds=round(delay_so_far(day, trip_id, now)))
    if perturb:
        eta += timedelta(seconds=perturb(day, trip_id, k, now))
    return eta


def snapshot(day: date, now: datetime, perturb=None) -> bytes:
    message = gtfs_realtime_pb2.FeedMessage()
    message.header.gtfs_realtime_version = "1.0"
    message.header.timestamp = int(now.timestamp())
    for trip_id in TRIPS:
        if now < scheduled(day, trip_id, 0) - timedelta(minutes=30):
            continue
        listed = []
        for k, stop_id in enumerate(STOPS[:-1]):  # final stop is never published
            eta = estimate(day, trip_id, k, now, perturb)
            passed = max(arrival(day, trip_id, k), eta) + timedelta(seconds=PERSIST_S)
            if now < passed:
                listed.append((stop_id, eta))
        if not listed:
            continue
        entity = message.entity.add(id=trip_id)
        entity.trip_update.trip.trip_id = trip_id
        for stop_id, eta in listed:
            stu = entity.trip_update.stop_time_update.add(stop_id=stop_id)
            stu.arrival.time = int(eta.timestamp())
    return message.SerializeToString()


def alert_snapshot(now: datetime) -> bytes:
    message = gtfs_realtime_pb2.FeedMessage()
    message.header.gtfs_realtime_version = "1.0"
    message.header.timestamp = int(now.timestamp())
    if now >= local(ALERT_DAY, *ALERT_FROM) and now.date() == ALERT_DAY:
        alert = message.entity.add(id="BSA_TEST").alert
        alert.header_text.translation.add(text="Delays systemwide", language="en")
        alert.informed_entity.add(agency_id="BART")
    return message.SerializeToString()


def snapshot_times(day: date) -> list[datetime]:
    t, end, out = local(day, *FIRST_SNAPSHOT), local(day, *LAST_SNAPSHOT), []
    while t <= end:
        out.append(t)
        t += timedelta(minutes=1)
    return out


def static_overrides() -> dict:
    stops = [["stop_id", "stop_name", "stop_lat", "stop_lon", "location_type", "parent_station"]]
    stops += [[s, s, "37.7", "-122.4", "0", s[:3]] for s in STOPS]
    trips = [["route_id", "service_id", "trip_id", "trip_headsign", "direction_id"]]
    stop_times = [["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]]
    for trip_id, (route_id, (h, m)) in TRIPS.items():
        trips.append([route_id, "WKDY", trip_id, "Somewhere", "0"])
        for k, (stop_id, seq) in enumerate(zip(STOPS, SEQUENCES, strict=True)):
            minutes = h * 60 + m + 10 * k
            t = f"{minutes // 60:02d}:{minutes % 60:02d}:00"
            stop_times.append([trip_id, t, t, stop_id, str(seq)])
    return {"stops.txt": stops, "trips.txt": trips, "stop_times.txt": stop_times}


def build_synthetic_warehouse(root: Path, perturb=None) -> Path:
    raw = root / "raw" / "gtfs_rt"
    for day in DAYS:
        for now in snapshot_times(day):
            save_snapshot(raw, "trip_updates", now, snapshot(day, now, perturb))
            save_snapshot(raw, "alerts", now, alert_snapshot(now))
    processed = root / "processed"
    run_transform(raw, processed)
    run_alerts(raw, processed)
    gtfs_zip = write_gtfs_zip(root / "gtfs" / "google_transit.zip", static_overrides())
    db = root / "warehouse" / "bart.duckdb"
    build_warehouse(gtfs_zip, processed, db)
    return db


def synthetic_config(out_dir: Path, **overrides) -> ModelConfig:
    """The repository config, scaled to the tiny synthetic sample."""
    cfg = load_model_config(REPO_CONFIG)
    return replace(
        cfg,
        output_dir=out_dir,
        split={
            "train": (DAYS[0], DAYS[1]),
            "validation": (DAYS[2], DAYS[2]),
            "test": (DAYS[3], DAYS[3]),
        },
        baseline_min_group_size=3,
        # Each bucket x route x stop group has 6 training rows, bucket x route 18 and
        # bucket 36, so these sizes reach every fallback level.
        baseline_sensitivity_min_group_sizes=(3, 6, 12, 40),
        bootstrap_replicates=300,
        tree=TreeConfig(
            max_leaf_nodes=(4, 8),
            learning_rate=0.1,
            max_iter=20,
            min_samples_leaf=5,
            l2_regularization=0.0,
        ),
        **overrides,
    )
