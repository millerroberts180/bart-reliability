import tomllib
from pathlib import Path

import pytest

from bart_reliability.warehouse.eta_revision_config import (
    ETARevisionConfig,
    ETARevisionConfigError,
    load_eta_revision_config,
)

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config" / "eta_revision.toml"


def write(tmp_path, text):
    path = tmp_path / "eta_revision.toml"
    path.write_text(text)
    return path


def repo_text():
    return REPO_CONFIG.read_text()


def test_repository_config_matches_documented_defaults():
    config = load_eta_revision_config(REPO_CONFIG)
    assert config == ETARevisionConfig()
    assert config.max_collection_gap_s == 90
    assert (config.stability_window, config.stable_spread_s, config.tier_a_spread_s) == (3, 60, 30)
    assert config.tier_a_persistence_s == (-60, 120)
    assert config.horizon_targets_s == (300, 600, 900)
    assert config.horizon_tolerance_s == 60
    assert config.exclude_origin_stops is True


def test_values_are_read_from_the_file(tmp_path):
    text = repo_text().replace("max_collection_gap_s = 90", "max_collection_gap_s = 120")
    assert load_eta_revision_config(write(tmp_path, text)).max_collection_gap_s == 120


def test_missing_file_fails_clearly(tmp_path):
    with pytest.raises(ETARevisionConfigError, match="not found"):
        load_eta_revision_config(tmp_path / "nope.toml")


def test_missing_key_fails_rather_than_defaulting(tmp_path):
    text = "\n".join(
        line for line in repo_text().splitlines() if not line.startswith("stable_spread_s")
    )
    with pytest.raises(ETARevisionConfigError, match="missing keys \\['stable_spread_s'\\]"):
        load_eta_revision_config(write(tmp_path, text))


def test_unknown_key_fails(tmp_path):
    with pytest.raises(ETARevisionConfigError, match="unknown keys \\['typo_s'\\]"):
        load_eta_revision_config(write(tmp_path, repo_text() + "\ntypo_s = 1\n"))


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("tier_a_spread_s = 30", "tier_a_spread_s = 90", "must not exceed stable_spread_s"),
        ("max_collection_gap_s = 90", "max_collection_gap_s = 30", "60 s polling interval"),
        ("horizon_tolerance_s = 60", "horizon_tolerance_s = 150", "must not overlap"),
        ("tier_a_persistence_s = [-60, 120]", "tier_a_persistence_s = [120, -60]", "low <= high"),
        ("stability_window = 3", "stability_window = 1", "at least 2"),
        ("horizon_tolerance_s = 60", 'horizon_tolerance_s = "60"', "must be an integer"),
        ("exclude_origin_stops = true", "exclude_origin_stops = 1", "true or false"),
    ],
)
def test_invalid_values_fail_clearly(tmp_path, old, new, message):
    assert old in repo_text()
    with pytest.raises(ETARevisionConfigError, match=message):
        load_eta_revision_config(write(tmp_path, repo_text().replace(old, new)))


def test_repository_config_is_valid_toml_with_comments():
    raw = tomllib.loads(repo_text())
    assert set(raw) == set(ETARevisionConfig().as_dict())
    assert repo_text().count("#") > 5  # every parameter is explained
