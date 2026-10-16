"""Model configuration: strict loading, and refusal of leaky or unknown features."""

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from bart_reliability.modeling.config import (
    LeakageError,
    ModelConfigError,
    load_model_config,
)
from bart_reliability.modeling.features import FEATURES, PROHIBITED_COLUMNS

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config" / "eta_model.toml"


@pytest.fixture
def cfg():
    return load_model_config(REPO_CONFIG)


def test_repository_config_loads(cfg):
    assert cfg.split["train"] == (date(2026, 10, 10), date(2026, 10, 12))
    assert cfg.large_revision_threshold_s == 60
    assert cfg.quality_tiers == ("A",)
    assert "published_horizon_bucket_s" in cfg.categorical_features
    assert set(cfg.features).isdisjoint(PROHIBITED_COLUMNS)


def test_repository_audit_settings(cfg):
    assert cfg.bootstrap_replicates >= 2000
    assert cfg.bootstrap_confidence_level == 0.95
    assert cfg.baseline_min_group_size == 30
    assert cfg.baseline_sensitivity_min_group_sizes == (15, 30, 60, 100)


@pytest.mark.parametrize("sizes", [(15, 60, 100), (30, 15, 60), (0, 30), ()])
def test_sensitivity_sizes_must_be_increasing_and_include_the_primary(cfg, sizes):
    with pytest.raises(ModelConfigError, match="sensitivity_min_group_sizes"):
        replace(cfg, baseline_sensitivity_min_group_sizes=sizes)


def test_catalog_never_contains_prohibited_columns():
    assert {f.name for f in FEATURES}.isdisjoint(PROHIBITED_COLUMNS)
    assert {f.kind for f in FEATURES} == {"numeric", "categorical"}


@pytest.mark.parametrize(
    "column",
    [
        "final_stable_estimate",
        "eta_revision_seconds",
        "absolute_eta_revision_seconds",
        "time_to_proxy_s",
        "target_horizon_s",
        "observation_rank_from_end",
        "last_seen_at",
        "quality_tier",
        "event_id",
    ],
)
def test_prohibited_feature_is_refused(cfg, column):
    with pytest.raises(LeakageError, match="prohibited"):
        replace(cfg, numeric_features=(*cfg.numeric_features, column))


def test_feature_outside_catalog_is_refused(cfg):
    with pytest.raises(LeakageError, match="not in the point-in-time catalog"):
        replace(cfg, numeric_features=(*cfg.numeric_features, "minutes_until_final_estimate"))


def test_feature_kind_must_match_catalog(cfg):
    with pytest.raises(ModelConfigError, match="is categorical, not numeric"):
        replace(
            cfg,
            numeric_features=(*cfg.numeric_features, "stop_id"),
            categorical_features=tuple(c for c in cfg.categorical_features if c != "stop_id"),
        )


@pytest.mark.parametrize(
    "split, message",
    [
        (
            {
                "train": (date(2026, 10, 10), date(2026, 10, 13)),
                "validation": (date(2026, 10, 13), date(2026, 10, 13)),
                "test": (date(2026, 10, 14), date(2026, 10, 14)),
            },
            "must end before",
        ),
        (
            {
                "train": (date(2026, 10, 12), date(2026, 10, 10)),
                "validation": (date(2026, 10, 13), date(2026, 10, 13)),
                "test": (date(2026, 10, 14), date(2026, 10, 14)),
            },
            "starts after it ends",
        ),
        (
            {
                "train": (date(2026, 10, 10), date(2026, 10, 12)),
                "test": (date(2026, 10, 14), date(2026, 10, 14)),
            },
            "exactly",
        ),
    ],
)
def test_split_ranges_must_be_ordered(cfg, split, message):
    with pytest.raises(ModelConfigError, match=message):
        replace(cfg, split=split)


def test_baseline_levels_must_be_categorical(cfg):
    with pytest.raises(ModelConfigError, match="non-categorical"):
        replace(cfg, baseline_levels=(("published_horizon_s",),))


def test_missing_and_unknown_keys_are_reported(tmp_path):
    text = REPO_CONFIG.read_text()
    path = tmp_path / "c.toml"
    path.write_text(text.replace("seed = 20261015\n", ""))
    with pytest.raises(ModelConfigError, match=r"missing keys \['seed'\]"):
        load_model_config(path)
    path.write_text(text.replace("[calibration]\nbins = 10", "[calibration]\nbins = 10\nextra = 1"))
    with pytest.raises(ModelConfigError, match=r"unknown keys \['extra'\]"):
        load_model_config(path)


def test_missing_file_is_a_config_error(tmp_path):
    with pytest.raises(ModelConfigError, match="not found"):
        load_model_config(tmp_path / "absent.toml")
