"""Flatten one trip-update FeedMessage into rows, one per stop-time update."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import PurePosixPath
from zoneinfo import ZoneInfo

import pyarrow as pa
from google.transit import gtfs_realtime_pb2

BART_TZ = ZoneInfo("America/Los_Angeles")
# Local times before this belong to the previous day's service.
SERVICE_DAY_CUTOFF = time(3, 0)

# <feed>/<YYYY-MM-DD>/<HHMMSS>Z.pb, as written by the collector's storage module.
_SNAPSHOT_NAME = re.compile(r"(?:^|/)(\d{4}-\d{2}-\d{2})/(\d{6})Z\.pb$")

_TRIP_REL = gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship
_STOP_REL = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.ScheduleRelationship

SCHEMA = pa.schema(
    [
        pa.field("feed_timestamp", pa.timestamp("s", tz="UTC"), nullable=False),
        pa.field("collected_at", pa.timestamp("s", tz="UTC"), nullable=False),
        pa.field("trip_id", pa.string(), nullable=False),
        pa.field("route_id", pa.string()),
        pa.field("direction_id", pa.int8()),
        pa.field("stop_id", pa.string(), nullable=False),
        pa.field("stop_sequence", pa.int32()),
        pa.field("predicted_arrival", pa.timestamp("s", tz="UTC")),
        pa.field("predicted_departure", pa.timestamp("s", tz="UTC")),
        pa.field("arrival_delay_s", pa.int32()),
        pa.field("departure_delay_s", pa.int32()),
        pa.field("arrival_uncertainty_s", pa.int32()),
        pa.field("trip_schedule_relationship", pa.string()),
        pa.field("stop_schedule_relationship", pa.string()),
        pa.field("prediction_horizon_seconds", pa.int64()),
        pa.field("inferred_service_date", pa.date32(), nullable=False),
        pa.field("source_file", pa.string(), nullable=False),
    ]
)


def parse_collected_at(source_file: str) -> datetime:
    """Recover the UTC collection time from a snapshot path like .../2026-10-09/224227Z.pb."""
    match = _SNAPSHOT_NAME.search(PurePosixPath(source_file).as_posix())
    if not match:
        raise ValueError(f"unrecognized snapshot filename: {source_file}")
    day, hms = match.groups()
    return datetime.strptime(f"{day} {hms}", "%Y-%m-%d %H%M%S").replace(tzinfo=UTC)


def infer_service_date(collected_at: datetime) -> date:
    """Provisional service date: Pacific local date, times before 03:00 go to the previous day.

    The definitive service date comes from the static GTFS join (trip -> service_id).
    """
    local = collected_at.astimezone(BART_TZ)
    if local.time() < SERVICE_DAY_CUTOFF:
        return local.date() - timedelta(days=1)
    return local.date()


@dataclass
class FlattenStats:
    rows: int = 0
    skipped_missing_key: int = 0
    duplicates_in_file: int = 0


@dataclass
class FlattenResult:
    rows: list[dict] = field(default_factory=list)
    stats: FlattenStats = field(default_factory=FlattenStats)


def flatten_feed(
    message: gtfs_realtime_pb2.FeedMessage, collected_at: datetime, source_file: str
) -> FlattenResult:
    """Return one row per stop-time update.

    Optional fields the feed omits become None rather than protobuf defaults.
    Rows without a trip_id or stop_id can't be keyed and are counted, not kept.
    """
    result = FlattenResult()
    feed_ts = message.header.timestamp
    collected_s = int(collected_at.timestamp())
    svc_date = infer_service_date(collected_at)
    seen: set[tuple[str, str]] = set()

    for entity in message.entity:
        if not entity.HasField("trip_update"):
            continue
        update = entity.trip_update
        trip = update.trip
        trip_id = trip.trip_id if trip.HasField("trip_id") else None
        trip_fields = {
            "route_id": trip.route_id if trip.HasField("route_id") else None,
            "direction_id": trip.direction_id if trip.HasField("direction_id") else None,
            "trip_schedule_relationship": (
                _TRIP_REL.Name(trip.schedule_relationship)
                if trip.HasField("schedule_relationship")
                else None
            ),
        }

        for stu in update.stop_time_update:
            stop_id = stu.stop_id if stu.HasField("stop_id") else None
            if not trip_id or not stop_id:
                result.stats.skipped_missing_key += 1
                continue
            if (trip_id, stop_id) in seen:
                result.stats.duplicates_in_file += 1
                continue
            seen.add((trip_id, stop_id))

            arrival = _event_time(stu, "arrival")
            result.rows.append(
                {
                    "feed_timestamp": feed_ts,
                    "collected_at": collected_s,
                    "trip_id": trip_id,
                    **trip_fields,
                    "stop_id": stop_id,
                    "stop_sequence": (stu.stop_sequence if stu.HasField("stop_sequence") else None),
                    "predicted_arrival": arrival,
                    "predicted_departure": _event_time(stu, "departure"),
                    "arrival_delay_s": _event_field(stu, "arrival", "delay"),
                    "departure_delay_s": _event_field(stu, "departure", "delay"),
                    "arrival_uncertainty_s": _event_field(stu, "arrival", "uncertainty"),
                    "stop_schedule_relationship": (
                        _STOP_REL.Name(stu.schedule_relationship)
                        if stu.HasField("schedule_relationship")
                        else None
                    ),
                    "prediction_horizon_seconds": (
                        arrival - collected_s if arrival is not None else None
                    ),
                    "inferred_service_date": svc_date,
                    "source_file": source_file,
                }
            )

    result.stats.rows = len(result.rows)
    return result


def rows_to_table(rows: list[dict]) -> pa.Table:
    return pa.Table.from_pylist(rows, schema=SCHEMA)


def _event_time(stu, event: str) -> int | None:
    return _event_field(stu, event, "time")


def _event_field(stu, event: str, name: str) -> int | None:
    if not stu.HasField(event):
        return None
    ev = getattr(stu, event)
    return getattr(ev, name) if ev.HasField(name) else None
