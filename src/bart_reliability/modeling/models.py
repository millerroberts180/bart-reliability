"""Candidate models: a regularized linear family and a gradient-boosted tree family."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import HuberRegressor, LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from bart_reliability.modeling.config import ModelConfig

REGRESSION = "regression"
CLASSIFICATION = "classification"


@dataclass(frozen=True)
class Candidate:
    name: str
    family: str  # "linear" or "tree"
    task: str  # REGRESSION or CLASSIFICATION
    params: dict = field(default_factory=dict)


def candidates(cfg: ModelConfig) -> list[Candidate]:
    """The small, documented grid. Linear candidates come first, so they win ties."""
    out = []
    for alpha in cfg.linear.huber_alpha:
        out.append(
            Candidate(f"linear_huber_alpha={alpha:g}", "linear", REGRESSION, {"alpha": alpha})
        )
    for leaves in cfg.tree.max_leaf_nodes:
        out.append(
            Candidate(f"tree_hgb_leaves={leaves}", "tree", REGRESSION, {"max_leaf_nodes": leaves})
        )
    for c in cfg.linear.logistic_c:
        out.append(Candidate(f"linear_logistic_C={c:g}", "linear", CLASSIFICATION, {"C": c}))
    for leaves in cfg.tree.max_leaf_nodes:
        out.append(
            Candidate(
                f"tree_hgb_leaves={leaves}", "tree", CLASSIFICATION, {"max_leaf_nodes": leaves}
            )
        )
    return out


def build_estimator(candidate: Candidate, cfg: ModelConfig) -> Pipeline:
    """An unfitted pipeline. Encoders and scalers are fitted with the model, on train only."""
    numeric, categorical = list(cfg.numeric_features), list(cfg.categorical_features)
    if candidate.family == "linear":
        prep = ColumnTransformer(
            [
                (
                    "num",
                    Pipeline(
                        [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
                    ),
                    numeric,
                ),
                ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
            ],
            verbose_feature_names_out=False,
        )
        if candidate.task == REGRESSION:
            model = HuberRegressor(
                alpha=candidate.params["alpha"],
                epsilon=cfg.linear.huber_epsilon,
                max_iter=cfg.linear.max_iter,
            )
        else:
            model = LogisticRegression(C=candidate.params["C"], max_iter=cfg.linear.max_iter)
    else:
        # Unknown categories become missing, which the trees handle natively.
        prep = ColumnTransformer(
            [
                ("num", "passthrough", numeric),
                (
                    "cat",
                    OrdinalEncoder(
                        handle_unknown="use_encoded_value",
                        unknown_value=np.nan,
                        encoded_missing_value=np.nan,
                    ),
                    categorical,
                ),
            ],
            verbose_feature_names_out=False,
        )
        common = dict(
            max_leaf_nodes=candidate.params["max_leaf_nodes"],
            learning_rate=cfg.tree.learning_rate,
            max_iter=cfg.tree.max_iter,
            min_samples_leaf=cfg.tree.min_samples_leaf,
            l2_regularization=cfg.tree.l2_regularization,
            categorical_features=list(range(len(numeric), len(numeric) + len(categorical))),
            early_stopping=False,
            random_state=cfg.seed,
        )
        if candidate.task == REGRESSION:
            model = HistGradientBoostingRegressor(loss="absolute_error", **common)
        else:
            model = HistGradientBoostingClassifier(**common)
    return Pipeline([("prep", prep), ("model", model)])


def predict(estimator: Pipeline, task: str, X) -> np.ndarray:
    if task == REGRESSION:
        return estimator.predict(X)
    return estimator.predict_proba(X)[:, 1]


def linear_coefficients(estimator: Pipeline, top: int = 15) -> list[dict]:
    """Largest standardized coefficients of a fitted linear pipeline, for the report."""
    names = estimator.named_steps["prep"].get_feature_names_out()
    coef = np.ravel(estimator.named_steps["model"].coef_)
    order = np.argsort(-np.abs(coef))[:top]
    return [{"feature": str(names[i]), "coefficient": round(float(coef[i]), 4)} for i in order]
