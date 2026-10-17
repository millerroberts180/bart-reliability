"""Command-line entry point: bart-eta-bundle build | verify | predict."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from bart_reliability.collector.logging_setup import configure_logging
from bart_reliability.modeling.config import (
    DEFAULT_CONFIG_PATH,
    LeakageError,
    ModelConfigError,
    load_model_config,
)
from bart_reliability.serving.config import (
    DEFAULT_BUNDLE_CONFIG_PATH,
    BundleConfigError,
    load_bundle_config,
)
from bart_reliability.serving.predictor import (
    DEFAULT_BUNDLE_DIR,
    BundleError,
    RecordError,
    load_predictor,
)

logger = logging.getLogger(__name__)
DEFAULT_DB = Path("data/warehouse/bart.duckdb")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build, verify and use the ETA revision bundle.")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="rebuild the bundle from a warehouse")
    build.add_argument("--db", type=Path, default=DEFAULT_DB, help="warehouse (read-only)")
    build.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    build.add_argument("--bundle-config", type=Path, default=DEFAULT_BUNDLE_CONFIG_PATH)
    build.add_argument("--run-dir", type=Path, help="modeling run (default: from the config)")
    build.add_argument("--out-dir", type=Path, help="bundle (default: from the bundle config)")
    for name in ("verify", "predict"):
        p = sub.add_parser(name)
        p.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE_DIR)
        p.add_argument("--expected-bundle-id", help="refuse any other build")
        if name == "predict":
            p.add_argument(
                "--record",
                type=Path,
                required=True,
                help="JSON file with one record ('-' for stdin)",
            )
    args = parser.parse_args(argv)

    configure_logging(None)
    try:
        if args.command == "build":
            from bart_reliability.serving.bundle import build_bundle

            result = build_bundle(
                args.db,
                load_model_config(args.config),
                load_bundle_config(args.bundle_config),
                out_dir=args.out_dir,
                run_dir=args.run_dir,
            )
            meta = result.metadata
            logger.info(
                "eta_bundle_built",
                extra={
                    "fields": {
                        "bundle_dir": str(result.bundle_dir),
                        "bundle_id": meta["bundle_id"],
                        "model_version": meta["model"]["version"],
                        "verification": meta["verification"],
                        "interval_available": meta["interval"]["available"],
                        "interval_unavailable_reasons": meta["interval"]["unavailable_reasons"],
                    }
                },
            )
            return 0
        predictor = load_predictor(args.bundle, args.expected_bundle_id)
        if args.command == "verify":
            meta = predictor.metadata
            print(
                json.dumps(
                    {
                        "bundle_id": meta["bundle_id"],
                        "model": meta["model"]["version"],
                        "feature_schema_version": meta["feature_schema_version"],
                        "verified": True,
                    },
                    indent=1,
                )
            )
            return 0
        text = sys.stdin.read() if str(args.record) == "-" else args.record.read_text()
        print(json.dumps(predictor.predict(json.loads(text)), indent=1))
        return 0
    except (BundleError, RecordError, json.JSONDecodeError) as e:
        logger.error("eta_bundle_rejected", extra={"fields": {"reason": str(e)}})
        return 1
    except (ModelConfigError, LeakageError, BundleConfigError, FileNotFoundError) as e:
        logger.error("eta_bundle_invalid_input", extra={"fields": {"reason": str(e)}})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
