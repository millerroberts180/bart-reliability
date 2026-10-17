"""Configuration for the local historical-replay API (config/local_api.toml)."""

from __future__ import annotations

import ipaddress
import tomllib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_API_CONFIG_PATH = Path("config/local_api.toml")
LOOPBACK_NAMES = {"localhost"}


class ApiConfigError(ValueError):
    """Raised when the local API configuration is missing values or invalid."""


def is_loopback(host: str) -> bool:
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def parse_utc(value: str) -> datetime:
    try:
        ts = datetime.fromisoformat(value)
    except (TypeError, ValueError) as e:
        raise ApiConfigError(f"as_of is not an ISO-8601 timestamp: {value!r}") from e
    if ts.tzinfo is None:
        raise ApiConfigError("as_of must include a UTC offset, e.g. 2026-10-15T17:00:00Z")
    return ts.astimezone(UTC)


@dataclass(frozen=True)
class LocalApiConfig:
    as_of: datetime
    warehouse: Path
    bundle: Path
    stale_after_seconds: int
    history_lookback_seconds: int
    stability_may_be_revised: float
    stability_likely_to_be_revised: float
    host: str
    port: int

    def __post_init__(self):
        problems = []
        if self.as_of.tzinfo is None:
            problems.append("as_of must be timezone-aware")
        if self.stale_after_seconds <= 0:
            problems.append("stale_after_seconds must be positive")
        if self.history_lookback_seconds < 3600:
            problems.append("history_lookback_seconds must be at least 3600")
        if not 0 < self.stability_may_be_revised < self.stability_likely_to_be_revised < 1:
            problems.append("stability cutoffs must satisfy 0 < may_be_revised < likely < 1")
        if not is_loopback(self.host):
            problems.append(f"host {self.host!r} is not a loopback address; this API is local only")
        if not 0 < self.port < 65536:
            problems.append("port must be between 1 and 65535")
        if problems:
            raise ApiConfigError("; ".join(problems))

    def with_overrides(self, **overrides) -> LocalApiConfig:
        clean = {k: v for k, v in overrides.items() if v is not None}
        if isinstance(clean.get("as_of"), str):
            clean["as_of"] = parse_utc(clean["as_of"])
        return replace(self, **clean)


def load_api_config(path: Path = DEFAULT_API_CONFIG_PATH) -> LocalApiConfig:
    """Read a TOML file. Every key is required, so defaults never apply silently."""
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError as e:
        raise ApiConfigError(f"local API config not found: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ApiConfigError(f"local API config is not valid TOML: {e}") from e
    keys = {
        "as_of",
        "warehouse",
        "bundle",
        "stale_after_seconds",
        "history_lookback_seconds",
        "stability_may_be_revised",
        "stability_likely_to_be_revised",
        "host",
        "port",
    }
    missing, unknown = sorted(keys - raw.keys()), sorted(raw.keys() - keys)
    if missing or unknown:
        raise ApiConfigError(f"missing keys {missing}, unknown keys {unknown}")
    for name in ("stale_after_seconds", "history_lookback_seconds", "port"):
        if not isinstance(raw[name], int) or isinstance(raw[name], bool):
            raise ApiConfigError(f"{name} must be an integer")
    return LocalApiConfig(
        as_of=parse_utc(str(raw["as_of"])),
        warehouse=Path(raw["warehouse"]),
        bundle=Path(raw["bundle"]),
        stale_after_seconds=raw["stale_after_seconds"],
        history_lookback_seconds=raw["history_lookback_seconds"],
        stability_may_be_revised=float(raw["stability_may_be_revised"]),
        stability_likely_to_be_revised=float(raw["stability_likely_to_be_revised"]),
        host=str(raw["host"]),
        port=raw["port"],
    )
