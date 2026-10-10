"""Shared fixtures: feed bytes are built with the official bindings, never downloaded."""

from __future__ import annotations

from pathlib import Path

import pytest
from google.transit import gtfs_realtime_pb2

from bart_reliability.collector.config import (
    CollectorConfig,
    FeedConfig,
    RetryConfig,
)

FEED_TIMESTAMP = 1_791_585_582
TRIP_URL = "https://example.test/gtfsrt/tripupdate.aspx"
ALERTS_URL = "https://example.test/gtfsrt/alerts.aspx"


def build_feed(entities: int = 0, timestamp: int = FEED_TIMESTAMP) -> bytes:
    message = gtfs_realtime_pb2.FeedMessage()
    message.header.gtfs_realtime_version = "1.0"
    message.header.timestamp = timestamp
    for i in range(entities):
        entity = message.entity.add()
        entity.id = f"trip-{i}"
        entity.trip_update.trip.trip_id = f"trip-{i}"
        update = entity.trip_update.stop_time_update.add()
        update.stop_id = "EMBR"
        update.arrival.time = timestamp + 600
    return message.SerializeToString()


@pytest.fixture
def trip_update_bytes() -> bytes:
    return build_feed(entities=3)


@pytest.fixture
def empty_alerts_bytes() -> bytes:
    return build_feed(entities=0)


@pytest.fixture
def config(tmp_path: Path) -> CollectorConfig:
    return CollectorConfig(
        interval_seconds=60,
        output_dir=tmp_path / "gtfs_rt",
        log_file=None,
        retry=RetryConfig(
            timeout_seconds=2.0,
            max_attempts=3,
            backoff_initial_seconds=1.0,
            backoff_max_seconds=4.0,
        ),
        feeds=(
            FeedConfig(name="trip_updates", url=TRIP_URL),
            FeedConfig(name="alerts", url=ALERTS_URL),
        ),
    )
