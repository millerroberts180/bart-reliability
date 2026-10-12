"""Normalize GTFS-Realtime service-alert snapshots into Parquet.

Outputs, under the processed root:

    alert_snapshots/date=/hour=/part.parquet       one row per alert snapshot, empty feeds too
    alert_observations/date=/hour=/part.parquet    one row per (snapshot, alert entity)
    alert_versions/part.parquet                    one row per distinct alert content
    alert_active_periods/part.parquet              one row per (content, active period)
    alert_informed_entities/part.parquet           one row per (content, informed entity)
    alert_snapshots/_quarantine.jsonl              snapshots that could not be processed

Alert content is keyed by `alert_fingerprint`: the SHA-256 of the alert message as
canonical JSON. An entity whose content changes gets a new fingerprint while keeping its
entity ID, so versions are (entity_id, alert_fingerprint). Periods and informed entities
hang off the fingerprint, never off snapshots, so there is no snapshot x period x entity
cross product.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
from google.protobuf.json_format import MessageToJson
from google.transit import gtfs_realtime_pb2

from bart_reliability.collector.validate import ValidationError, validate_feed
from bart_reliability.transform.pipeline import (
    PART_FILE,
    QUARANTINE_FILE,
    _dedupe_by_feed_timestamp,
    _load_header,
    _write_parquet_atomic,
    _write_quarantine,
    discover,
)

logger = logging.getLogger(__name__)

ALERT_FEED_DIR = "alerts"
SNAPSHOT_DIR = "alert_snapshots"
OBSERVATION_DIR = "alert_observations"
VERSIONS_DIR = "alert_versions"
PERIODS_DIR = "alert_active_periods"
ENTITIES_DIR = "alert_informed_entities"
PREFERRED_LANGUAGES = ("en", "en-US", "en-us")

_TS = pa.timestamp("s", tz="UTC")
_TRANSLATIONS = pa.list_(pa.struct([("language", pa.string()), ("text", pa.string())]))

SNAPSHOT_SCHEMA = pa.schema(
    [
        pa.field("feed_timestamp", _TS, nullable=False),
        pa.field("collected_at", _TS, nullable=False),
        pa.field("source_file", pa.string(), nullable=False),
        pa.field("entity_count", pa.int32(), nullable=False),
        pa.field("alert_count", pa.int32(), nullable=False),
    ]
)
OBSERVATION_SCHEMA = pa.schema(
    [
        pa.field("feed_timestamp", _TS, nullable=False),
        pa.field("collected_at", _TS, nullable=False),
        pa.field("source_file", pa.string(), nullable=False),
        pa.field("entity_id", pa.string(), nullable=False),
        pa.field("alert_fingerprint", pa.string(), nullable=False),
    ]
)
VERSION_SCHEMA = pa.schema(
    [
        pa.field("alert_fingerprint", pa.string(), nullable=False),
        pa.field("cause", pa.string()),
        pa.field("effect", pa.string()),
        pa.field("severity_level", pa.string()),
        pa.field("header_text", pa.string()),
        pa.field("description_text", pa.string()),
        pa.field("url", pa.string()),
        pa.field("header_translations", _TRANSLATIONS),
        pa.field("description_translations", _TRANSLATIONS),
        pa.field("url_translations", _TRANSLATIONS),
        pa.field("active_period_count", pa.int32(), nullable=False),
        pa.field("informed_entity_count", pa.int32(), nullable=False),
        pa.field("alert_json", pa.string(), nullable=False),
    ]
)
PERIOD_SCHEMA = pa.schema(
    [
        pa.field("alert_fingerprint", pa.string(), nullable=False),
        pa.field("period_index", pa.int32(), nullable=False),
        pa.field("active_start", _TS),  # null: open start
        pa.field("active_end", _TS),  # null: open end ("until further notice")
    ]
)
ENTITY_SCHEMA = pa.schema(
    [
        pa.field("alert_fingerprint", pa.string(), nullable=False),
        pa.field("entity_index", pa.int32(), nullable=False),
        pa.field("agency_id", pa.string()),
        pa.field("route_id", pa.string()),
        pa.field("route_type", pa.int32()),
        pa.field("direction_id", pa.int32()),
        pa.field("trip_id", pa.string()),
        pa.field("trip_route_id", pa.string()),
        pa.field("stop_id", pa.string()),
    ]
)


@dataclass
class AlertSummary:
    files_found: int = 0
    files_used: int = 0
    files_duplicate_feed: int = 0
    files_quarantined: int = 0
    empty_snapshots: int = 0
    observations: int = 0
    versions: int = 0
    non_alert_entities_skipped: int = 0
    deleted_entities_skipped: int = 0
    duplicate_entity_ids_skipped: int = 0
    quarantine: list[dict] = field(default_factory=list)


def alert_fingerprint(alert: gtfs_realtime_pb2.Alert) -> tuple[str, str]:
    """(sha256 hex, canonical JSON) of an alert's content. Stable across runs/versions."""
    canonical = MessageToJson(alert, preserving_proto_field_name=True, sort_keys=True, indent=None)
    return hashlib.sha256(canonical.encode()).hexdigest(), canonical


