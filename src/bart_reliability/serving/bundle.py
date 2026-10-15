"""Build the inference bundle deterministically from a warehouse (the training snapshot).

Steps: run the modeling pipeline (deterministic for a warehouse and config) -> copy the
two selected fitted pipelines byte for byte -> calibrate the provisional interval on
validation residuals -> write bundle.json -> load the bundle through the full
verification path -> confirm exact parity with the pipeline's own predictions, in batch
for every validation and test row and one record at a time for a fixed sample -> replace
the output directory atomically. Nothing in bundle.json depends on paths or wall-clock
time, so rebuilding from the same warehouse and config gives identical bytes.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd

from bart_reliability.modeling.config import ModelConfig
from bart_reliability.modeling.pipeline import load_frame, run_pipeline
from bart_reliability.serving.config import BundleConfig
from bart_reliability.serving.interval import calibrate_interval
from bart_reliability.serving.predictor import BundleError, Predictor, runtime_environment
from bart_reliability.serving.schema import (
    METADATA_FILENAME,
    SCHEMA_PATH,
    bundle_id,
    canonical_json,
    constant,
    load_schema,
    sha256_file,
)

ROLES = {"regression": "regression.joblib", "classification": "classification.joblib"}
CATEGORICAL_MECHANISM = {
    "tree": (
        "OrdinalEncoder fitted on training rows (known_categories). Unseen values never "
        "reach the model: predict() returns fallback_required instead of using the "
        "trees' missing-value branch"
    ),
    "linear": (
        "OneHotEncoder fitted on training rows (known_categories). Unseen values never "
        "reach the model: predict() returns fallback_required"
    ),
}
TEST_DAY_STATUS = (
    "The test service dates have been used to evaluate the selected models and to decide "
    "interval availability. They are not an untouched holdout for later model versions, "
    "which must be evaluated on later service days."
)


@dataclass(frozen=True)
class BuildResult:
    bundle_dir: Path
    run_dir: Path
    metadata: dict


def check_feature_contract(cfg: ModelConfig, contract: list[dict]) -> None:
    """The configured model features must be exactly the committed schema, in order."""
    configured = [(n, "numeric") for n in cfg.numeric_features] + [
        (n, "categorical") for n in cfg.categorical_features
    ]
    committed = [(f["name"], f["kind"]) for f in contract]
    if configured != committed:
        raise BundleError(
            "config/eta_model.toml features differ from the committed feature schema; "
            "update config/eta_model_bundle.schema.json and bump feature_schema_version"
        )


def served_records(con: duckdb.DuckDBPyConnection, cfg: ModelConfig, version: str) -> pd.DataFrame:
    """Validation and test rows as inference records, built from point-in-time columns
    only: the feature table, the snapshot time and the published ETA. No label column
    is read."""
    features = ", ".join(f"f.{c}" for c in cfg.features)
    df = con.execute(
        f"""
        SELECT m.event_id, m.published_horizon_bucket_s AS horizon_bucket_s, m.split,
               f.prediction_collected_at AS snapshot_collected_at,
               e.published_estimate AS published_eta, {features}
        FROM eta_model_frame m
        JOIN eta_model_examples e USING (event_id, published_horizon_bucket_s)
        JOIN eta_model_features f USING (event_id, published_horizon_bucket_s)
        WHERE m.split IN ('validation', 'test')
        ORDER BY m.event_id, m.published_horizon_bucket_s
        """
    ).df()
    df["feature_schema_version"] = version
    return df


def to_record(row: pd.Series, fields: list[str]) -> dict:
    out = {}
    for name in fields:
        value = row[name]
        if isinstance(value, pd.Timestamp):
            value = value.isoformat()
        elif isinstance(value, np.integer):
            value = int(value)
        elif isinstance(value, np.floating):
            value = float(value)
        out[name] = value
    return out


def build_bundle(
    db_path: Path,
    cfg: ModelConfig,
    bcfg: BundleConfig,
    out_dir: Path | None = None,
    run_dir: Path | None = None,
    schema_path: Path = SCHEMA_PATH,
) -> BuildResult:
    schema = load_schema(schema_path)
    contract = constant(schema, "features")
    check_feature_contract(cfg, contract)
    version = constant(schema, "feature_schema_version")
    domain = constant(schema, "domain")

    run = run_pipeline(db_path, cfg, run_dir)
    built = run.manifest["feature_build"]
    if (built["horizon_targets_s"], built["horizon_tolerance_s"]) != (
        domain["published_horizon_buckets_s"],
        domain["horizon_tolerance_s"],
    ):
        raise BundleError("the warehouse's horizon settings differ from the committed domain")

    with duckdb.connect(str(run.out_dir / "features.duckdb"), read_only=True) as con:
        con.execute("SET TimeZone = 'UTC'")
        frame = load_frame(con, cfg)
        records = served_records(con, cfg, version)
    preds = pd.read_parquet(run.out_dir / "predictions.parquet")
    selection = run.metrics["selection"]
    names = {task: selection[task]["selected"] for task in ROLES}
    keyed = frame[frame["split"].isin(["validation", "test"])].merge(
        preds[
            [
                "event_id",
                "horizon_bucket_s",
                "split",
                f"revision_s__{names['regression']}",
                f"large_revision_probability__{names['classification']}",
            ]
        ],
        on=["event_id", "horizon_bucket_s", "split"],
        how="left",
        validate="one_to_one",
    )
    keyed = keyed.rename(
        columns={
            f"revision_s__{names['regression']}": "predicted_revision_s",
            f"large_revision_probability__{names['classification']}": "predicted_probability",
        }
    )
    if keyed["predicted_revision_s"].isna().any() or keyed["predicted_probability"].isna().any():
        raise BundleError("the modeling run has no prediction for some validation/test rows")

    interval = calibrate_interval(
        keyed[keyed["split"] == "validation"],
        keyed[keyed["split"] == "test"],
        bcfg.nominal_coverage,
        bcfg.min_calibration_examples_per_horizon,
        bcfg.max_coverage_error,
        cfg.bootstrap_replicates,
        cfg.seed,
        cfg.bootstrap_confidence_level,
    )

    out_dir = out_dir or bcfg.output_dir
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_dir.with_name(f".{out_dir.name}.building")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        artifacts = []
        for role, filename in ROLES.items():
            source = run.out_dir / "models" / f"{role}__{names[role]}.joblib"
            shutil.copyfile(source, tmp / filename)
            artifacts.append(
                {
                    "role": role,
                    "filename": filename,
                    "sha256": sha256_file(tmp / filename),
                    "bytes": (tmp / filename).stat().st_size,
                }
            )
        metadata = _metadata(schema, cfg, bcfg, run, names, artifacts, interval, contract)
        metadata["bundle_id"] = bundle_id(metadata)
        _write(tmp, metadata)
        # Verify through the same path a consumer uses, then record the parity results.
        predictor = Predictor.load(tmp, schema_path=schema_path)
        metadata["verification"] = _verify(predictor, keyed, records, cfg, bcfg)
        metadata["bundle_id"] = bundle_id(metadata)
        _write(tmp, metadata)
        Predictor.load(tmp, expected_bundle_id=metadata["bundle_id"], schema_path=schema_path)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    old = out_dir.with_name(f".{out_dir.name}.old")
    shutil.rmtree(old, ignore_errors=True)
    if out_dir.exists():
        out_dir.rename(old)
    tmp.rename(out_dir)
    shutil.rmtree(old, ignore_errors=True)
    return BuildResult(out_dir, run.out_dir, metadata)


def _metadata(schema, cfg, bcfg, run, names, artifacts, interval, contract) -> dict:
    samples = run.metrics["samples"]
    bounds = run.manifest["split_bounds_utc"]
    selected = {}
    for role, filename in ROLES.items():
        family = names[role].split("_", 1)[0]
        selected[role] = {
            "candidate": names[role],
            "family": family,
            "estimator": None,  # filled from the fitted artifact below
            "selected_by": run.metrics["selection"][role]["criterion"],
            "refitted_on_validation": run.metrics["selection"]["refitted_on_validation"],
            "artifact": filename,
        }
    for role in ROLES:
        model = joblib.load(run.out_dir / "models" / f"{role}__{names[role]}.joblib")
        selected[role]["estimator"] = type(model.named_steps["model"]).__name__
        cats = model.named_steps["prep"].named_transformers_["cat"].categories_
        selected[role]["known_categories"] = {
            name: [str(v) for v in values]
            for name, values in zip(cfg.categorical_features, cats, strict=True)
        }
        params = model.named_steps["model"].get_params()
        selected[role]["parameters"] = json.loads(json.dumps(params, default=str))
    known = selected["regression"].pop("known_categories")
    if selected["classification"].pop("known_categories") != known:
        raise BundleError("the selected models were fitted on different categories")
    if sorted(known) != sorted(cfg.categorical_features):
        raise BundleError("known categories do not cover every categorical feature")
    parameters = {role: selected[role].pop("parameters") for role in ROLES}
    training = {
        "warehouse": run.manifest["warehouse_data"],
        "frame_fingerprint_sha256": run.manifest["frame_fingerprint_sha256"],
        "train_service_dates": samples["train"]["service_dates"],
        "validation_service_dates": samples["validation"]["service_dates"],
        "test_service_dates": samples["test"]["service_dates"],
        # Latest outcome (label confirmation) used to fit the models, and to calibrate
        # the interval.
        "training_data_cutoff_utc": bounds["train"]["last_label_known"],
        "calibration_data_cutoff_utc": bounds["validation"]["last_label_known"],
        "quality_tiers": list(cfg.quality_tiers),
        "test_day_status": TEST_DAY_STATUS,
    }
    modeling = cfg.as_dict()
    modeling.pop("output_dir")  # machine-local
    # The model version identifies what determines the point predictions: the fitted
    # artifacts and the feature contract. Calibration, policies and descriptive metadata
    # are covered by bundle_id, so they never change the model version on their own.
    content = canonical_json({"artifacts": [a["sha256"] for a in artifacts], "features": contract})
    version_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
    return {
        "producer": "bart-reliability",
        "producer_version": importlib.metadata.version("bart-reliability"),
        "bundle_format_version": 2,
        "bundle_id": "",  # set by the caller: content hash of everything else
        "feature_schema_version": constant(schema, "feature_schema_version"),
        "model": {
            "name": bcfg.model_name,
            "version": f"{bcfg.model_line_version}+{version_hash}",
            "regression": selected["regression"],
            "classification": selected["classification"],
        },
        "artifacts": artifacts,
        "environment": runtime_environment(),
        "features": contract,
        "context_fields": constant(schema, "context_fields"),
        "domain": constant(schema, "domain"),
        "categorical_handling": {
            "input": schema["properties"]["categorical_handling"]["properties"]["input"]["const"],
            "regression": CATEGORICAL_MECHANISM[selected["regression"]["family"]],
            "classification": CATEGORICAL_MECHANISM[selected["classification"]["family"]],
            "known_categories": known,
        },
        "fallback_behavior": constant(schema, "fallback_behavior"),
        "training_data": training,
        "model_configuration": {
            "modeling": modeling,
            "bundle": bcfg.as_dict(),
            "selected_parameters": parameters,
        },
        "interval": interval,
        "verification": {},
    }


def _verify(predictor, keyed, records, cfg, bcfg) -> dict:
    """Exact parity with the modeling pipeline's predictions.parquet."""
    reg, prob = predictor._predict_frame(keyed[list(cfg.features)])
    reg_ref = keyed["predicted_revision_s"].to_numpy()
    prob_ref = keyed["predicted_probability"].to_numpy()
    known = predictor._known
    supported = np.ones(len(keyed), dtype=bool)
    for name in cfg.categorical_features:
        supported &= keyed[name].isin(known[name]).to_numpy()
    batch = {
        "rows": int(len(keyed)),
        "supported_rows": int(supported.sum()),
        "splits": ["validation", "test"],
        "regression_exact": bool(np.array_equal(reg, reg_ref)),
        "classification_exact": bool(np.array_equal(prob, prob_ref)),
        "max_abs_difference": {
            "regression": float(np.max(np.abs(reg - reg_ref))),
            "classification": float(np.max(np.abs(prob - prob_ref))),
        },
    }
    if len(records) != len(keyed):
        raise BundleError("inference records do not line up with the evaluated rows")
    lookup = keyed.set_index(["event_id", "horizon_bucket_s"])
    n = min(bcfg.single_record_parity_rows, len(records))
    indices = sorted(set(np.linspace(0, len(records) - 1, n).round().astype(int).tolist()))
    fields = predictor._context + predictor.features
    mismatches, fallback = 0, 0
    for i in indices:
        row = records.iloc[i]
        out = predictor.predict(to_record(row, fields))
        if out["status"] != "ok":  # unseen category: no prediction to compare
            fallback += 1
            continue
        ref = lookup.loc[(row["event_id"], row["horizon_bucket_s"])]
        if (
            out["predicted_eta_revision_seconds"] != ref["predicted_revision_s"]
            or out["probability_absolute_revision_over_60_seconds"] != ref["predicted_probability"]
        ):
            mismatches += 1
    single = {
        "rows": len(indices),
        "selection": "evenly spaced over validation and test",
        "supported_rows": len(indices) - fallback,
        "fallback_required_rows": fallback,
        "exact": mismatches == 0,
        "mismatches": mismatches,
    }
    if not (batch["regression_exact"] and batch["classification_exact"] and single["exact"]):
        raise BundleError(
            f"bundle predictions differ from the modeling pipeline: {batch}, {single}"
        )
    return {
        "reference": "predictions.parquet of the modeling run built in the same build",
        "batch_parity": batch,
        "single_record_parity": single,
    }


def _write(directory: Path, metadata: dict) -> None:
    (directory / METADATA_FILENAME).write_text(
        json.dumps(metadata, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    )
