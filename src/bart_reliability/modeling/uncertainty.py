"""Paired cluster bootstrap for model-minus-baseline differences on the test period.

The primary resampling unit is the **trip run** (service date + trip_id). When a trip is
drawn, every stop-arrival event of that trip and all of their published-time horizons
(5/10/15 minutes) enter the replicate together, with one weight. Events of the same trip
share conditions (its delay, its crew, its path), so they are not independent.
Resampling **events** instead is kept only as a sensitivity analysis; its intervals are
narrower because it treats those correlated events as independent. Rows are never
resampled on their own. Every prediction set is scored on the same resamples, so the
differences are paired.

Even trip-clustered intervals are conditional on the evaluated test day. They do not
capture day-to-day variability or conditions shared by many trips at once (a
system-wide delay, the weather), so they cannot establish generalization to future
service days.
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

TRIP = "trip_run_key"
EVENT = "event_id"
TRIP_SCOPE_NOTE = (
    "Primary intervals: paired percentile bootstrap over trip runs (service date + "
    "trip_id); a drawn trip brings every stop-arrival event and every published-time "
    "horizon it has. They are conditional on the single test day: they do not capture "
    "day-to-day variability, and may not capture system-wide conditions shared by many "
    "trips, so they cannot establish generalization to future service days."
)
EVENT_SENSITIVITY_NOTE = (
    "Sensitivity only: the same bootstrap with stop-arrival events as the unit. These "
    "intervals are narrower than the trip-clustered ones because events from the same "
    "trip are correlated, and resampling them independently understates the uncertainty."
)
# Direction in which each metric improves.
BETTER = {"mae_s": "lower", "brier": "lower", "pr_auc": "higher"}


def trip_run_key(service_date: pd.Series, trip_id: pd.Series) -> pd.Series:
    """One key per trip run. BART reuses trip_id on every service day, so the service
    date is part of the key: the same trip_id on two dates is two runs."""
    dates = pd.to_datetime(service_date).dt.strftime("%Y-%m-%d")
    return dates + ":" + trip_id.astype(str)


def cluster_resample_weights(
    cluster_ids: pd.Series, replicates: int, seed: int
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield (row weights, cluster counts) per replicate.

    Each replicate draws as many clusters as there are, with replacement. A row's weight
    is the number of times its cluster was drawn, so a cluster's rows always move
    together. Clusters are ordered by key, so results depend only on the data and seed.
    """
    codes, clusters = pd.factorize(cluster_ids, sort=True)
    n = len(clusters)
    rng = np.random.default_rng(seed)
    for _ in range(replicates):
        counts = np.bincount(rng.integers(0, n, size=n), minlength=n)
        yield counts[codes], counts


def bootstrap_draws(
    rows: pd.DataFrame, reg: dict, prob: dict, replicates: int, seed: int, cluster: str = TRIP
) -> dict:
    """Per-replicate metric values for every named prediction set.

    rows: the `cluster` column, horizon_bucket_s, eta_revision_seconds, large_revision.
    reg / prob: name -> regression predictions / large-revision probabilities.
    Returns {name: {"mae_s": {"overall": arr, "<bucket>": arr}, "brier": arr, "pr_auc": arr}}.
    """
    y = rows["eta_revision_seconds"].to_numpy(dtype=float)
    yc = rows["large_revision"].to_numpy(dtype=int)
    horizons = {
        str(h): (rows["horizon_bucket_s"] == h).to_numpy()
        for h in sorted(rows["horizon_bucket_s"].unique())
    }
    abs_err = {name: np.abs(np.asarray(p, dtype=float) - y) for name, p in reg.items()}
    sq_err = {name: (np.asarray(p, dtype=float) - yc) ** 2 for name, p in prob.items()}
    out = {
        name: {
            "mae_s": {
                "overall": np.empty(replicates),
                **{h: np.empty(replicates) for h in horizons},
            }
        }
        for name in reg
    }
    for name in prob:
        out.setdefault(name, {})
        out[name]["brier"] = np.empty(replicates)
        out[name]["pr_auc"] = np.empty(replicates)

    for b, (w, _) in enumerate(cluster_resample_weights(rows[cluster], replicates, seed)):
        total = w.sum()
        for name, err in abs_err.items():
            out[name]["mae_s"]["overall"][b] = (w * err).sum() / total
            for h, m in horizons.items():
                # Undefined (NaN) if a replicate drew no event with this horizon.
                weight = w[m].sum()
                out[name]["mae_s"][h][b] = (w[m] * err[m]).sum() / weight if weight else np.nan
        has_positive = (w * yc).sum() > 0
        for name, err in sq_err.items():
            out[name]["brier"][b] = (w * err).sum() / total
            out[name]["pr_auc"][b] = (
                average_precision_score(yc, prob[name], sample_weight=w) if has_positive else np.nan
            )
    return out


