"""Provisional, horizon-aware residual interval for the predicted ETA revision.

Per published-time horizon bucket, the interval is the predicted revision plus the
empirical lower and upper residual quantiles (actual minus predicted revision) of the
selected regression model on the **validation** split. The model was fitted on training
rows only, so these residuals are out of sample. Validation also selected the model, so
the calibration is not independent of model selection.

Test outcomes never fit the interval. They are used only to measure its coverage and to
apply the availability rule declared in config/eta_model_bundle.toml before any test
coverage was computed. The interval is conditional on one calibration day and one test
day, so it is provisional. A future, independently calibrated interval (calibration days
separate from both selection and test) can be added beside it in the response.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bart_reliability.modeling.uncertainty import (
    TRIP,
    cluster_resample_weights,
    percentile_interval,
)

METHOD = "validation_residual_quantiles_by_published_time_horizon"


def coverage(y, lower, upper) -> float:
    """Share of outcomes inside [lower, upper], both bounds inclusive."""
    y, lower, upper = (np.asarray(a, dtype=float) for a in (y, lower, upper))
    if np.any(lower > upper):
        raise ValueError("interval lower bound above upper bound")
    return float(np.mean((lower <= y) & (y <= upper))) if len(y) else float("nan")


def residual_quantiles(residuals: np.ndarray, nominal: float) -> tuple[float, float]:
    """Equal-tailed empirical quantiles, rounded outward to observed residuals."""
    # Rounded so that, e.g., nominal 0.8 gives exactly 0.1 rather than 0.09999999999999998.
    tail = round((1 - nominal) / 2, 12)
    r = np.asarray(residuals, dtype=float)
    return float(np.quantile(r, tail, method="lower")), float(
        np.quantile(r, round(1 - tail, 12), method="higher")
    )


def _clustered_interval(inside: np.ndarray, clusters: pd.Series, replicates, seed, level):
    draws = np.array(
        [
            (w * inside).sum() / w.sum()
            for w, _ in cluster_resample_weights(clusters, replicates, seed)
        ]
    )
    lo, hi = percentile_interval(draws, level)
    return [round(lo, 4), round(hi, 4)]


def calibrate_interval(
    validation: pd.DataFrame,
    test: pd.DataFrame,
    nominal: float,
    min_calibration_examples: int,
    max_coverage_error: float,
    replicates: int,
    seed: int,
    confidence_level: float,
) -> dict:
    """validation / test: horizon_bucket_s, eta_revision_seconds, predicted_revision_s,
    service_date and (test) trip_run_key."""
    by_horizon, reasons = {}, []
    test_inside = np.zeros(len(test), dtype=bool)
    for bucket in sorted(validation["horizon_bucket_s"].unique()):
        cal = validation[validation["horizon_bucket_s"] == bucket]
        residuals = cal["eta_revision_seconds"] - cal["predicted_revision_s"]
        q_lo, q_hi = residual_quantiles(residuals.to_numpy(), nominal)
        mask = (test["horizon_bucket_s"] == bucket).to_numpy()
        t = test[mask]
        lower, upper = t["predicted_revision_s"] + q_lo, t["predicted_revision_s"] + q_hi
        inside = (lower <= t["eta_revision_seconds"]) & (t["eta_revision_seconds"] <= upper)
        test_inside[mask] = inside.to_numpy()
        test_cov = coverage(t["eta_revision_seconds"], lower, upper)
        key = str(int(bucket))
        by_horizon[key] = {
            "residual_quantiles_s": [q_lo, q_hi],
            "calibration_examples": int(len(cal)),
            "validation_coverage": round(
                coverage(
                    cal["eta_revision_seconds"],
                    cal["predicted_revision_s"] + q_lo,
                    cal["predicted_revision_s"] + q_hi,
                ),
                4,
            ),
            "test_examples": int(len(t)),
            "test_coverage": round(test_cov, 4),
            "test_coverage_interval_trip_clustered": _clustered_interval(
                inside.to_numpy(), t[TRIP], replicates, seed, confidence_level
            ),
            "mean_width_s": round(q_hi - q_lo, 2),
        }
        if len(cal) < min_calibration_examples:
            reasons.append(
                f"{key} s horizon: {len(cal)} calibration examples, fewer than "
                f"{min_calibration_examples}"
            )
        if abs(test_cov - nominal) > max_coverage_error:
            reasons.append(
                f"{key} s horizon: test coverage {test_cov:.4f} is more than "
                f"{max_coverage_error} from nominal {nominal}"
            )
    overall = float(test_inside.mean())
    if abs(overall - nominal) > max_coverage_error:
        reasons.append(
            f"overall test coverage {overall:.4f} is more than {max_coverage_error} from "
            f"nominal {nominal}"
        )
    dates = pd.to_datetime(validation["service_date"])
    test_dates = pd.to_datetime(test["service_date"])
    return {
        "method": METHOD,
        "status": "provisional",
        "nominal_coverage": nominal,
        "available": not reasons,
        "unavailable_reasons": reasons,
        "availability_rule": {
            "declared_before_test_coverage_was_computed": True,
            "min_calibration_examples_per_horizon": min_calibration_examples,
            "max_coverage_error": max_coverage_error,
        },
        "calibration": {
            "split": "validation",
            "service_dates": [str(dates.min().date()), str(dates.max().date())],
            "examples": int(len(validation)),
            "residual": "actual minus predicted eta_revision_seconds, selected regression model",
            "quantile_rule": "lower tail: numpy 'lower' quantile; upper tail: 'higher' quantile",
            "reused_for_model_selection": True,
            "independent_of_model_selection": False,
            "uses_test_outcomes": False,
        },
        "test_evaluation": {
            "service_dates": [str(test_dates.min().date()), str(test_dates.max().date())],
            "examples": int(len(test)),
            "trips": int(test[TRIP].nunique()),
            "coverage": round(overall, 4),
            "coverage_interval_trip_clustered": _clustered_interval(
                test_inside, test[TRIP], replicates, seed, confidence_level
            ),
            "used_for": "coverage measurement and the predeclared availability rule only",
        },
        "by_horizon": by_horizon,
    }
