"""Command-line entry point: bart-transform."""

from __future__ import annotations

import argparse
import dataclasses
import logging
from pathlib import Path

from bart_reliability.collector.logging_setup import configure_logging
from bart_reliability.transform.alerts import run_alerts
from bart_reliability.transform.pipeline import run

logger = logging.getLogger(__name__)

DEFAULT_RAW_DIR = Path("data/raw/gtfs_rt")
DEFAULT_OUT_DIR = Path("data/processed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert raw GTFS-Realtime trip-update and alert snapshots into Parquet."
    )
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    configure_logging(None)
    logger.info(
        "transform_started",
        extra={"fields": {"raw_dir": str(args.raw_dir), "out_dir": str(args.out_dir)}},
    )
    summary = run(args.raw_dir, args.out_dir)
    fields = dataclasses.asdict(summary)
    fields.pop("quarantine")
    logger.info("transform_complete", extra={"fields": fields})
    alerts = dataclasses.asdict(run_alerts(args.raw_dir, args.out_dir))
    alerts.pop("quarantine")
    logger.info("alerts_transform_complete", extra={"fields": alerts})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
