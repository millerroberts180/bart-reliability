"""Paired cluster bootstrap: trip and event grouping, determinism and interval math."""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import average_precision_score

from bart_reliability.modeling.uncertainty import (
    EVENT,
    TRIP,
    bootstrap_draws,
    cluster_resample_weights,
    compare,
    interpret,
    observed_values,
    paired_difference,
    percentile_interval,
    trip_run_key,
)

DATES = [date(2026, 10, 13), date(2026, 10, 14)]


def frame(n_trips=6, seed=0):
    """The same trip_ids on two service dates; each trip has three stop-arrival events,
    and each event one to three published-time horizons."""
    rng = np.random.default_rng(seed)
    rows = []
    for day in DATES:
        for t in range(n_trips):
            for k, seq in enumerate((3, 4, 6)):
                for h in (300, 600, 900)[: 1 + (t + k) % 3]:
                    y = float(rng.integers(-30, 200))
                    rows.append(
                        {
                            "service_date": pd.Timestamp(day),
                            "trip_id": f"T{t}",
                            "event_id": f"{day}:T{t}:{seq}",
                            "horizon_bucket_s": h,
                            "eta_revision_seconds": y,
                            "large_revision": int(abs(y) > 60),
                        }
                    )
    df = pd.DataFrame(rows)
    df[TRIP] = trip_run_key(df["service_date"], df["trip_id"])
    return df


def predictions(rows, seed):
    rng = np.random.default_rng(seed)
    reg = rows["eta_revision_seconds"].to_numpy() + rng.normal(0, 20, len(rows))
    prob = np.clip(rows["large_revision"].to_numpy() * 0.6 + rng.uniform(0, 0.4, len(rows)), 0, 1)
    return reg, prob


def weights_by(rows, w, column):
    return pd.Series(w).groupby(rows[column].to_numpy()).nunique()


def test_every_row_of_a_sampled_trip_shares_its_weight():
    rows = frame()
    n_trips = rows[TRIP].nunique()
    codes = pd.factorize(rows[TRIP], sort=True)[0]
    for w, counts in cluster_resample_weights(rows[TRIP], 50, seed=7):
        assert (weights_by(rows, w, TRIP) == 1).all()
        assert counts.sum() == n_trips  # as many trips drawn as exist
        assert (w == counts[codes]).all()  # a row's weight is its trip's draw count


def test_stops_and_horizons_of_a_trip_stay_together():
    rows = frame()
    per_trip = rows.groupby(TRIP).agg(
        stops=("event_id", "nunique"), horizons=("horizon_bucket_s", "nunique")
    )
    assert (per_trip["stops"] == 3).all() and (per_trip["horizons"] > 1).all()
    for w, _ in cluster_resample_weights(rows[TRIP], 50, seed=7):
        # Every stop and horizon of a trip carries the trip's weight.
        assert (weights_by(rows, w, TRIP) == 1).all()
        assert (weights_by(rows, w, EVENT) == 1).all()
    # Event clustering, by contrast, separates stops of the same trip.
    split = any(
        (weights_by(rows, w, TRIP) > 1).any()
        for w, _ in cluster_resample_weights(rows[EVENT], 50, seed=7)
    )
    assert split


def test_trip_runs_on_different_service_dates_are_not_merged():
    rows = frame()
    assert rows["trip_id"].nunique() == 6 and rows[TRIP].nunique() == 12
    assert trip_run_key(pd.Series(DATES), pd.Series(["T1", "T1"])).tolist() == [
        "2026-10-13:T1",
        "2026-10-14:T1",
    ]
    first, second = (
        (rows[TRIP] == "2026-10-13:T1").to_numpy(),
        (rows[TRIP] == "2026-10-14:T1").to_numpy(),
    )
    differ = [
        w[first][0] != w[second][0] for w, _ in cluster_resample_weights(rows[TRIP], 50, seed=7)
    ]
    assert any(differ)  # the two runs are drawn independently


def test_resampling_is_deterministic_and_seeded():
    ids = frame()[TRIP]
    first = [w for w, _ in cluster_resample_weights(ids, 20, seed=3)]
    again = [w for w, _ in cluster_resample_weights(ids, 20, seed=3)]
    other = [w for w, _ in cluster_resample_weights(ids, 20, seed=4)]
    assert all((a == b).all() for a, b in zip(first, again, strict=True))
    assert any((a != b).any() for a, b in zip(first, other, strict=True))
    # Row order does not matter: clusters are keyed, not positional.
    shuffled = ids.sample(frac=1, random_state=1)
    reordered = [w for w, _ in cluster_resample_weights(shuffled, 20, seed=3)]
    by_key = lambda w, s: pd.Series(w, index=s.to_numpy()).groupby(level=0).first()  # noqa: E731
    assert all(
        by_key(a, ids).equals(by_key(b, shuffled)) for a, b in zip(first, reordered, strict=True)
    )


