"""Command-line entry point: bart-eta-model."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from bart_reliability.collector.logging_setup import configure_logging
from bart_reliability.modeling.config import (
    DEFAULT_CONFIG_PATH,
    LeakageError,
    ModelConfigError,
    load_model_config,
)
from bart_reliability.modeling.pipeline import run_pipeline

logger = logging.getLogger(__name__)

DEFAULT_DB = Path("data/warehouse/bart.duckdb")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fit and evaluate leakage-safe ETA revision models on a warehouse."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="warehouse (read-only)")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--out-dir", type=Path, help="default: output_dir from the config")
    args = parser.parse_args(argv)

    configure_logging(None)
    try:
        cfg = load_model_config(args.config)
        logger.info("eta_model_started", extra={"fields": {"db": str(args.db)}})
        result = run_pipeline(args.db, cfg, args.out_dir)
    except LeakageError as e:
        logger.error("eta_model_leakage_check_failed", extra={"fields": {"reason": str(e)}})
        return 1
    except (ModelConfigError, FileNotFoundError) as e:
        logger.error("eta_model_invalid_input", extra={"fields": {"reason": str(e)}})
        return 2

    test = result.metrics["test"]
    selected = result.metrics["selection"]
    reg, cls = selected["regression"]["selected"], selected["classification"]["selected"]
    logger.info(
        "eta_model_complete",
        extra={
            "fields": {
                "out_dir": str(result.out_dir),
                "provisional": True,
                "samples": result.metrics["samples"],
                "selected": {"regression": reg, "classification": cls},
                "test_mae_s": {
                    name: test["regression"][name]["overall"]["mae_s"]
                    for name in test["regression"]
                },
                "test_brier": {
                    name: test["classification"][name]["overall"]["brier"]
                    for name in test["classification"]
                },
            }
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
