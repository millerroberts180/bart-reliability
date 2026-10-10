import json
import logging
from datetime import UTC, datetime

import requests
import responses
from conftest import ALERTS_URL, TRIP_URL

from bart_reliability.collector.logging_setup import JsonFormatter
from bart_reliability.collector.main import run_cycle, run_forever

COLLECTED_AT = datetime(2026, 10, 9, 21, 15, 0, tzinfo=UTC)


def cycle(config):
    with requests.Session() as session:
        return run_cycle(session, config, now=lambda: COLLECTED_AT, sleep=lambda s: None)


@responses.activate
def test_cycle_saves_both_feeds(config, trip_update_bytes, empty_alerts_bytes):
    responses.get(TRIP_URL, body=trip_update_bytes)
    responses.get(ALERTS_URL, body=empty_alerts_bytes)
    assert cycle(config) == {"trip_updates": True, "alerts": True}
    day = config.output_dir / "trip_updates" / "2026-10-09"
    assert (day / "211500Z.pb").read_bytes() == trip_update_bytes
    assert (config.output_dir / "alerts" / "2026-10-09" / "211500Z.pb").exists()


@responses.activate
def test_one_feed_failing_does_not_block_the_other(config, empty_alerts_bytes):
    responses.get(TRIP_URL, status=404)
    responses.get(ALERTS_URL, body=empty_alerts_bytes)
    assert cycle(config) == {"trip_updates": False, "alerts": True}
    assert not (config.output_dir / "trip_updates").exists()


@responses.activate
def test_invalid_response_is_never_stored(config, empty_alerts_bytes):
    responses.get(TRIP_URL, body=b"<html>maintenance</html>")
    responses.get(ALERTS_URL, body=empty_alerts_bytes)
    assert cycle(config)["trip_updates"] is False
    assert not (config.output_dir / "trip_updates").exists()


@responses.activate
def test_existing_snapshot_is_kept_and_logged(config, trip_update_bytes, caplog):
    responses.get(TRIP_URL, body=trip_update_bytes)
    responses.get(ALERTS_URL, body=trip_update_bytes)
    cycle(config)
    with caplog.at_level(logging.ERROR):
        assert cycle(config) == {"trip_updates": False, "alerts": False}
    assert [r.getMessage() for r in caplog.records] == ["snapshot_exists", "snapshot_exists"]
    assert str(caplog.records[0].fields["path"]).endswith("211500Z.pb")


@responses.activate
def test_failure_log_is_structured_json(config, empty_alerts_bytes, caplog):
    responses.get(TRIP_URL, status=404)
    responses.get(ALERTS_URL, body=empty_alerts_bytes)
    with caplog.at_level(logging.INFO):
        cycle(config)
    failed = next(r for r in caplog.records if r.getMessage() == "feed_failed")
    entry = json.loads(JsonFormatter().format(failed))
    assert entry["event"] == "feed_failed"
    assert entry["feed"] == "trip_updates"
    assert entry["reason"] == "http 404"
    assert entry["attempts"] == 1


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_schedule_is_fixed_rate_not_drifting(config):
    clock = FakeClock()
    starts = []

    def slow_cycle():
        starts.append(clock.now)
        clock.now += 7  # each cycle takes 7 seconds of work
        return {}

    run_forever(config, slow_cycle, clock.monotonic, clock.sleep, max_cycles=4)
    assert starts == [0, 60, 120, 180]


def test_overrun_skips_missed_ticks_and_logs(config, caplog):
    clock = FakeClock()
    starts = []
    durations = iter([130, 1, 1])

    def cycle_fn():
        starts.append(clock.now)
        clock.now += next(durations)
        return {}

    with caplog.at_level(logging.WARNING):
        run_forever(config, cycle_fn, clock.monotonic, clock.sleep, max_cycles=3)
    # The first cycle ran past the 60s and 120s ticks, so the next one starts at 180s.
    assert starts == [0, 180, 240]
    missed = [r for r in caplog.records if r.getMessage() == "intervals_missed"]
    assert missed[0].fields["missed"] == 2
