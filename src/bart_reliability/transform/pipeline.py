"""Rebuild hourly Parquet partitions from raw trip-update snapshots."""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pyarrow.parquet as pq

from bart_reliability.collector.validate import ValidationError, validate_feed
from bart_reliability.transform.flatten import (
    flatten_feed,
    parse_collected_at,
    rows_to_table,
)

logger = logging.getLogger(__name__)

FEED_DIR = "trip_updates"
QUARANTINE_FILE = "_quarantine.jsonl"
PART_FILE = "part.parquet"


@dataclass(frozen=True)
class Snapshot:
    path: Path
    source_file: str  # relative to the raw root, e.g. trip_updates/2026-10-09/224227Z.pb
    collected_at: datetime
    feed_timestamp: int


@dataclass
class Summary:
    files_found: int = 0
    files_used: int = 0
    files_duplicate_feed: int = 0
    files_quarantined: int = 0
    rows_written: int = 0
    rows_skipped_missing_key: int = 0
    rows_duplicate_in_file: int = 0
    partitions_written: int = 0
    quarantine: list[dict] = field(default_factory=list)


def run(raw_dir: Path, out_dir: Path) -> Summary:
    """Process every trip-update snapshot under raw_dir into out_dir.

    Safe to rerun: each hour partition is rebuilt from scratch and atomically
    replaced, so the same inputs always produce the same output.
    """
    summary = Summary()
    paths = discover(raw_dir)
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

    by_hour: dict[tuple[str, str], list[Snapshot]] = defaultdict(list)
    for snap in kept:
        key = (snap.collected_at.strftime("%Y-%m-%d"), snap.collected_at.strftime("%H"))
        by_hour[key].append(snap)

    for (day, hour), hour_snaps in sorted(by_hour.items()):
        rows = []
        for snap in hour_snaps:
            # Re-read here so only one hour of rows is in memory at a time.
            try:
                message = validate_feed(snap.path.read_bytes())
            except (OSError, ValidationError) as e:
                summary.quarantine.append({"source_file": snap.source_file, "reason": str(e)})
                summary.files_used -= 1
                continue
            result = flatten_feed(message, snap.collected_at, snap.source_file)
            rows.extend(result.rows)
            summary.rows_skipped_missing_key += result.stats.skipped_missing_key
            summary.rows_duplicate_in_file += result.stats.duplicates_in_file
        partition = out_dir / FEED_DIR / f"date={day}" / f"hour={hour}"
        _write_parquet_atomic(rows_to_table(rows), partition / PART_FILE)
        summary.rows_written += len(rows)
        summary.partitions_written += 1

    summary.files_quarantined = len(summary.quarantine)
    _write_quarantine(out_dir / FEED_DIR / QUARANTINE_FILE, summary.quarantine)
    for entry in summary.quarantine:
        logger.warning("snapshot_quarantined", extra={"fields": entry})
    return summary


def discover(raw_dir: Path) -> list[Path]:
    """All trip-update snapshots, skipping the collector's hidden temp files."""
    root = raw_dir / FEED_DIR
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.pb") if not p.name.startswith("."))


def _load_header(path: Path, source_file: str) -> Snapshot:
    collected_at = parse_collected_at(source_file)
    try:
        message = validate_feed(path.read_bytes())
    except ValidationError as e:
        raise ValueError(f"invalid feed: {e}") from e
    return Snapshot(path, source_file, collected_at, message.header.timestamp)


def _dedupe_by_feed_timestamp(snapshots: list[Snapshot]) -> list[Snapshot]:
    """Keep the earliest-collected snapshot for each feed timestamp."""
    earliest: dict[int, Snapshot] = {}
    for snap in sorted(snapshots, key=lambda s: (s.collected_at, s.source_file)):
        earliest.setdefault(snap.feed_timestamp, snap)
    return sorted(earliest.values(), key=lambda s: (s.collected_at, s.source_file))


def _write_parquet_atomic(table, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, path)


def _write_quarantine(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for entry in sorted(entries, key=lambda e: e["source_file"]):
            f.write(json.dumps(entry) + "\n")
    os.replace(tmp, path)
