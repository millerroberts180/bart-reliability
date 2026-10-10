"""Run the collector: one cycle per interval, each feed handled independently."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import requests

from bart_reliability.collector.config import CollectorConfig, ConfigError, load_config
from bart_reliability.collector.fetch import FetchError, fetch_valid_feed
from bart_reliability.collector.logging_setup import configure_logging
from bart_reliability.collector.storage import save_snapshot

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = Path("config/collector.toml")
USER_AGENT = "bart-reliability-lab/0.1 (research collector)"


def utc_now() -> datetime:
    return datetime.now(UTC)


def run_cycle(
    session: requests.Session,
    config: CollectorConfig,
    now: Callable[[], datetime] = utc_now,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, bool]:
    """Fetch, validate, and store every feed once. Returns {feed_name: saved}.

    A failure in one feed is logged and never prevents the others from running.
    """
    results: dict[str, bool] = {}
    for feed in config.feeds:
        fields: dict = {"feed": feed.name}
        try:
            result = fetch_valid_feed(session, feed, config.retry, sleep=sleep)
            collected_at = now()
            path = save_snapshot(config.output_dir, feed.name, collected_at, result.content)
        except FetchError as e:
            fields.update(reason=e.reason, attempts=e.attempts, retryable=e.retryable)
            logger.error("feed_failed", extra={"fields": fields})
            results[feed.name] = False
        except FileExistsError as e:
            # os.link reports (source, destination); the destination is the clash.
            fields.update(path=e.filename2 or e.filename)
            logger.error("snapshot_exists", extra={"fields": fields})
            results[feed.name] = False
        except OSError as e:
            fields.update(reason=str(e))
            logger.error("storage_failed", extra={"fields": fields})
            results[feed.name] = False
        except Exception:
            # Last resort so one unexpected bug can't stop a 24-hour run.
            logger.exception("unexpected_error", extra={"fields": fields})
            results[feed.name] = False
        else:
            fields.update(
                path=str(path),
                bytes=len(result.content),
                attempts=result.attempts,
                collected_at=collected_at.isoformat(),
                feed_timestamp=result.message.header.timestamp,
                entities=len(result.message.entity),
            )
            logger.info("snapshot_saved", extra={"fields": fields})
            results[feed.name] = True
    return results


def run_forever(
    config: CollectorConfig,
    cycle: Callable[[], dict[str, bool]],
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    max_cycles: int | None = None,
) -> None:
    """Call cycle() on a fixed-rate schedule.

    Ticks are computed from the start time, not from when the last cycle ended,
    so slow cycles don't push the schedule later. If a cycle overruns one or
    more ticks, the missed ticks are logged and skipped rather than run late.
    """
    interval = config.interval_seconds
    next_tick = monotonic()
    count = 0
    while max_cycles is None or count < max_cycles:
        results = cycle()
        count += 1
        logger.info(
            "cycle_complete",
            extra={"fields": {"cycle": count, "saved": sum(results.values()), "feeds": results}},
        )
        if max_cycles is not None and count >= max_cycles:
            break

        next_tick += interval
        delay = next_tick - monotonic()
        if delay < 0:
            missed = int(-delay // interval) + 1
            logger.warning(
                "intervals_missed",
                extra={"fields": {"missed": missed, "overrun_seconds": round(-delay, 3)}},
            )
            next_tick += missed * interval
            delay = next_tick - monotonic()
        sleep(delay)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect BART GTFS-Realtime snapshots.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="path to TOML config")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as e:
        configure_logging(None)
        logger.error("config_invalid", extra={"fields": {"reason": str(e)}})
        return 2

    configure_logging(config.log_file)
    logger.info(
        "collector_started",
        extra={
            "fields": {
                "config": str(args.config),
                "interval_seconds": config.interval_seconds,
                "feeds": [feed.name for feed in config.feeds],
                "output_dir": str(config.output_dir),
            }
        },
    )

    with requests.Session() as session:
        session.headers["User-Agent"] = USER_AGENT
        try:
            run_forever(
                config,
                cycle=lambda: run_cycle(session, config),
                max_cycles=1 if args.once else None,
            )
        except KeyboardInterrupt:
            logger.info("collector_stopped", extra={"fields": {"reason": "keyboard interrupt"}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