def _translations(ts: gtfs_realtime_pb2.TranslatedString) -> list[dict]:
    return [
        {"language": t.language if t.HasField("language") else None, "text": t.text}
        for t in ts.translation
    ]


def _preferred(translations: list[dict]) -> str | None:
    for language in PREFERRED_LANGUAGES:
        for t in translations:
            if t["language"] == language:
                return t["text"]
    return translations[0]["text"] if translations else None


def _enum(alert, field_name, enum) -> str | None:
    return enum.Name(getattr(alert, field_name)) if alert.HasField(field_name) else None


def flatten_alert(alert: gtfs_realtime_pb2.Alert) -> tuple[dict, list[dict], list[dict]]:
    """Return (version row, active-period rows, informed-entity rows) for one alert."""
    fingerprint, canonical = alert_fingerprint(alert)
    header = _translations(alert.header_text)
    description = _translations(alert.description_text)
    url = _translations(alert.url)
    version = {
        "alert_fingerprint": fingerprint,
        "cause": _enum(alert, "cause", gtfs_realtime_pb2.Alert.Cause),
        "effect": _enum(alert, "effect", gtfs_realtime_pb2.Alert.Effect),
        "severity_level": _enum(alert, "severity_level", gtfs_realtime_pb2.Alert.SeverityLevel),
        "header_text": _preferred(header),
        "description_text": _preferred(description),
        "url": _preferred(url),
        "header_translations": header,
        "description_translations": description,
        "url_translations": url,
        "active_period_count": len(alert.active_period),
        "informed_entity_count": len(alert.informed_entity),
        "alert_json": canonical,
    }
    periods = [
        {
            "alert_fingerprint": fingerprint,
            "period_index": i,
            "active_start": p.start if p.HasField("start") and p.start else None,
            "active_end": p.end if p.HasField("end") and p.end else None,
        }
        for i, p in enumerate(alert.active_period)
    ]
    entities = []
    for i, e in enumerate(alert.informed_entity):
        trip = e.trip if e.HasField("trip") else None
        entities.append(
            {
                "alert_fingerprint": fingerprint,
                "entity_index": i,
                "agency_id": e.agency_id if e.HasField("agency_id") else None,
                "route_id": e.route_id if e.HasField("route_id") else None,
                "route_type": e.route_type if e.HasField("route_type") else None,
                "direction_id": e.direction_id if e.HasField("direction_id") else None,
                "trip_id": trip.trip_id if trip and trip.HasField("trip_id") else None,
                "trip_route_id": trip.route_id if trip and trip.HasField("route_id") else None,
                "stop_id": e.stop_id if e.HasField("stop_id") else None,
            }
        )
    return version, periods, entities


