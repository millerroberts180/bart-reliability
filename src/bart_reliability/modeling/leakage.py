"""Leakage guards on the model frame (the SQL point-in-time checks live in features.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from bart_reliability.modeling.config import LeakageError, ModelConfig
from bart_reliability.modeling.features import FEATURE_KINDS, PROHIBITED_COLUMNS

# Diagnostic alarm, not a proof of absence: one feature separating large revisions this
# well on training rows is far stronger than anything known to be available before the
# outcome, so the run stops for investigation. Passing it says nothing about leaks that
# act through combinations of features. The primary leakage controls are structural: the
# point-in-time SQL checks, the prohibited-field catalog, split isolation, train-only
# aggregation, and the perturbation tests.
SUSPICIOUS_SINGLE_FEATURE_AUC = 0.95


def check_model_inputs(columns: list[str], cfg: ModelConfig) -> None:
    """The exact model input columns must be the configured point-in-time features."""
    if list(columns) != list(cfg.features):
        raise LeakageError(f"model inputs {columns} differ from configured {list(cfg.features)}")
    leaked = sorted(set(columns) & PROHIBITED_COLUMNS)
    unknown = sorted(set(columns) - FEATURE_KINDS.keys())
    if leaked or unknown:
        raise LeakageError(f"model inputs include prohibited {leaked} or unknown {unknown}")


def single_feature_alarm(train: pd.DataFrame, cfg: ModelConfig) -> dict:
    """Alarm: ROC-AUC of each feature alone for large revisions on training rows.

    Numeric features are scored directly (direction-free). Categorical features are
    scored by their training-row large-revision rate, which is optimistic, so it errs
    toward flagging. Raises LeakageError if any feature reaches the ceiling.
    """
    y = train["large_revision"].to_numpy()
    if y.min() == y.max():
        return {}
    scores = {}
    for name in cfg.features:
        if FEATURE_KINDS[name] == "numeric":
            x = train[name].to_numpy(dtype=float)
            x = np.where(np.isnan(x), np.nanmedian(x), x)
        else:
            x = train.groupby(name)["large_revision"].transform("mean").to_numpy()
        auc = roc_auc_score(y, x) if len(np.unique(x)) > 1 else 0.5
        scores[name] = round(float(max(auc, 1 - auc)), 4)
    suspicious = {k: v for k, v in scores.items() if v >= SUSPICIOUS_SINGLE_FEATURE_AUC}
    if suspicious:
        raise LeakageError(
            f"single features predict large revisions implausibly well: {suspicious}"
        )
    return scores
