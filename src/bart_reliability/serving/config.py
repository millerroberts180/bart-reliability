"""Configuration for the inference bundle (config/eta_model_bundle.toml)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_BUNDLE_CONFIG_PATH = Path("config/eta_model_bundle.toml")


class BundleConfigError(ValueError):
    """Raised when the bundle configuration is missing values or invalid."""


@dataclass(frozen=True)
class BundleConfig:
    model_name: str
    model_line_version: str
    output_dir: Path
    nominal_coverage: float
    min_calibration_examples_per_horizon: int
    max_coverage_error: float
    single_record_parity_rows: int

    def __post_init__(self):
        problems = []
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.model_name):
            problems.append("model_name must be lowercase letters, digits and underscores")
        if not re.fullmatch(r"\d+\.\d+\.\d+", self.model_line_version):
            problems.append("model_line_version must look like 1.2.3")
        if not 0 < self.nominal_coverage < 1:
            problems.append("interval.nominal_coverage must be between 0 and 1")
        if self.min_calibration_examples_per_horizon < 1:
            problems.append("interval.min_calibration_examples_per_horizon must be positive")
        if not 0 <= self.max_coverage_error < 1:
            problems.append("interval.max_coverage_error must be in [0, 1)")
        if self.single_record_parity_rows < 1:
            problems.append("verification.single_record_parity_rows must be positive")
        if problems:
            raise BundleConfigError("; ".join(problems))

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("output_dir")  # machine-local, not part of the bundle's identity
        return d


def load_bundle_config(path: Path = DEFAULT_BUNDLE_CONFIG_PATH) -> BundleConfig:
    """Read a TOML file. Every key is required, so defaults never apply silently."""
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError as e:
        raise BundleConfigError(f"bundle config not found: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise BundleConfigError(f"bundle config is not valid TOML: {e}") from e
    expected = {
        "": {"model_name", "model_line_version", "output_dir", "interval", "verification"},
        "interval": {
            "nominal_coverage",
            "min_calibration_examples_per_horizon",
            "max_coverage_error",
        },
        "verification": {"single_record_parity_rows"},
    }
    for section, keys in expected.items():
        table = raw if not section else raw.get(section)
        if not isinstance(table, dict):
            raise BundleConfigError(f"missing table [{section}]")
        missing, unknown = sorted(keys - table.keys()), sorted(table.keys() - keys)
        if missing or unknown:
            where = f"[{section}]" if section else "top level"
            raise BundleConfigError(f"{where}: missing keys {missing}, unknown keys {unknown}")
    iv, ver = raw["interval"], raw["verification"]
    for name, value in (
        ("min_calibration_examples_per_horizon", iv["min_calibration_examples_per_horizon"]),
        ("single_record_parity_rows", ver["single_record_parity_rows"]),
    ):
        if not isinstance(value, int) or isinstance(value, bool):
            raise BundleConfigError(f"{name} must be an integer")
    try:
        return BundleConfig(
            model_name=str(raw["model_name"]),
            model_line_version=str(raw["model_line_version"]),
            output_dir=Path(raw["output_dir"]),
            nominal_coverage=float(iv["nominal_coverage"]),
            min_calibration_examples_per_horizon=iv["min_calibration_examples_per_horizon"],
            max_coverage_error=float(iv["max_coverage_error"]),
            single_record_parity_rows=ver["single_record_parity_rows"],
        )
    except (TypeError, ValueError) as e:
        if isinstance(e, BundleConfigError):
            raise
        raise BundleConfigError(f"invalid bundle config: {e}") from e
