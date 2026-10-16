"""Metric calculations checked against hand-computed values."""

import math

import numpy as np
import pytest

from bart_reliability.modeling.metrics import (
    calibration_table,
    classification_metrics,
    regression_metrics,
    relative_to,
)


def test_regression_metrics_by_hand():
    m = regression_metrics(np.array([0, 10, 20]), np.array([0, 20, 10]))
    assert m["n"] == 3
    assert m["mae_s"] == pytest.approx(20 / 3, abs=0.01)
    assert m["median_ae_s"] == 10
    assert m["rmse_s"] == pytest.approx(math.sqrt(200 / 3), abs=0.01)
    assert m["mean_error_s"] == 0


def test_regression_metrics_empty():
    assert regression_metrics(np.array([]), np.array([]))["mae_s"] is None


def test_classification_metrics_by_hand():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.6, 0.4, 0.9])
    m = classification_metrics(y, p, threshold=0.5)
    assert (m["n"], m["positives"], m["prevalence"], m["predicted_positive"]) == (4, 2, 0.5, 2)
    assert (m["precision"], m["recall"]) == (0.5, 0.5)
    # Positive-negative pairs ranked correctly: 3 of 4.
    assert m["roc_auc"] == 0.75
    # Ranked 0.9 (hit), 0.6, 0.4 (hit), 0.1: precision 1 at recall 0.5, 2/3 at recall 1.
    assert m["pr_auc"] == pytest.approx(0.5 * 1 + 0.5 * 2 / 3, abs=1e-4)
    assert m["brier"] == pytest.approx((0.01 + 0.36 + 0.36 + 0.01) / 4)
    # Bins: 0.1 -> [0.1,0.2) observed 0; 0.4 -> [0.4,0.5) observed 1; 0.6 -> observed 0;
    # 0.9 -> [0.9,1.0] observed 1. ECE = mean(|0-0.1|, |1-0.4|, |0-0.6|, |1-0.9|).
    assert m["ece"] == pytest.approx((0.1 + 0.6 + 0.6 + 0.1) / 4)


def test_threshold_is_inclusive_and_undefined_values_are_none():
    y = np.array([0, 1])
    assert classification_metrics(y, np.array([0.2, 0.5]), 0.5)["precision"] == 1.0
    none_predicted = classification_metrics(y, np.array([0.1, 0.2]), 0.5)
    assert none_predicted["precision"] is None
    assert none_predicted["recall"] == 0.0
    one_class = classification_metrics(np.array([0, 0]), np.array([0.1, 0.2]), 0.5)
    assert one_class["roc_auc"] is None
    assert one_class["pr_auc"] is None
    assert one_class["recall"] is None


def test_constant_scores_give_no_skill_values():
    # The no-revision baseline predicts probability 0 everywhere.
    y = np.array([0, 0, 0, 1])
    m = classification_metrics(y, np.zeros(4), 0.5)
    assert m["roc_auc"] == 0.5
    assert m["pr_auc"] == 0.25  # equals prevalence
    assert m["brier"] == 0.25


def test_calibration_table_bins():
    table = calibration_table(np.array([0, 1, 1, 0, 1]), np.array([0.0, 0.05, 0.1, 0.95, 1.0]))
    assert len(table) == 10
    assert table[0] == {"bin": "[0.0, 0.1)", "n": 2, "mean_predicted": 0.025, "observed_rate": 0.5}
    assert table[1]["n"] == 1  # 0.1 starts the second bin
    assert table[9]["bin"] == "[0.9, 1.0]" and table[9]["n"] == 2  # 1.0 is included
    assert table[5] == {"bin": "[0.5, 0.6)", "n": 0, "mean_predicted": None, "observed_rate": None}


def test_relative_to_baseline():
    rel = relative_to(
        {"mae_s": 8.0, "brier": None}, {"mae_s": 10.0, "brier": 0.2}, ("mae_s", "brier")
    )
    assert rel["mae_s"] == {"difference": -2.0, "pct": -20.0}
    assert rel["brier"] == {"difference": None, "pct": None}
