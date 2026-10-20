"""A locked model pair from an earlier bundle, and category support on the test rows.

The locked pair is loaded through the bundle verifier (schema, content hash, pinned
bundle_id, artifact SHA-256 and runtime versions) before anything is fitted, so a wrong
or altered bundle stops the run before any test prediction exists. It is only ever used
to predict on the test rows: it is never refitted or recalibrated.

Category support follows the serving rule: a row whose categorical value was never seen
by a model's encoders is outside that model's demonstrated support, and the bundle would
return `fallback_required` for it. In batch evaluation every row is still scored, as the
modeling pipeline always has; the support counts and the shared-support subset show how
much of the comparison rests on such rows.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from bart_reliability.modeling.config import ModelConfig, ModelConfigError
from bart_reliability.serving.predictor import Predictor


@dataclass(frozen=True)
class LockedModels:
    name: str
    bundle_id: str
    model_version: str
    regression_candidate: str
    classification_candidate: str
    train_service_dates: list[str]
    validation_service_dates: list[str]
    artifacts: list[dict]
    regression: Pipeline
    classification: Pipeline

    def describe(self) -> dict:
        return {
            "name": self.name,
            "bundle_id": self.bundle_id,
            "model_version": self.model_version,
            "regression": self.regression_candidate,
            "classification": self.classification_candidate,
            "train_service_dates": self.train_service_dates,
            "validation_service_dates": self.validation_service_dates,
            "artifacts": self.artifacts,
            "refitted": False,
            "scored_on": "test rows only",
        }


def load_locked_models(cfg: ModelConfig) -> LockedModels | None:
    """The configured locked pair, verified, or None when no comparison is configured."""
    locked = cfg.locked_comparison
    if locked is None:
        return None
    predictor = Predictor.load(locked.bundle_dir, expected_bundle_id=locked.bundle_id)
    if predictor.features != list(cfg.features):
        raise ModelConfigError(
            f"locked bundle features {predictor.features} differ from the configured "
            f"features {list(cfg.features)}"
        )
    meta = predictor.metadata
    return LockedModels(
        name=locked.name,
        bundle_id=meta["bundle_id"],
        model_version=meta["model"]["version"],
        regression_candidate=meta["model"]["regression"]["candidate"],
        classification_candidate=meta["model"]["classification"]["candidate"],
        train_service_dates=meta["training_data"]["train_service_dates"],
        validation_service_dates=meta["training_data"]["validation_service_dates"],
        artifacts=[
            {k: a[k] for k in ("role", "filename", "sha256", "bytes")} for a in meta["artifacts"]
        ],
        regression=predictor.regression,
        classification=predictor.classification,
    )


def known_categories(estimator: Pipeline, categorical: list[str]) -> dict[str, set[str]]:
    """Categories each categorical feature's encoder saw when the model was fitted."""
    cats = estimator.named_steps["prep"].named_transformers_["cat"].categories_
    return {name: {str(v) for v in values} for name, values in zip(categorical, cats, strict=True)}


def pair_categories(regression: Pipeline, classification: Pipeline, categorical: list[str]):
    """One category set for a model pair; both models must have seen the same values."""
    reg = known_categories(regression, categorical)
    if known_categories(classification, categorical) != reg:
        raise ValueError("the regression and classification models saw different categories")
    return reg


def outside_support(rows: pd.DataFrame, known: dict[str, set[str]]) -> np.ndarray:
    """True for rows with at least one categorical value the model never saw."""
    mask = np.zeros(len(rows), dtype=bool)
    for name, values in known.items():
        mask |= ~rows[name].astype(str).isin(values).to_numpy()
    return mask


def support_report(
    rows: pd.DataFrame, known_by_model: dict[str, dict[str, set[str]]]
) -> tuple[dict, np.ndarray]:
    """Rows outside each model's support (by feature and value), and the shared-support
    mask: rows every listed model has full support for."""
    out, shared = {}, np.ones(len(rows), dtype=bool)
    for model, known in known_by_model.items():
        mask = outside_support(rows, known)
        shared &= ~mask
        by_feature = {}
        for name, values in known.items():
            unseen = ~rows[name].astype(str).isin(values)
            if unseen.any():
                counts = rows.loc[unseen, name].astype(str).value_counts().sort_index()
                by_feature[name] = {str(k): int(v) for k, v in counts.items()}
        out[model] = {
            **_counts(rows, mask),
            "share_of_examples": _share(mask),
            "unseen_values_by_feature": by_feature,
        }
    report = {
        "rule": (
            "A row is outside a model's support if any categorical value was never seen by "
            "that model's encoders. The bundle would return fallback_required for it; batch "
            "evaluation still scores every row."
        ),
        "examples": int(len(rows)),
        "outside_support": out,
        "shared_support": {**_counts(rows, shared), "share_of_examples": _share(shared)},
    }
    return report, shared


def _counts(rows: pd.DataFrame, mask: np.ndarray) -> dict:
    sub = rows[mask]
    return {
        "examples": int(mask.sum()),
        "events": int(sub["event_id"].nunique()),
        "trips": int(sub["trip_run_key"].nunique()),
    }


def _share(mask: np.ndarray) -> float:
    return round(float(mask.mean()), 6) if len(mask) else 0.0
