"""The supported inference entry point: load_predictor(bundle_dir).predict(record).

Loading verifies the bundle before anything is unpickled: the directory holds exactly the
listed files, bundle.json satisfies the committed schema and its own content hash, the
runtime matches the recorded Python, scikit-learn and numpy versions, and every artifact
matches its SHA-256. Unpickling runs code, so only load bundles built by
`bart-eta-bundle build` into a directory you control. Pass `expected_bundle_id` to pin a
specific build.

A record must contain exactly the context fields and the features the bundle's feature
schema lists. Nothing is filled in: missing, unexpected, null, mistyped or inconsistent
values are rejected (RecordError). A valid record with any categorical value unseen in
training is outside the models' demonstrated support: it gets status
"fallback_required" with no prediction, probability or interval, and the caller should
use BART's unadjusted published ETA.
"""

from __future__ import annotations

import json
import math
import platform
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import is_classifier, is_regressor
from sklearn.pipeline import Pipeline

from bart_reliability.serving.schema import (
    METADATA_FILENAME,
    SCHEMA_PATH,
    SchemaError,
    bundle_id,
    load_schema,
    sha256_file,
    validate,
)

DEFAULT_BUNDLE_DIR = Path("data/models/eta_revision_bundle")
FALLBACK_REASON = "input outside demonstrated model support"


class BundleError(ValueError):
    """Raised when a bundle is missing, malformed, altered or built for another runtime."""


class RecordError(ValueError):
    """Raised when an inference record does not match the bundle's feature schema."""


def runtime_environment() -> dict:
    import duckdb

    return {
        "python": platform.python_version(),
        "scikit-learn": sklearn.__version__,
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "joblib": joblib.__version__,
        "duckdb": duckdb.__version__,
    }


def _minor(version: str) -> str:
    return ".".join(version.split(".")[:2])


def load_predictor(
    bundle_dir: Path = DEFAULT_BUNDLE_DIR,
    expected_bundle_id: str | None = None,
    schema_path: Path = SCHEMA_PATH,
) -> Predictor:
    return Predictor.load(bundle_dir, expected_bundle_id, schema_path)


