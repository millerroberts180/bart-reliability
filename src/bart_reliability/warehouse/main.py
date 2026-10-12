"""Command-line entry point: bart-build-warehouse."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from bart_reliability.collector.logging_setup import configure_logging
from bart_reliability.warehouse.build import build_warehouse
from bart_reliability.warehouse.eta_revision_config import (
    DEFAULT_CONFIG_PATH,
    ETARevisionConfigError,
    load_eta_revision_config,
)
from bart_reliability.warehouse.static_gtfs import StaticGTFSError

logger = logging.getLogger(__name__)

STATIC_ROOT = Path("data/raw/gtfs_static")
DEFAULT_PROCESSED_DIR = Path("data/processed")
DEFAULT_DB = Path("data/warehouse/bart.duckdb")


def latest_archive(root: Path = STATIC_ROOT) -> Path:
    """Newest data/raw/gtfs_static/<date>/google_transit.zip (dated folders sort by name)."""
    archives = sorted(root.glob("*/google_transit.zip"))
    if not archives:
        raise StaticGTFSError(f"no static GTFS archive found under {root}/<date>/")
    return archives[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load static GTFS and processed trip updates into DuckDB."
    )
    parser.add_argument(
        "--gtfs-zip", type=Path, help="static GTFS ZIP (default: newest dated archive)"
    )
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--eta-revision-config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="ETA revision dataset parameters (TOML)",
    )
    args = parser.parse_args(argv)

    configure_logging(None)
    try:
        gtfs_zip = args.gtfs_zip or latest_archive()
        logger.info(
            "warehouse_build_started",
            extra={"fields": {"gtfs_zip": str(gtfs_zip), "db": str(args.db)}},
        )
        eta_config = load_eta_revision_config(args.eta_revision_config)
        result = build_warehouse(gtfs_zip, args.processed_dir, args.db, eta_config)
    except StaticGTFSError as e:
        logger.error("static_gtfs_invalid", extra={"fields": {"reason": str(e)}})
        return 2
    except ETARevisionConfigError as e:
        logger.error("eta_revision_config_invalid", extra={"fields": {"reason": str(e)}})
        return 2

    for warning in result.static.warnings:
        logger.warning("static_gtfs_issue", extra={"fields": {"issue": warning}})
    logger.info("static_gtfs_provenance", extra={"fields": result.static.provenance})
    logger.info(
        "warehouse_build_complete",
        extra={
            "fields": {
                "db": str(result.db_path),
                "archive_sha256": result.static.archive_sha256,
                "static_row_counts": result.static.row_counts,
                "parquet_files": result.parquet_files,
            }
        },
    )
    logger.info("join_quality", extra={"fields": result.quality})
    logger.info("eta_revision_dataset", extra={"fields": result.eta_revision})
    failed = {k: v for k, v in result.eta_revision["quality_checks"].items() if v}
    if failed:
        logger.error("eta_revision_checks_failed", extra={"fields": failed})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
