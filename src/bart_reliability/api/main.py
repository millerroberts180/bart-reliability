"""Command-line entry point: bart-serve-local (historical replay, loopback only)."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from bart_reliability.api.config import (
    DEFAULT_API_CONFIG_PATH,
    ApiConfigError,
    is_loopback,
    load_api_config,
)
from bart_reliability.collector.logging_setup import configure_logging

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve the local historical-replay prediction API on the loopback interface."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_API_CONFIG_PATH)
    parser.add_argument("--as-of", help="replay time, e.g. 2026-10-15T17:00:00Z")
    parser.add_argument("--warehouse", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--host", help="loopback address only (default from config)")
    parser.add_argument("--port", type=int)
    args = parser.parse_args(argv)

    configure_logging(None)
    try:
        cfg = load_api_config(args.config).with_overrides(
            as_of=args.as_of,
            warehouse=args.warehouse,
            bundle=args.bundle,
            host=args.host,
            port=args.port,
        )
    except ApiConfigError as e:
        logger.error("local_api_invalid_config", extra={"fields": {"reason": str(e)}})
        return 2
    if not is_loopback(cfg.host):  # also enforced by the config itself
        logger.error("local_api_refused_host", extra={"fields": {"host": cfg.host}})
        return 2

    import uvicorn

    from bart_reliability.api.app import ApiState, create_app

    state = ApiState.load(cfg)
    logger.info(
        "local_api_starting",
        extra={
            "fields": {
                "mode": "historical_replay",
                "as_of": cfg.as_of.isoformat(),
                "url": f"http://{cfg.host}:{cfg.port}/api/v1/health",
                "problems": state.problems(),
            }
        },
    )
    uvicorn.run(create_app(cfg, state), host=cfg.host, port=cfg.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
