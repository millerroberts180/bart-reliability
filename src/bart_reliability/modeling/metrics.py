"""Regression, classification and calibration metrics. Undefined values are None."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score


def _r(x: float | None, digits: int = 4) -> float | None:
    return None if x is None else round(float(x), digits)


def regression_metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    y, pred = np.asarray(y, dtype=float), np.asarray(pred, dtype=float)
    if len(y) == 0:
        return {"n": 0, "mae_s": None, "median_ae_s": None, "rmse_s": None, "mean_error_s": None}
    err = pred - y
    return {
        "n": int(len(y)),
        "mae_s": _r(np.mean(np.abs(err)), 2),
        "median_ae_s": _r(np.median(np.abs(err)), 2),
        "rmse_s": _r(np.sqrt(np.mean(err**2)), 2),
        # Positive: predictions are later (larger revisions) than what happened.
        "mean_error_s": _r(np.mean(err), 2),
    }


def classification_metrics(
    y: np.ndarray, prob: np.ndarray, threshold: float, bins: int = 10
) -> dict:
    y = np.asarray(y, dtype=int)
    prob = np.asarray(prob, dtype=float)
    n, positives = len(y), int(y.sum())
    predicted = prob >= threshold
    tp = int((predicted & (y == 1)).sum())
    both_classes = 0 < positives < n
    table = calibration_table(y, prob, bins)
    return {
        "n": n,
        "positives": positives,
        "prevalence": _r(positives / n) if n else None,
        "predicted_positive": int(predicted.sum()),
        "precision": _r(tp / predicted.sum()) if predicted.sum() else None,
        "recall": _r(tp / positives) if positives else None,
        "pr_auc": _r(average_precision_score(y, prob)) if positives else None,
        "roc_auc": _r(roc_auc_score(y, prob)) if both_classes else None,
        "brier": _r(np.mean((prob - y) ** 2)) if n else None,
        "ece": _r(
            sum(b["n"] / n * abs(b["observed_rate"] - b["mean_predicted"]) for b in table if b["n"])
        )
        if n
        else None,
        "calibration": table,
    }


def calibration_table(y: np.ndarray, prob: np.ndarray, bins: int = 10) -> list[dict]:
    """Equal-width probability bins; the last bin includes 1.0."""
    y, prob = np.asarray(y, dtype=float), np.asarray(prob, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    index = np.clip(np.digitize(prob, edges[1:-1], right=False), 0, bins - 1)
    out = []
    for b in range(bins):
        mask = index == b
        count = int(mask.sum())
        out.append(
            {
                "bin": f"[{edges[b]:.1f}, {edges[b + 1]:.1f}{']' if b == bins - 1 else ')'}",
                "n": count,
                "mean_predicted": _r(prob[mask].mean()) if count else None,
                "observed_rate": _r(y[mask].mean()) if count else None,
            }
        )
    return out


def relative_to(model: dict, baseline: dict, keys: tuple[str, ...]) -> dict:
    """model − baseline per metric, in units and percent. Negative error = improvement."""
    out = {}
    for k in keys:
        a, b = model.get(k), baseline.get(k)
        if a is None or b is None:
            out[k] = {"difference": None, "pct": None}
            continue
        out[k] = {"difference": _r(a - b, 4), "pct": _r(100 * (a - b) / b, 2) if b else None}
    return out
