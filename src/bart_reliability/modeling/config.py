"""Configuration for ETA revision models (config/eta_model.toml)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from bart_reliability.modeling.features import FEATURE_KINDS, PROHIBITED_COLUMNS

DEFAULT_CONFIG_PATH = Path("config/eta_model.toml")
SPLITS = ("train", "validation", "test")
# Tables that may be left out entirely; when present, every key is still required.
OPTIONAL_TABLES = frozenset({"locked_comparison"})
QUALITY_TIERS = ("A", "B")


class ModelConfigError(ValueError):
    """Raised when the model configuration is missing values or invalid."""


class LeakageError(ModelConfigError):
    """Raised when a configured feature or pipeline step could leak outcome information."""


@dataclass(frozen=True)
class LinearConfig:
    huber_alpha: tuple[float, ...]
    huber_epsilon: float
    logistic_c: tuple[float, ...]
    max_iter: int


@dataclass(frozen=True)
class TreeConfig:
    max_leaf_nodes: tuple[int, ...]
    learning_rate: float
    max_iter: int
    min_samples_leaf: int
    l2_regularization: float


@dataclass(frozen=True)
class LockedComparisonConfig:
    """An earlier, locked model pair scored on the test rows beside the retrained models."""

    name: str
    bundle_dir: Path
    bundle_id: str


@dataclass(frozen=True)
class ModelConfig:
    seed: int
    large_revision_threshold_s: int
    decision_threshold: float
    quality_tiers: tuple[str, ...]
    output_dir: Path
    split: dict[str, tuple[date, date]]
    numeric_features: tuple[str, ...]
    categorical_features: tuple[str, ...]
    baseline_levels: tuple[tuple[str, ...], ...]
    baseline_min_group_size: int
    baseline_sensitivity_min_group_sizes: tuple[int, ...]
    linear: LinearConfig
    tree: TreeConfig
    calibration_bins: int
    bootstrap_replicates: int
    bootstrap_confidence_level: float
    # Optional: without it no locked model is loaded or scored.
    locked_comparison: LockedComparisonConfig | None = None

    @property
    def features(self) -> tuple[str, ...]:
        return self.numeric_features + self.categorical_features

    def __post_init__(self):
        problems = []
        problems += validate_features(self.numeric_features, self.categorical_features)
        problems += validate_split(self.split)
        if not set(self.quality_tiers) <= set(QUALITY_TIERS) or not self.quality_tiers:
            problems.append(f"quality_tiers must be a non-empty subset of {QUALITY_TIERS}")
        if self.large_revision_threshold_s <= 0:
            problems.append("large_revision_threshold_s must be positive")
        if not 0 < self.decision_threshold < 1:
            problems.append("decision_threshold must be between 0 and 1")
        if self.baseline_min_group_size < 1:
            problems.append("historical_baseline.min_group_size must be at least 1")
        for level in self.baseline_levels:
            bad = [c for c in level if FEATURE_KINDS.get(c) != "categorical"]
            if bad:
                problems.append(f"historical_baseline level uses non-categorical columns {bad}")
        sizes = self.baseline_sensitivity_min_group_sizes
        if (
            not sizes
            or any(n < 1 for n in sizes)
            or list(sizes) != sorted(set(sizes))
            or self.baseline_min_group_size not in sizes
        ):
            problems.append(
                "historical_baseline.sensitivity_min_group_sizes must be increasing, positive "
                "and include min_group_size"
            )
        if self.bootstrap_replicates < 1:
            problems.append("uncertainty.replicates must be positive")
        if not 0 < self.bootstrap_confidence_level < 1:
            problems.append("uncertainty.confidence_level must be between 0 and 1")
        if self.calibration_bins < 2:
            problems.append("calibration.bins must be at least 2")
        if not (self.linear.huber_alpha and self.linear.logistic_c and self.tree.max_leaf_nodes):
            problems.append("every model grid needs at least one value")
        if self.locked_comparison is not None:
            problems += validate_locked_comparison(self.locked_comparison)
        if problems:
            leaks = [p for p in problems if p.startswith("leakage:")]
            raise (LeakageError if leaks else ModelConfigError)("; ".join(problems))

    def as_dict(self) -> dict:
        d = asdict(self)
        d["output_dir"] = str(self.output_dir)
        d["split"] = {k: [str(a), str(b)] for k, (a, b) in self.split.items()}
        if self.locked_comparison is not None:
            d["locked_comparison"]["bundle_dir"] = str(self.locked_comparison.bundle_dir)
        return d


def validate_features(numeric: tuple[str, ...], categorical: tuple[str, ...]) -> list[str]:
    """Problems with a feature selection; leakage problems are prefixed 'leakage:'."""
    problems = []
    selected = [*numeric, *categorical]
    prohibited = sorted(set(selected) & PROHIBITED_COLUMNS)
    if prohibited:
        problems.append(f"leakage: prohibited columns selected as features {prohibited}")
    unknown = sorted(set(selected) - FEATURE_KINDS.keys() - set(prohibited))
    if unknown:
        problems.append(f"leakage: features not in the point-in-time catalog {unknown}")
    for name, kind in [
        *((n, "numeric") for n in numeric),
        *((n, "categorical") for n in categorical),
    ]:
        if name in FEATURE_KINDS and FEATURE_KINDS[name] != kind:
            problems.append(f"{name} is {FEATURE_KINDS[name]}, not {kind}")
    if len(set(selected)) != len(selected):
        problems.append("features must not repeat")
    if not selected:
        problems.append("at least one feature is required")
    return problems


def validate_locked_comparison(locked: LockedComparisonConfig) -> list[str]:
    problems = []
    if not re.fullmatch(r"locked_[a-z0-9_]+", locked.name):
        problems.append("locked_comparison.name must look like 'locked_<label>'")
    if not re.fullmatch(r"[0-9a-f]{64}", locked.bundle_id):
        problems.append("locked_comparison.bundle_id must be a SHA-256 hex digest")
    return problems


def validate_split(split: dict[str, tuple[date, date]]) -> list[str]:
    if set(split) != set(SPLITS):
        return [f"split must define exactly {SPLITS}"]
    problems = []
    for name in SPLITS:
        start, end = split[name]
        if start > end:
            problems.append(f"split.{name} starts after it ends")
    for earlier, later in zip(SPLITS, SPLITS[1:], strict=False):
        if split[earlier][1] >= split[later][0]:
            problems.append(f"split.{earlier} must end before split.{later} starts")
    return problems


def load_model_config(path: Path = DEFAULT_CONFIG_PATH) -> ModelConfig:
    """Read a TOML file. Every key is required, so defaults never apply silently."""
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError as e:
        raise ModelConfigError(f"model config not found: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ModelConfigError(f"model config is not valid TOML: {e}") from e

    expected = {
        "": {
            "seed",
            "large_revision_threshold_s",
            "decision_threshold",
            "quality_tiers",
            "output_dir",
            "split",
            "features",
            "historical_baseline",
            "linear",
            "tree",
            "calibration",
            "uncertainty",
        },
        "split": set(SPLITS),
        "locked_comparison": {"name", "bundle_dir", "bundle_id"},
        "features": {"numeric", "categorical"},
        "historical_baseline": {"levels", "min_group_size", "sensitivity_min_group_sizes"},
        "linear": {"huber_alpha", "huber_epsilon", "logistic_c", "max_iter"},
        "tree": {
            "max_leaf_nodes",
            "learning_rate",
            "max_iter",
            "min_samples_leaf",
            "l2_regularization",
        },
        "calibration": {"bins"},
        "uncertainty": {"replicates", "confidence_level"},
    }
    for section, keys in expected.items():
        if section in OPTIONAL_TABLES and section not in raw:
            continue
        table = raw if not section else raw.get(section)
        if not isinstance(table, dict):
            raise ModelConfigError(f"missing table [{section}]")
        top = keys | (OPTIONAL_TABLES & raw.keys()) if not section else keys
        missing, unknown = sorted(keys - table.keys()), sorted(table.keys() - top)
        if missing or unknown:
            where = f"[{section}]" if section else "top level"
            raise ModelConfigError(f"{where}: missing keys {missing}, unknown keys {unknown}")

    try:
        split = {}
        for name in SPLITS:
            start, end = raw["split"][name]
            split[name] = (_date(start), _date(end))
        return ModelConfig(
            seed=_int(raw["seed"], "seed"),
            large_revision_threshold_s=_int(
                raw["large_revision_threshold_s"], "large_revision_threshold_s"
            ),
            decision_threshold=float(raw["decision_threshold"]),
            quality_tiers=tuple(raw["quality_tiers"]),
            output_dir=Path(raw["output_dir"]),
            split=split,
            numeric_features=tuple(raw["features"]["numeric"]),
            categorical_features=tuple(raw["features"]["categorical"]),
            baseline_levels=tuple(tuple(level) for level in raw["historical_baseline"]["levels"]),
            baseline_min_group_size=_int(
                raw["historical_baseline"]["min_group_size"], "min_group_size"
            ),
            baseline_sensitivity_min_group_sizes=tuple(
                _int(n, "sensitivity_min_group_sizes")
                for n in raw["historical_baseline"]["sensitivity_min_group_sizes"]
            ),
            linear=LinearConfig(
                huber_alpha=tuple(float(a) for a in raw["linear"]["huber_alpha"]),
                huber_epsilon=float(raw["linear"]["huber_epsilon"]),
                logistic_c=tuple(float(c) for c in raw["linear"]["logistic_c"]),
                max_iter=_int(raw["linear"]["max_iter"], "linear.max_iter"),
            ),
            tree=TreeConfig(
                max_leaf_nodes=tuple(
                    _int(n, "tree.max_leaf_nodes") for n in raw["tree"]["max_leaf_nodes"]
                ),
                learning_rate=float(raw["tree"]["learning_rate"]),
                max_iter=_int(raw["tree"]["max_iter"], "tree.max_iter"),
                min_samples_leaf=_int(raw["tree"]["min_samples_leaf"], "tree.min_samples_leaf"),
                l2_regularization=float(raw["tree"]["l2_regularization"]),
            ),
            calibration_bins=_int(raw["calibration"]["bins"], "calibration.bins"),
            bootstrap_replicates=_int(raw["uncertainty"]["replicates"], "uncertainty.replicates"),
            bootstrap_confidence_level=float(raw["uncertainty"]["confidence_level"]),
            locked_comparison=_locked(raw.get("locked_comparison")),
        )
    except ModelConfigError:
        raise
    except (TypeError, ValueError) as e:
        raise ModelConfigError(f"invalid model config: {e}") from e


def _locked(table: dict | None) -> LockedComparisonConfig | None:
    if table is None:
        return None
    return LockedComparisonConfig(
        name=str(table["name"]),
        bundle_dir=Path(table["bundle_dir"]),
        bundle_id=str(table["bundle_id"]),
    )


def _int(value, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ModelConfigError(f"{name} must be an integer")
    return value


def _date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)
