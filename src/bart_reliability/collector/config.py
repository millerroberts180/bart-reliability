"""Load and check collector settings from a TOML file."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

# Feed names become directory names, so keep them to a safe character set.
_FEED_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class ConfigError(ValueError):
    """Raised when the configuration file is missing values or has invalid ones."""


@dataclass(frozen=True)
class FeedConfig:
    name: str
    url: str


@dataclass(frozen=True)
class RetryConfig:
    timeout_seconds: float
    max_attempts: int
    backoff_initial_seconds: float
    backoff_max_seconds: float


@dataclass(frozen=True)
class CollectorConfig:
    interval_seconds: float
    output_dir: Path
    log_file: Path | None
    retry: RetryConfig
    feeds: tuple[FeedConfig, ...]


def load_config(path: Path) -> CollectorConfig:
    """Read a TOML config file and return validated settings."""
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError as e:
        raise ConfigError(f"config file not found: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"config file is not valid TOML: {e}") from e
    return parse_config(raw)


def parse_config(raw: dict) -> CollectorConfig:
    """Build a CollectorConfig from already-parsed TOML data."""
    try:
        retry_raw = raw["retry"]
        retry = RetryConfig(
            timeout_seconds=float(retry_raw["timeout_seconds"]),
            max_attempts=int(retry_raw["max_attempts"]),
            backoff_initial_seconds=float(retry_raw["backoff_initial_seconds"]),
            backoff_max_seconds=float(retry_raw["backoff_max_seconds"]),
        )
        feeds = tuple(FeedConfig(name=f["name"], url=f["url"]) for f in raw["feeds"])
        log_file = raw.get("log_file")
        config = CollectorConfig(
            interval_seconds=float(raw["interval_seconds"]),
            output_dir=Path(raw["output_dir"]),
            log_file=Path(log_file) if log_file else None,
            retry=retry,
            feeds=feeds,
        )
    except KeyError as e:
        raise ConfigError(f"missing config value: {e.args[0]}") from e
    except (TypeError, ValueError) as e:
        raise ConfigError(f"invalid config value: {e}") from e

    _check(config)
    return config


def _check(config: CollectorConfig) -> None:
    retry = config.retry
    if config.interval_seconds <= 0:
        raise ConfigError("interval_seconds must be positive")
    if retry.timeout_seconds <= 0:
        raise ConfigError("retry.timeout_seconds must be positive")
    if retry.max_attempts < 1:
        raise ConfigError("retry.max_attempts must be at least 1")
    if retry.backoff_initial_seconds < 0 or retry.backoff_max_seconds < 0:
        raise ConfigError("retry backoff values must not be negative")
    if not config.feeds:
        raise ConfigError("at least one feed must be configured")

    names = [feed.name for feed in config.feeds]
    if len(names) != len(set(names)):
        raise ConfigError("feed names must be unique")
    for feed in config.feeds:
        if not _FEED_NAME_PATTERN.match(feed.name):
            raise ConfigError(f"invalid feed name {feed.name!r}: use lowercase letters, digits, _")
        if not feed.url.startswith(("https://", "http://")):
            raise ConfigError(f"feed {feed.name!r} url must start with http:// or https://")
