from pathlib import Path

import pytest

from bart_reliability.collector.config import ConfigError, load_config, parse_config

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config" / "collector.toml"


def valid_raw():
    return {
        "interval_seconds": 60,
        "output_dir": "data/raw/gtfs_rt",
        "retry": {
            "timeout_seconds": 2,
            "max_attempts": 3,
            "backoff_initial_seconds": 1,
            "backoff_max_seconds": 4,
        },
        "feeds": [{"name": "alerts", "url": "https://example.test/alerts"}],
    }


def test_repository_config_loads():
    config = load_config(REPO_CONFIG)
    assert config.interval_seconds == 60
    assert [feed.name for feed in config.feeds] == ["trip_updates", "alerts"]


def test_missing_file_raises_config_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")


def test_missing_value_raises_config_error():
    raw = valid_raw()
    del raw["retry"]["max_attempts"]
    with pytest.raises(ConfigError, match="max_attempts"):
        parse_config(raw)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("interval_seconds",), 0),
        (("retry", "max_attempts"), 0),
        (("retry", "timeout_seconds"), -1),
    ],
)
def test_out_of_range_values_are_rejected(path, value):
    raw = valid_raw()
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ConfigError):
        parse_config(raw)


@pytest.mark.parametrize("name", ["../escape", "Trip Updates", ""])
def test_unsafe_feed_names_are_rejected(name):
    raw = valid_raw()
    raw["feeds"][0]["name"] = name
    with pytest.raises(ConfigError, match="feed name"):
        parse_config(raw)


def test_duplicate_feed_names_are_rejected():
    raw = valid_raw()
    raw["feeds"].append(dict(raw["feeds"][0]))
    with pytest.raises(ConfigError, match="unique"):
        parse_config(raw)