@pytest.mark.parametrize("cluster", [TRIP, EVENT])
def test_draws_match_a_hand_calculation_with_cluster_weights(cluster):
    rows = frame()
    reg, prob = predictions(rows, 1)
    draws = bootstrap_draws(rows, {"m": reg}, {"m": prob}, 5, 11, cluster=cluster)
    y, yc = rows["eta_revision_seconds"].to_numpy(), rows["large_revision"].to_numpy()
    m = (rows["horizon_bucket_s"] == 600).to_numpy()
    for b, (w, _) in enumerate(cluster_resample_weights(rows[cluster], 5, seed=11)):
        assert draws["m"]["mae_s"]["overall"][b] == pytest.approx(
            np.sum(w * np.abs(reg - y)) / w.sum()
        )
        assert draws["m"]["mae_s"]["600"][b] == pytest.approx(
            np.sum(w[m] * np.abs(reg[m] - y[m])) / w[m].sum()
        )
        assert draws["m"]["brier"][b] == pytest.approx(np.sum(w * (prob - yc) ** 2) / w.sum())
        assert draws["m"]["pr_auc"][b] == pytest.approx(
            average_precision_score(yc, prob, sample_weight=w)
        )


def test_bootstrap_results_are_deterministic():
    rows = frame(10)
    reg_a, prob_a = predictions(rows, 1)
    reg_b, prob_b = predictions(rows, 2)
    args = (rows, {"a": reg_a, "b": reg_b}, {"a": prob_a, "b": prob_b})
    results = [
        compare(rows, bootstrap_draws(*args, 200, 5), observed_values(*args), "a", "a", "b", 0.95)
        for _ in range(2)
    ]
    assert results[0] == results[1]
    # The default clustering unit is the trip run.
    trip = bootstrap_draws(*args, 50, 5)
    explicit = bootstrap_draws(*args, 50, 5, cluster=TRIP)
    assert np.array_equal(trip["a"]["mae_s"]["overall"], explicit["a"]["mae_s"]["overall"])


def test_percentile_interval_by_hand():
    assert percentile_interval(np.arange(101, dtype=float), 0.95) == pytest.approx((2.5, 97.5))
    # Undefined replicates are ignored.
    assert percentile_interval(np.array([1.0, np.nan, 3.0]), 0.5) == pytest.approx((1.5, 2.5))


def test_interpretation_of_intervals():
    assert "does not establish an improvement" in interpret(-1.0, 0.5, "lower")
    assert "within this test day only" in interpret(-2.0, -0.5, "lower")
    assert "worse" in interpret(0.1, 2.0, "lower")
    assert "within this test day only" in interpret(0.01, 0.2, "higher")  # PR-AUC
    assert "does not establish an improvement" in interpret(-0.01, 0.2, "higher")


def test_paired_difference_reports_observed_interval_and_share():
    draws = {
        "m": {
            "brier": np.array([0.10, 0.12, 0.14, 0.16]),
            "pr_auc": np.array([0.6, 0.6, 0.5, 0.7]),
        },
        "b": {
            "brier": np.array([0.11, 0.11, 0.15, 0.15]),
            "pr_auc": np.array([0.5, 0.6, 0.6, 0.6]),
        },
    }
    observed = {"m": {"brier": 0.13, "pr_auc": 0.62}, "b": {"brier": 0.14, "pr_auc": 0.58}}
    brier = paired_difference(draws, observed, "m", "b", "brier", 0.5)
    assert brier["observed"] == pytest.approx(-0.01)
    # Differences: -0.01, +0.01, -0.01, +0.01 -> 25th/75th percentiles -0.01 and +0.01.
    assert (brier["ci_low"], brier["ci_high"]) == (pytest.approx(-0.01), pytest.approx(0.01))
    assert brier["share_of_replicates_model_better"] == 0.5
    assert "does not establish an improvement" in brier["interpretation"]
    pr = paired_difference(draws, observed, "m", "b", "pr_auc", 0.5)
    assert pr["better_when"] == "higher"
    assert pr["share_of_replicates_model_better"] == 0.5  # +0.1 twice, 0 and -0.1 once


def test_identical_predictions_give_a_zero_interval():
    rows = frame()
    reg, prob = predictions(rows, 1)
    args = (rows, {"a": reg, "b": reg.copy()}, {"a": prob, "b": prob.copy()})
    out = compare(rows, bootstrap_draws(*args, 100, 1), observed_values(*args), "a", "a", "b", 0.95)
    for block in (
        out["mae_s"]["overall"],
        *out["mae_s"]["by_horizon"].values(),
        out["brier"],
        out["pr_auc"],
    ):
        assert block["observed"] == 0 and block["ci_low"] == 0 and block["ci_high"] == 0
        assert block["share_of_replicates_model_better"] == 0
        assert "does not establish an improvement" in block["interpretation"]


def test_observed_values_match_the_metric_functions():
    from bart_reliability.modeling.metrics import classification_metrics, regression_metrics

    rows = frame()
    reg, prob = predictions(rows, 1)
    obs = observed_values(rows, {"m": reg}, {"m": prob})
    y, yc = rows["eta_revision_seconds"].to_numpy(), rows["large_revision"].to_numpy()
    assert obs["m"]["mae_s"]["overall"] == pytest.approx(
        regression_metrics(y, reg)["mae_s"], abs=0.01
    )
    cm = classification_metrics(yc, prob, 0.5)
    assert obs["m"]["brier"] == pytest.approx(cm["brier"], abs=1e-4)
    assert obs["m"]["pr_auc"] == pytest.approx(cm["pr_auc"], abs=1e-4)