class Predictor:
    def __init__(self, metadata: dict, regression: Pipeline, classification: Pipeline):
        self.metadata = metadata
        self.regression = regression
        self.classification = classification
        self.features = [f["name"] for f in metadata["features"]]
        self._kinds = {f["name"]: f for f in metadata["features"]}
        self._context = [c["name"] for c in metadata["context_fields"]]
        self._known = {
            k: set(v) for k, v in metadata["categorical_handling"]["known_categories"].items()
        }
        self._domain = metadata["domain"]
        self._tz = ZoneInfo(self._domain["timezone"])

    # -- loading and verification ---------------------------------------------------

    @classmethod
    def load(
        cls,
        bundle_dir: Path,
        expected_bundle_id: str | None = None,
        schema_path: Path = SCHEMA_PATH,
    ) -> Predictor:
        bundle_dir = Path(bundle_dir)
        meta_path = bundle_dir / METADATA_FILENAME
        if not meta_path.is_file():
            raise BundleError(f"no {METADATA_FILENAME} in {bundle_dir}")
        try:
            metadata = json.loads(meta_path.read_text())
            validate(metadata, load_schema(schema_path))
        except (json.JSONDecodeError, SchemaError) as e:
            raise BundleError(f"bundle metadata rejected: {e}") from e
        if bundle_id(metadata) != metadata["bundle_id"]:
            raise BundleError("bundle metadata was altered: its content hash does not match")
        if expected_bundle_id is not None and metadata["bundle_id"] != expected_bundle_id:
            raise BundleError(f"bundle {metadata['bundle_id']} is not the pinned build")

        listed = {a["filename"] for a in metadata["artifacts"]} | {METADATA_FILENAME}
        present = {p.name for p in bundle_dir.iterdir()}
        if present != listed:
            raise BundleError(
                f"bundle files differ from metadata: missing {sorted(listed - present)}, "
                f"unexpected {sorted(present - listed)}"
            )
        built, here = metadata["environment"], runtime_environment()
        for name, same in (
            ("python", _minor(built["python"]) == _minor(here["python"])),
            ("scikit-learn", built["scikit-learn"] == here["scikit-learn"]),
            ("numpy", _minor(built["numpy"]) == _minor(here["numpy"])),
        ):
            if not same:
                raise BundleError(
                    f"bundle was built with {name} {built[name]}, running {here[name]}; rebuild it"
                )
        models = {}
        for artifact in metadata["artifacts"]:
            path = bundle_dir / artifact["filename"]
            if path.stat().st_size != artifact["bytes"] or sha256_file(path) != artifact["sha256"]:
                raise BundleError(f"{artifact['filename']} does not match its recorded SHA-256")
            models[artifact["role"]] = joblib.load(path)  # only after the hash check
        features = [f["name"] for f in metadata["features"]]
        for role, model in models.items():
            if not isinstance(model, Pipeline):
                raise BundleError(f"{role} artifact is not a scikit-learn Pipeline")
            if list(getattr(model, "feature_names_in_", [])) != features:
                raise BundleError(f"{role} model inputs differ from the feature schema")
            final = model.named_steps.get("model")
            role_ok = is_regressor(final) if role == "regression" else is_classifier(final)
            if not role_ok or type(final).__name__ != metadata["model"][role]["estimator"]:
                raise BundleError(f"{role} artifact holds the wrong kind of estimator")
        return cls(metadata, models["regression"], models["classification"])

    # -- inference ------------------------------------------------------------------

    def predict(self, record: Mapping) -> dict:
        """Predict for one point-in-time feature record (see docs/model_serving.md).

        Returns status "ok" with the model outputs, or status "fallback_required" with
        no model outputs when a categorical value was never seen in training.
        """
        row, unknown, published_eta = self._validate(record)
        if unknown:
            return self._response(
                "fallback_required",
                published_eta,
                unknown,
                reason=FALLBACK_REASON,
                fallback={"action": "use_published_eta", "eta": _iso(published_eta)},
            )
        frame = pd.DataFrame(
            {name: pd.Series([row[name]], dtype=self._dtype(name)) for name in self.features}
        )
        revision = float(self.regression.predict(frame)[0])
        probability = float(self.classification.predict_proba(frame)[0, 1])
        bucket = str(row["published_horizon_bucket_s"])
        return self._response(
            "ok",
            published_eta,
            [],
            predicted_eta_revision_seconds=revision,
            probability_absolute_revision_over_60_seconds=probability,
            predicted_final_published_eta=_iso(published_eta + timedelta(seconds=revision)),
            revision_intervals=[self._interval(bucket, revision, published_eta)],
        )

    def _response(self, status, published_eta, unknown, **fields) -> dict:
        """One key set for both statuses, so callers never guess which fields exist."""
        meta = self.metadata
        return {
            "status": status,
            "reason": None,
            "feature_schema_version": meta["feature_schema_version"],
            "model": {
                "name": meta["model"]["name"],
                "version": meta["model"]["version"],
                "bundle_id": meta["bundle_id"],
                "regression": meta["model"]["regression"]["candidate"],
                "classification": meta["model"]["classification"]["candidate"],
            },
            "training_data_cutoff": meta["training_data"]["training_data_cutoff_utc"],
            "calibration_data_cutoff": meta["training_data"]["calibration_data_cutoff_utc"],
            "provisional": True,
            "published_eta": _iso(published_eta),
            "predicted_eta_revision_seconds": None,
            "probability_absolute_revision_over_60_seconds": None,
            "predicted_final_published_eta": None,
            "revision_intervals": [],
            "unknown_categories": unknown,
            "fallback": None,
            **fields,
        }

    def _predict_frame(self, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """Batch predictions on a model-ready frame. Used to verify parity, not served."""
        if list(frame.columns) != self.features:
            raise RecordError("frame columns differ from the feature schema")
        return self.regression.predict(frame), self.classification.predict_proba(frame)[:, 1]

    def _dtype(self, name: str):
        return "float64" if self._kinds[name]["kind"] == "numeric" else object

    def _interval(self, bucket: str, revision: float, published_eta: datetime) -> dict:
        iv = self.metadata["interval"]
        h = iv["by_horizon"][bucket]
        entry = {
            "method": iv["method"],
            "status": iv["status"],
            "nominal_coverage": iv["nominal_coverage"],
            "available": iv["available"],
            "unavailable_reasons": iv["unavailable_reasons"],
            "lower_revision_seconds": None,
            "upper_revision_seconds": None,
            "lower_final_published_eta": None,
            "upper_final_published_eta": None,
            "empirical_test_coverage": {
                "overall": iv["test_evaluation"]["coverage"],
                "this_horizon": h["test_coverage"],
                "this_horizon_interval_trip_clustered": h["test_coverage_interval_trip_clustered"],
                "test_service_dates": iv["test_evaluation"]["service_dates"],
            },
            "calibration": iv["calibration"],
            "calibration_examples_this_horizon": h["calibration_examples"],
            "residual_quantiles_this_horizon_s": h["residual_quantiles_s"],
            "independently_calibrated": iv["calibration"]["independent_of_model_selection"],
        }
        if iv["available"]:
            lo, hi = (revision + q for q in h["residual_quantiles_s"])
            entry |= {
                "lower_revision_seconds": lo,
                "upper_revision_seconds": hi,
                "lower_final_published_eta": _iso(published_eta + timedelta(seconds=lo)),
                "upper_final_published_eta": _iso(published_eta + timedelta(seconds=hi)),
            }
        return entry

    def _validate(self, record: Mapping) -> tuple[dict, list[dict], datetime]:
        if not isinstance(record, Mapping):
            raise RecordError("a record must be a mapping of field names to values")
        expected = set(self._context) | set(self.features)
        missing, unexpected = sorted(expected - set(record)), sorted(set(record) - expected)
        if missing or unexpected:
            raise RecordError(f"missing fields {missing}; unexpected fields {unexpected}")
        version = record["feature_schema_version"]
        if version != self.metadata["feature_schema_version"]:
            raise RecordError(
                f"feature_schema_version {version!r} does not match "
                f"{self.metadata['feature_schema_version']!r}"
            )
        snapshot = _timestamp(record, "snapshot_collected_at")
        published_eta = _timestamp(record, "published_eta")

        row, unknown = {}, []
        for name in self.features:
            spec, value = self._kinds[name], record[name]
            if spec["input_type"] == "number":
                if not isinstance(value, int | float) or isinstance(value, bool):
                    raise RecordError(f"{name} must be a number, got {type(value).__name__}")
                if not math.isfinite(value):
                    raise RecordError(f"{name} must be finite")
                row[name] = float(value)
            elif spec["input_type"] == "integer":
                if not isinstance(value, int) or isinstance(value, bool):
                    raise RecordError(f"{name} must be an integer, got {type(value).__name__}")
                row[name] = str(value)
            else:
                if not isinstance(value, str) or not value:
                    raise RecordError(f"{name} must be a non-empty string")
                row[name] = value
            if spec["kind"] == "categorical" and row[name] not in self._known.get(name, set()):
                unknown.append({"feature": name, "value": record[name]})

        domain = self._domain
        bucket, horizon = record["published_horizon_bucket_s"], record["published_horizon_s"]
        if bucket not in domain["published_horizon_buckets_s"]:
            raise RecordError(f"published_horizon_bucket_s {bucket} is not a served horizon")
        if abs(horizon - bucket) > domain["horizon_tolerance_s"]:
            raise RecordError("published_horizon_s is outside the bucket's tolerance")
        elapsed = (published_eta - snapshot).total_seconds()
        if abs(elapsed - horizon) > 0.5:
            raise RecordError(
                "published_horizon_s does not equal published_eta minus snapshot_collected_at"
            )
        lo, hi = domain["hour_local_range"]
        hour = record["hour_local"]
        if not lo <= hour <= hi or hour != snapshot.astimezone(self._tz).hour:
            raise RecordError("hour_local is not the Pacific hour of snapshot_collected_at")
        return row, sorted(unknown, key=lambda u: u["feature"]), published_eta


def _timestamp(record: Mapping, name: str) -> datetime:
    value = record[name]
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as e:
            raise RecordError(f"{name} is not an ISO-8601 timestamp") from e
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RecordError(f"{name} must be a timezone-aware timestamp")
    return value


def _iso(ts: datetime) -> str:
    """UTC, rounded to the nearest second."""
    utc = ts.astimezone(ZoneInfo("UTC"))
    rounded = (utc + timedelta(microseconds=500_000)).replace(microsecond=0)
    return rounded.strftime("%Y-%m-%dT%H:%M:%SZ")