def run_alerts(raw_dir: Path, out_dir: Path) -> AlertSummary:
    """Process every alert snapshot under raw_dir/alerts into out_dir. Safe to rerun."""
    summary = AlertSummary()
    paths = discover(raw_dir, ALERT_FEED_DIR)
    summary.files_found = len(paths)
    snapshots = []
    for path in paths:
        source_file = path.relative_to(raw_dir).as_posix()
        try:
            snapshots.append(_load_header(path, source_file))
        except (OSError, ValueError) as e:
            summary.quarantine.append({"source_file": source_file, "reason": str(e)})
    kept = _dedupe_by_feed_timestamp(snapshots)
    summary.files_used = len(kept)
    summary.files_duplicate_feed = len(snapshots) - len(kept)

    versions: dict[str, dict] = {}
    periods: dict[str, list[dict]] = {}
    entities: dict[str, list[dict]] = {}
    by_hour: dict[tuple[str, str], list] = defaultdict(list)
    for snap in kept:
        by_hour[(snap.collected_at.strftime("%Y-%m-%d"), snap.collected_at.strftime("%H"))].append(
            snap
        )

    for (day, hour), hour_snaps in sorted(by_hour.items()):
        manifest, observations = [], []
        for snap in hour_snaps:
            try:
                message = validate_feed(snap.path.read_bytes())
            except (OSError, ValidationError) as e:
                summary.quarantine.append({"source_file": snap.source_file, "reason": str(e)})
                summary.files_used -= 1
                continue
            alert_count = 0
            seen_ids: set[str] = set()
            for entity in message.entity:
                if entity.HasField("is_deleted") and entity.is_deleted:
                    summary.deleted_entities_skipped += 1
                    continue
                if not entity.HasField("alert"):
                    summary.non_alert_entities_skipped += 1
                    continue
                if entity.id in seen_ids:
                    summary.duplicate_entity_ids_skipped += 1  # keep the first
                    continue
                seen_ids.add(entity.id)
                version, version_periods, version_entities = flatten_alert(entity.alert)
                fp = version["alert_fingerprint"]
                versions.setdefault(fp, version)
                periods.setdefault(fp, version_periods)
                entities.setdefault(fp, version_entities)
                observations.append(
                    {
                        "feed_timestamp": message.header.timestamp,
                        "collected_at": int(snap.collected_at.timestamp()),
                        "source_file": snap.source_file,
                        "entity_id": entity.id,
                        "alert_fingerprint": fp,
                    }
                )
                alert_count += 1
            manifest.append(
                {
                    "feed_timestamp": message.header.timestamp,
                    "collected_at": int(snap.collected_at.timestamp()),
                    "source_file": snap.source_file,
                    "entity_count": len(message.entity),
                    "alert_count": alert_count,
                }
            )
            summary.empty_snapshots += alert_count == 0
        partition = f"date={day}/hour={hour}"
        _write_parquet_atomic(
            pa.Table.from_pylist(manifest, schema=SNAPSHOT_SCHEMA),
            out_dir / SNAPSHOT_DIR / partition / PART_FILE,
        )
        _write_parquet_atomic(
            pa.Table.from_pylist(observations, schema=OBSERVATION_SCHEMA),
            out_dir / OBSERVATION_DIR / partition / PART_FILE,
        )
        summary.observations += len(observations)

    order = sorted(versions)
    _write_parquet_atomic(
        pa.Table.from_pylist([versions[f] for f in order], schema=VERSION_SCHEMA),
        out_dir / VERSIONS_DIR / PART_FILE,
    )
    _write_parquet_atomic(
        pa.Table.from_pylist([p for f in order for p in periods[f]], schema=PERIOD_SCHEMA),
        out_dir / PERIODS_DIR / PART_FILE,
    )
    _write_parquet_atomic(
        pa.Table.from_pylist([e for f in order for e in entities[f]], schema=ENTITY_SCHEMA),
        out_dir / ENTITIES_DIR / PART_FILE,
    )
    summary.versions = len(versions)
    summary.files_quarantined = len(summary.quarantine)
    _write_quarantine(out_dir / SNAPSHOT_DIR / QUARANTINE_FILE, summary.quarantine)
    for entry in summary.quarantine:
        logger.warning("alert_snapshot_quarantined", extra={"fields": entry})
    return summary