def percentile_interval(values: np.ndarray, confidence: float) -> tuple[float, float]:
    """Percentile interval (numpy's linear interpolation), ignoring undefined replicates."""
    tail = (1 - confidence) / 2
    lo, hi = np.nanquantile(values, [tail, 1 - tail])
    return float(lo), float(hi)


def interpret(lo: float, hi: float, better: str) -> str:
    improved = hi < 0 if better == "lower" else lo > 0
    worse = lo > 0 if better == "lower" else hi < 0
    if improved:
        return "improvement distinguishable from zero within this test day only"
    if worse:
        return "worse than the baseline within this test day"
    return "interval includes zero: the available test day does not establish an improvement"


def paired_difference(
    draws: dict,
    observed: dict,
    model: str,
    baseline: str,
    metric: str,
    confidence: float,
    horizon: str | None = None,
) -> dict:
    """model − baseline for one metric: observed value, interval, and share of replicates
    in which the model is better."""

    def pick(d, name):
        v = d[name][metric]
        return v[horizon or "overall"] if metric == "mae_s" else v

    diffs = pick(draws, model) - pick(draws, baseline)
    observed_diff = pick(observed, model) - pick(observed, baseline)
    lo, hi = percentile_interval(diffs, confidence)
    better = BETTER[metric]
    valid = diffs[~np.isnan(diffs)]
    share = float(np.mean(valid < 0 if better == "lower" else valid > 0))
    return {
        "observed": round(float(observed_diff), 4),
        "ci_low": round(lo, 4),
        "ci_high": round(hi, 4),
        "share_of_replicates_model_better": round(share, 4),
        "better_when": better,
        "undefined_replicates": int(np.isnan(diffs).sum()),
        "interpretation": interpret(lo, hi, better),
    }


def observed_values(rows: pd.DataFrame, reg: dict, prob: dict) -> dict:
    """The same statistics on the full evaluation set (every cluster drawn once)."""
    y = rows["eta_revision_seconds"].to_numpy(dtype=float)
    yc = rows["large_revision"].to_numpy(dtype=int)
    out = {}
    for name, p in reg.items():
        err = np.abs(np.asarray(p, dtype=float) - y)
        out[name] = {"mae_s": {"overall": float(err.mean())}}
        for h in sorted(rows["horizon_bucket_s"].unique()):
            m = (rows["horizon_bucket_s"] == h).to_numpy()
            out[name]["mae_s"][str(h)] = float(err[m].mean())
    for name, p in prob.items():
        out.setdefault(name, {})
        out[name]["brier"] = float(((np.asarray(p, dtype=float) - yc) ** 2).mean())
        out[name]["pr_auc"] = float(average_precision_score(yc, p)) if yc.any() else np.nan
    return out


def compare(
    rows: pd.DataFrame,
    draws: dict,
    observed: dict,
    reg_model: str,
    prob_model: str,
    baseline: str,
    confidence: float,
) -> dict:
    """The audited differences: MAE overall and per horizon, Brier score, PR-AUC."""
    horizons = [str(h) for h in sorted(rows["horizon_bucket_s"].unique())]
    return {
        "mae_s": {
            "overall": paired_difference(draws, observed, reg_model, baseline, "mae_s", confidence),
            "by_horizon": {
                h: paired_difference(
                    draws, observed, reg_model, baseline, "mae_s", confidence, horizon=h
                )
                for h in horizons
            },
        },
        "brier": paired_difference(draws, observed, prob_model, baseline, "brier", confidence),
        "pr_auc": paired_difference(draws, observed, prob_model, baseline, "pr_auc", confidence),
    }
