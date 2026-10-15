"""Baselines: train-only fitting and the documented fallback levels."""

import numpy as np
import pandas as pd
import pytest

from bart_reliability.modeling.baselines import (
    GLOBAL_LEVEL,
    HistoricalBaseline,
    NoRevisionBaseline,
)
from bart_reliability.modeling.config import LeakageError

LEVELS = (
    ("published_horizon_bucket_s", "route_short_name", "stop_id"),
    ("published_horizon_bucket_s", "route_short_name"),
    ("published_horizon_bucket_s",),
)


def rows(spec, split="train"):
    """spec: [(bucket, route, stop, revision_s), ...]"""
    df = pd.DataFrame(
        spec,
        columns=[
            "published_horizon_bucket_s",
            "route_short_name",
            "stop_id",
            "eta_revision_seconds",
        ],
    )
    df["large_revision"] = (df["eta_revision_seconds"].abs() > 60).astype(int)
    df["split"] = split
    return df


TRAIN = rows(
    [
        # (300, R, S1): 3 rows, enough for its own group
        ("300", "R", "S1", 10),
        ("300", "R", "S1", 20),
        ("300", "R", "S1", 90),
        # (300, R, S2): only 2 rows, so it defers to (300, R)
        ("300", "R", "S2", 100),
        ("300", "R", "S2", 120),
        # (900, Q, S9): 3 rows of another route and bucket
        ("900", "Q", "S9", 200),
        ("900", "Q", "S9", 300),
        ("900", "Q", "S9", 400),
    ]
)


@pytest.fixture
def fitted():
    return HistoricalBaseline(LEVELS, min_group_size=3).fit(TRAIN)


def test_no_revision_predicts_zero():
    reg, prob = NoRevisionBaseline().predict(TRAIN)
    assert (reg == 0).all() and (prob == 0).all()


def test_fallback_levels(fitted):
    query = rows(
        [
            ("300", "R", "S1", 0),  # own group
            ("300", "R", "S2", 0),  # small group -> bucket x route (5 rows)
            ("300", "Z", "S1", 0),  # unseen route -> bucket (5 rows)
            ("600", "R", "S1", 0),  # unseen bucket -> all training rows
        ],
        split="validation",
    )
    reg, prob, level = fitted.predict(query)
    assert list(level) == [
        "published_horizon_bucket_s+route_short_name+stop_id",
        "published_horizon_bucket_s+route_short_name",
        "published_horizon_bucket_s",
        GLOBAL_LEVEL,
    ]
    assert list(reg) == [20, 90, 90, np.median(TRAIN["eta_revision_seconds"])]
    assert prob[0] == pytest.approx(1 / 3)
    assert prob[1] == pytest.approx(3 / 5)  # 90, 100, 120 exceed 60 s
    assert prob[3] == pytest.approx(TRAIN["large_revision"].mean())


def test_fit_refuses_non_training_rows():
    mixed = pd.concat([TRAIN, rows([("300", "R", "S1", 5)], split="validation")])
    with pytest.raises(LeakageError, match="training rows only"):
        HistoricalBaseline(LEVELS, 3).fit(mixed)
    with pytest.raises(LeakageError):
        HistoricalBaseline(LEVELS, 3).fit(rows([("300", "R", "S1", 5)], split="test"))


def test_fit_ignores_rows_it_is_not_given(fitted):
    """Predictions depend only on training rows: other splits' labels cannot move them."""
    query = rows([("300", "R", "S1", 999), ("900", "Q", "S9", -999)], split="test")
    before = fitted.predict(query)
    query["eta_revision_seconds"] = [-5, 5]
    after = fitted.predict(query)
    for a, b in zip(before, after, strict=True):
        assert list(a) == list(b)


def test_fitted_groups_table(fitted):
    groups = fitted.fitted_groups()
    assert set(groups["level_name"]) == {
        "published_horizon_bucket_s+route_short_name+stop_id",
        "published_horizon_bucket_s+route_short_name",
        "published_horizon_bucket_s",
        GLOBAL_LEVEL,
    }
    # The 2-row group is below min_group_size and is not stored.
    assert "300|R|S2" not in set(groups["group_key"])
    assert groups.loc[groups["level_name"] == GLOBAL_LEVEL, "n"].item() == len(TRAIN)


# --- Predeclared min_group_size sensitivity -------------------------------------------

SIZES = (1, 3, 5, 9)


def test_sensitivity_versions_fit_on_training_rows_only():
    from bart_reliability.modeling.baselines import fit_sensitivity

    fitted = fit_sensitivity(TRAIN, LEVELS, SIZES)
    assert set(fitted) == set(SIZES)
    for size, model in fitted.items():
        assert model.min_group_size == size and model.levels == LEVELS
        assert model.global_stats["n"] == len(TRAIN)
    with pytest.raises(LeakageError):
        fit_sensitivity(
            pd.concat([TRAIN, rows([("300", "R", "S1", 5)], "validation")]), LEVELS, SIZES
        )


def test_validation_and_test_outcomes_never_enter_sensitivity_aggregates():
    from bart_reliability.modeling.baselines import fit_sensitivity

    evaluation = rows(
        [("300", "R", "S1", 1), ("900", "Q", "S9", 2), ("600", "Z", "S7", 3)], split="test"
    )
    before = {
        k: (m.fitted_groups(), m.predict(evaluation))
        for k, m in fit_sensitivity(TRAIN, LEVELS, SIZES).items()
    }
    scrambled = evaluation.assign(eta_revision_seconds=[-500, 500, 0], large_revision=[1, 1, 0])
    after = {
        k: (m.fitted_groups(), m.predict(scrambled))
        for k, m in fit_sensitivity(TRAIN, LEVELS, SIZES).items()
    }
    for size in SIZES:
        pd.testing.assert_frame_equal(before[size][0], after[size][0])
        for a, b in zip(before[size][1], after[size][1], strict=True):
            assert list(a) == list(b)


def test_sensitivity_preserves_the_fallback_hierarchy():
    from bart_reliability.modeling.baselines import fit_sensitivity

    query = rows(
        [("300", "R", "S1", 0), ("300", "R", "S2", 0), ("900", "Q", "S9", 0)], split="validation"
    )
    order = [*("+".join(level) for level in LEVELS), GLOBAL_LEVEL]
    levels = {
        size: list(model.predict(query)[2])
        for size, model in fit_sensitivity(TRAIN, LEVELS, SIZES).items()
    }
    # (300,R,S1) has 3 rows, (300,R) 5, bucket 300 5, all rows 8.
    assert [levels[s][0] for s in SIZES] == [order[0], order[0], order[1], order[3]]
    # (300,R,S2) has 2 rows: it defers to (300,R) from size 3 on.
    assert [levels[s][1] for s in SIZES] == [order[0], order[1], order[1], order[3]]
    # A larger minimum never moves a row to a more specific level.
    for i in range(len(query)):
        ranks = [order.index(levels[s][i]) for s in SIZES]
        assert ranks == sorted(ranks)
    # The primary-size version predicts exactly what the configured baseline predicts.
    primary = HistoricalBaseline(LEVELS, 3).fit(TRAIN).predict(query)
    sensitivity = fit_sensitivity(TRAIN, LEVELS, SIZES)[3].predict(query)
    for a, b in zip(primary, sensitivity, strict=True):
        assert list(a) == list(b)


def test_empty_level_is_reported_without_error():
    groups = HistoricalBaseline(LEVELS, 100).fit(TRAIN).fitted_groups()
    assert list(groups["level_name"]) == [GLOBAL_LEVEL]
