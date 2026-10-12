"""Configuration for the ETA revision dataset."""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("config/eta_revision.toml")


class ETARevisionConfigError(ValueError):
    """Raised when the ETA revision configuration is missing values or invalid."""


@dataclass(frozen=True)
class ETARevisionConfig:
    max_collection_gap_s: int = 90
    stability_window: int = 3
    stable_spread_s: int = 60
    tier_a_spread_s: int = 30
    tier_a_persistence_s: tuple[int, int] = (-60, 120)
    horizon_targets_s: tuple[int, ...] = (300, 600, 900)
    horizon_tolerance_s: int = 60
    exclude_origin_stops: bool = True

    def __post_init__(self):
        lo, hi = self.tier_a_persistence_s
        problems = []
        if self.max_collection_gap_s < 60:
            problems.append("max_collection_gap_s must be at least the 60 s polling interval")
        if self.stability_window < 2:
            problems.append("stability_window must be at least 2")
        if self.stable_spread_s < 0 or self.tier_a_spread_s < 0:
            problems.append("spreads must not be negative")
        if self.tier_a_spread_s > self.stable_spread_s:
            problems.append("tier_a_spread_s must not exceed stable_spread_s")
        if lo > hi:
            problems.append("tier_a_persistence_s must be [low, high] with low <= high")
        if not self.horizon_targets_s or any(t <= 0 for t in self.horizon_targets_s):
            problems.append("horizon_targets_s must be positive")
        if len(set(self.horizon_targets_s)) != len(self.horizon_targets_s):
            problems.append("horizon_targets_s must be unique")
        if self.horizon_tolerance_s <= 0:
            problems.append("horizon_tolerance_s must be positive")
        # Each prediction can represent at most one target.
        gaps = [
            b - a
            for a, b in zip(
                sorted(self.horizon_targets_s), sorted(self.horizon_targets_s)[1:], strict=False
            )
        ]
        if gaps and self.horizon_tolerance_s * 2 >= min(gaps):
            problems.append("horizon_tolerance_s windows of different targets must not overlap")
        if problems:
            raise ETARevisionConfigError("; ".join(problems))

    def with_overrides(self, **overrides) -> ETARevisionConfig:
        return replace(self, **overrides)

    def as_dict(self) -> dict:
        return asdict(self)


def load_eta_revision_config(path: Path = DEFAULT_CONFIG_PATH) -> ETARevisionConfig:
    """Read a TOML file. Every field must be present, so defaults never apply silently."""
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError as e:
        raise ETARevisionConfigError(f"ETA revision config not found: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ETARevisionConfigError(f"ETA revision config is not valid TOML: {e}") from e

    names = {f.name for f in fields(ETARevisionConfig)}
    missing = sorted(names - raw.keys())
    unknown = sorted(raw.keys() - names)
    if missing or unknown:
        raise ETARevisionConfigError(f"missing keys {missing}, unknown keys {unknown}")
    try:
        values = {
            **raw,
            "tier_a_persistence_s": tuple(int(v) for v in raw["tier_a_persistence_s"]),
            "horizon_targets_s": tuple(int(v) for v in raw["horizon_targets_s"]),
        }
        for name in (
            "max_collection_gap_s",
            "stability_window",
            "stable_spread_s",
            "tier_a_spread_s",
            "horizon_tolerance_s",
        ):
            if not isinstance(values[name], int) or isinstance(values[name], bool):
                raise ETARevisionConfigError(f"{name} must be an integer")
        if not isinstance(values["exclude_origin_stops"], bool):
            raise ETARevisionConfigError("exclude_origin_stops must be true or false")
        if len(values["tier_a_persistence_s"]) != 2:
            raise ETARevisionConfigError("tier_a_persistence_s must have two values")
        return ETARevisionConfig(**values)
    except (TypeError, ValueError) as e:
        if isinstance(e, ETARevisionConfigError):
            raise
        raise ETARevisionConfigError(f"invalid ETA revision config: {e}") from e
