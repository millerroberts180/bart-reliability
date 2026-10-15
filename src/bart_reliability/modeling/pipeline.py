"""Run the ETA revision modeling pipeline end to end and write its artifacts.

Steps: build point-in-time features (SQL) -> assign chronological splits -> fit baselines
and candidates on training rows -> compare candidates on validation -> score the selected
models once on test -> write everything to an ignored output directory, atomically.
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
import sklearn

from bart_reliability.modeling.baselines import HistoricalBaseline, NoRevisionBaseline
from bart_reliability.modeling.config import SPLITS, LeakageError, ModelConfig
from bart_reliability.modeling.features import (
    FEATURE_KINDS,
    PROHIBITED_COLUMNS,
    build_feature_tables,
)
from bart_reliability.modeling.leakage import (
    SUSPICIOUS_SINGLE_FEATURE_AUC,
    check_model_inputs,
    single_feature_alarm,
)
from bart_reliability.modeling.metrics import (
    classification_metrics,
    regression_metrics,
    relative_to,
)
from bart_reliability.modeling.models import (
    CLASSIFICATION,
    REGRESSION,
    build_estimator,
    candidates,
    linear_coefficients,
    predict,
)
from bart_reliability.modeling.report import write_report
from bart_reliability.modeling.sensitivity import (
    baseline_name,
    sensitivity_predictions,
    sensitivity_report,
)
from bart_reliability.modeling.splits import build_model_frame, check_split_integrity
from bart_reliability.modeling.uncertainty import (
    EVENT,
    EVENT_SENSITIVITY_NOTE,
    TRIP,
    TRIP_SCOPE_NOTE,
    bootstrap_draws,
    compare,
    observed_values,
    trip_run_key,
)

PROVISIONAL_NOTE = (
    "Provisional development results from a short collection period. They describe ETA "
    "revisions relative to BART's own final stable estimate on these service dates only, "
    "not arrival accuracy and not BART performance in general."
)
REGRESSION_KEYS = ("mae_s", "median_ae_s", "rmse_s")
CLASSIFICATION_KEYS = ("brier", "pr_auc", "roc_auc", "ece")


@dataclass(frozen=True)
class RunResult:
    out_dir: Path
    metrics: dict
    manifest: dict


def run_pipeline(db_path: Path, cfg: ModelConfig, out_dir: Path | None = None) -> RunResult:
    out_dir = out_dir or cfg.output_dir
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_dir.with_name(f".{out_dir.name}.building")
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "models").mkdir(parents=True)
    try:
        con = duckdb.connect(str(tmp / "features.duckdb"))
        try:
            _attach_warehouse(con, db_path)
            feature_report = build_feature_tables(con)
            failed = {k: v for k, v in feature_report["checks"].items() if v}
            if failed:
                raise LeakageError(f"point-in-time feature checks failed: {failed}")
            build_model_frame(con, cfg.split, cfg.quality_tiers)
            exclusions = _exclusions(con)
            frame = load_frame(con, cfg)
            warehouse = _warehouse_info(con)
            con.execute("DETACH wh")
        finally:
            con.close()
        bounds = check_split_integrity(frame)
        metrics, artifacts = fit_and_evaluate(frame, cfg)
        metrics["exclusions"] = exclusions
        manifest = _manifest(db_path, cfg, feature_report, warehouse, bounds, frame, artifacts)
        _write(tmp, metrics, manifest, artifacts)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    old = out_dir.with_name(f".{out_dir.name}.old")
    shutil.rmtree(old, ignore_errors=True)
    if out_dir.exists():
        out_dir.rename(old)
    tmp.rename(out_dir)
    shutil.rmtree(old, ignore_errors=True)
    return RunResult(out_dir, metrics, manifest)


def _attach_warehouse(con: duckdb.DuckDBPyConnection, db_path: Path) -> None:
    if not db_path.is_file():
        raise FileNotFoundError(f"warehouse not found: {db_path}")
    con.execute(
        f"ATTACH '{str(db_path.resolve()).replace(chr(39), chr(39) * 2)}' AS wh (READ_ONLY)"
    )
    # Timestamps come back in UTC regardless of the machine's time zone.
    con.execute("SET TimeZone = 'UTC'")
    catalog = con.execute("SELECT current_database()").fetchone()[0]
    con.execute(f"SET search_path = '{catalog}.main,wh.main'")


def load_frame(con: duckdb.DuckDBPyConnection, cfg: ModelConfig) -> pd.DataFrame:
    """Kept examples with their split, labels and configured features, in a fixed order."""
    columns = sorted(set(cfg.features) | {c for level in cfg.baseline_levels for c in level})
    leaked = sorted(set(columns) & PROHIBITED_COLUMNS)
    if leaked:
        raise LeakageError(f"prohibited columns requested for the model frame: {leaked}")
    selected = ", ".join(f"f.{c}" for c in columns)
    frame = con.execute(
        f"""
        SELECT m.event_id, m.published_horizon_bucket_s AS horizon_bucket_s, m.split,
               m.service_date, e.trip_id, m.prediction_collected_at, m.label_known_at,
               e.eta_revision_seconds, e.absolute_eta_revision_seconds, {selected}
        FROM eta_model_frame m
        JOIN eta_model_examples e USING (event_id, published_horizon_bucket_s)
        JOIN eta_model_features f USING (event_id, published_horizon_bucket_s)
        WHERE m.split IS NOT NULL
        ORDER BY m.event_id, m.published_horizon_bucket_s
        """
    ).df()
    frame["large_revision"] = (
        frame["absolute_eta_revision_seconds"] > cfg.large_revision_threshold_s
    ).astype(int)
    # Bootstrap clustering unit only (never a model input).
    frame["trip_run_key"] = trip_run_key(frame["service_date"], frame["trip_id"])
    for c in columns:
        if FEATURE_KINDS[c] == "categorical":
            frame[c] = frame[c].astype("string").fillna("unknown").astype(object)
        else:
            frame[c] = frame[c].astype(float)
    return frame


def fit_and_evaluate(frame: pd.DataFrame, cfg: ModelConfig) -> tuple[dict, dict]:
    parts = {name: frame[frame["split"] == name].reset_index(drop=True) for name in SPLITS}
    train, val, test = parts["train"], parts["validation"], parts["test"]
    features = list(cfg.features)
    threshold = cfg.decision_threshold
    check_model_inputs(list(train[features].columns), cfg)
    alarm_scores = single_feature_alarm(train, cfg)

    no_rev = NoRevisionBaseline()
    hist = HistoricalBaseline(cfg.baseline_levels, cfg.baseline_min_group_size).fit(train)

    def baseline_preds(rows):
        z_reg, z_prob = no_rev.predict(rows)
        h_reg, h_prob, h_level = hist.predict(rows)
        return {"no_revision": (z_reg, z_prob), "historical": (h_reg, h_prob)}, h_level

    val_base, val_levels = baseline_preds(val)
    fitted, fit_warnings = {}, {}
    val_reg = {k: v[0] for k, v in val_base.items()}
    val_prob = {k: v[1] for k, v in val_base.items()}
    for cand in candidates(cfg):
        est = build_estimator(cand, cfg)
        y = train["eta_revision_seconds"] if cand.task == REGRESSION else train["large_revision"]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            est.fit(train[features], y)
        key = f"{cand.task}:{cand.name}"
        fit_warnings[key] = sorted({f"{w.category.__name__}: {w.message}" for w in caught})
        fitted[key] = (cand, est)
        (val_reg if cand.task == REGRESSION else val_prob)[cand.name] = predict(
            est, cand.task, val[features]
        )

    reg_scores = {
        c.name: regression_metrics(val["eta_revision_seconds"], val_reg[c.name])["mae_s"]
        for c, _ in fitted.values()
        if c.task == REGRESSION
    }
    cls_scores = {
        c.name: classification_metrics(val["large_revision"], val_prob[c.name], threshold)["brier"]
        for c, _ in fitted.values()
        if c.task == CLASSIFICATION
    }
    best_reg = min(reg_scores, key=reg_scores.get)  # first minimum: linear wins ties
    best_cls = min(cls_scores, key=cls_scores.get)
    reg_est = fitted[f"{REGRESSION}:{best_reg}"][1]
    cls_est = fitted[f"{CLASSIFICATION}:{best_cls}"][1]

    # The single test evaluation: the two selected models beside both baselines.
    test_base, test_levels = baseline_preds(test)
    test_reg = {k: v[0] for k, v in test_base.items()} | {
        best_reg: predict(reg_est, REGRESSION, test[features])
    }
    test_prob = {k: v[1] for k, v in test_base.items()} | {
        best_cls: predict(cls_est, CLASSIFICATION, test[features])
    }

    # Predeclared baseline sensitivity, and paired event-bootstrap intervals on test for
    # the selected models minus each baseline setting (same resamples for all).
    names = {"regression": best_reg, "classification": best_cls}
    evaluated = {"validation": val, "test": test}
    sens_fitted, sens_preds = sensitivity_predictions(train, evaluated, cfg)
    primary = cfg.baseline_min_group_size
    if not np.array_equal(sens_preds["test"][primary][0], test_reg["historical"]):
        raise RuntimeError("sensitivity run of the primary setting differs from the baseline")
    boot_reg = {best_reg: test_reg[best_reg]} | {
        baseline_name(k, primary): v[0] for k, v in sens_preds["test"].items()
    }
    boot_prob = {best_cls: test_prob[best_cls]} | {
        baseline_name(k, primary): v[1] for k, v in sens_preds["test"].items()
    }
    # Primary: trip-clustered. Sensitivity: event-clustered, primary baseline only.
    draws = bootstrap_draws(
        test, boot_reg, boot_prob, cfg.bootstrap_replicates, cfg.seed, cluster=TRIP
    )
    observed = observed_values(test, boot_reg, boot_prob)
    pair_reg = {k: boot_reg[k] for k in (best_reg, "historical")}
    pair_prob = {k: boot_prob[k] for k in (best_cls, "historical")}
    event_draws = bootstrap_draws(
        test, pair_reg, pair_prob, cfg.bootstrap_replicates, cfg.seed, cluster=EVENT
    )

    def uncertainty_block(unit, cluster, clusters_draws, note):
        return {
            "resampling_unit": unit,
            "cluster_column": cluster,
            "clusters": int(test[cluster].nunique()),
            "note": note,
            "selected_minus_historical": compare(
                test,
                clusters_draws,
                observed,
                best_reg,
                best_cls,
                "historical",
                cfg.bootstrap_confidence_level,
            ),
        }

    metrics = {
        "provisional": True,
        "note": PROVISIONAL_NOTE,
        "large_revision_threshold_s": cfg.large_revision_threshold_s,
        "decision_threshold": threshold,
        "samples": {name: _sample(rows) for name, rows in parts.items()},
        "validation": _evaluate(val, val_reg, val_prob, cfg),
        "selection": {
            "refitted_on_validation": False,
            "regression": {
                "criterion": "validation MAE",
                "scores": reg_scores,
                "selected": best_reg,
            },
            "classification": {
                "criterion": "validation Brier score",
                "scores": cls_scores,
                "selected": best_cls,
            },
        },
        "test": _evaluate(test, test_reg, test_prob, cfg),
        "historical_baseline_levels_used": {
            "validation": _counts(val_levels),
            "test": _counts(test_levels),
        },
        "uncertainty": {
            "scope": TRIP_SCOPE_NOTE,
            "method": "paired percentile bootstrap",
            "replicates": cfg.bootstrap_replicates,
            "seed": cfg.seed,
            "confidence_level": cfg.bootstrap_confidence_level,
            "trips": int(test[TRIP].nunique()),
            "events": int(test[EVENT].nunique()),
            "examples": int(len(test)),
            "service_dates": _date_range(test),
            "models": names,
            "baseline": f"historical (min_group_size={primary})",
            "primary_trip_clustered": uncertainty_block(
                "trip run (service date + trip_id): every stop-arrival event of the trip "
                "and all of their published-time horizons",
                TRIP,
                draws,
                TRIP_SCOPE_NOTE,
            ),
            "sensitivity_event_clustered": uncertainty_block(
                "stop-arrival event: all of its published-time horizons",
                EVENT,
                event_draws,
                EVENT_SENSITIVITY_NOTE,
            ),
        },
        "historical_baseline_sensitivity": sensitivity_report(
            evaluated,
            sens_preds,
            sens_fitted,
            {"validation": val_reg[best_reg], "test": test_reg[best_reg]},
            {"validation": val_prob[best_cls], "test": test_prob[best_cls]},
            draws,
            observed,
            names,
            cfg,
        ),
        "single_feature_alarm": {
            "description": (
                "Diagnostic alarm for suspicious predictive power, not proof that leakage is "
                "absent. Primary controls: point-in-time SQL checks, the prohibited-field "
                "catalog, split isolation, train-only aggregation and perturbation tests."
            ),
            "single_feature_roc_auc_train": alarm_scores,
            "fails_at": SUSPICIOUS_SINGLE_FEATURE_AUC,
        },
        "fit_warnings": {k: v for k, v in fit_warnings.items() if v},
    }
    metrics["test"]["relative_to_baselines"] = {
        "regression": _relative(metrics["test"]["regression"], best_reg, REGRESSION_KEYS),
        "classification": _relative(
            metrics["test"]["classification"], best_cls, CLASSIFICATION_KEYS
        ),
    }
    metrics["validation"]["relative_to_baselines"] = {
        "regression": {
            name: _relative(metrics["validation"]["regression"], name, REGRESSION_KEYS)
            for name in reg_scores
        },
        "classification": {
            name: _relative(metrics["validation"]["classification"], name, CLASSIFICATION_KEYS)
            for name in cls_scores
        },
    }
    best_linear = min((n for n in reg_scores if n.startswith("linear")), key=reg_scores.get)
    metrics["linear_comparator"] = {
        "model": best_linear,
        "selected": best_linear == best_reg,
        "description": (
            "Huber regression is a robust linear comparator. Huber loss is quadratic for "
            "small residuals and linear for large ones; it does not directly optimize MAE."
        ),
        "largest_standardized_coefficients": linear_coefficients(
            fitted[f"{REGRESSION}:{best_linear}"][1]
        ),
    }

    predictions = _predictions(val, val_reg, val_prob, val_levels, "validation")
    predictions = pd.concat(
        [predictions, _predictions(test, test_reg, test_prob, test_levels, "test")],
        ignore_index=True,
    )
    artifacts = {
        "predictions": predictions,
        "historical_groups": hist.fitted_groups(),
        "models": {key: est for key, (_, est) in fitted.items()},
        "selected": {"regression": best_reg, "classification": best_cls},
        "sensitivity_groups": {k: b.fitted_groups() for k, b in sens_fitted.items()},
        "bootstrap_draws": pd.concat(
            [
                _flatten_draws(draws).assign(clustering="trip"),
                _flatten_draws(event_draws).assign(clustering="event"),
            ],
            ignore_index=True,
        ),
    }
    return metrics, artifacts


def _flatten_draws(draws: dict) -> pd.DataFrame:
    """Per-replicate metric values, one column per prediction set and metric."""
    columns = {}
    for name, metrics in draws.items():
        for metric, values in metrics.items():
            if isinstance(values, dict):
                for scope, v in values.items():
                    columns[f"{name}__{metric}__{scope}"] = v
            else:
                columns[f"{name}__{metric}"] = values
    return pd.DataFrame(columns).rename_axis("replicate").reset_index()


def _evaluate(rows: pd.DataFrame, reg: dict, prob: dict, cfg: ModelConfig) -> dict:
    """Metrics for every prediction set, overall and per published-horizon bucket."""
    buckets = sorted(rows["horizon_bucket_s"].unique())
    masks = {str(b): (rows["horizon_bucket_s"] == b).to_numpy() for b in buckets}

    def block(fn, y, pred):
        pred = np.asarray(pred)
        return {
            "overall": _with_sample(rows, fn(y, pred)),
            "by_horizon": {h: _with_sample(rows[m], fn(y[m], pred[m])) for h, m in masks.items()},
        }

    def cls(y, p):
        return classification_metrics(y, p, cfg.decision_threshold, cfg.calibration_bins)

    y_reg = rows["eta_revision_seconds"].to_numpy()
    y_cls = rows["large_revision"].to_numpy()
    return {
        "regression": {name: block(regression_metrics, y_reg, p) for name, p in reg.items()},
        "classification": {name: block(cls, y_cls, p) for name, p in prob.items()},
    }


def _relative(block: dict, model: str, keys: tuple[str, ...]) -> dict:
    out = {}
    for baseline in ("no_revision", "historical"):
        out[f"vs_{baseline}"] = {
            "overall": relative_to(block[model]["overall"], block[baseline]["overall"], keys),
            "by_horizon": {
                h: relative_to(
                    block[model]["by_horizon"][h], block[baseline]["by_horizon"][h], keys
                )
                for h in block[model]["by_horizon"]
            },
        }
    return out


def _sample(rows: pd.DataFrame) -> dict:
    return {
        "examples": int(len(rows)),
        "events": int(rows["event_id"].nunique()),
        "service_dates": _date_range(rows),
        "predictions_from_utc": _iso(rows["prediction_collected_at"].min()),
        "predictions_to_utc": _iso(rows["prediction_collected_at"].max()),
        "examples_by_horizon": {
            str(k): int(v) for k, v in rows["horizon_bucket_s"].value_counts().sort_index().items()
        },
        "large_revision_prevalence": round(float(rows["large_revision"].mean()), 4),
    }


def _with_sample(rows: pd.DataFrame, metrics: dict) -> dict:
    return {
        "examples": int(len(rows)),
        "events": int(rows["event_id"].nunique()),
        "service_dates": _date_range(rows),
        **{k: v for k, v in metrics.items() if k != "n"},
    }


def _date_range(rows: pd.DataFrame) -> list[str]:
    dates = pd.to_datetime(rows["service_date"])
    return [str(dates.min().date()), str(dates.max().date())]


def _predictions(rows, reg, prob, levels, split) -> pd.DataFrame:
    out = rows[
        [
            "event_id",
            "horizon_bucket_s",
            "service_date",
            "prediction_collected_at",
            "eta_revision_seconds",
            "large_revision",
        ]
    ].copy()
    out.insert(2, "split", split)
    out["historical_level"] = levels
    for name, pred in reg.items():
        out[f"revision_s__{name}"] = np.asarray(pred, dtype=float)
    for name, p in prob.items():
        out[f"large_revision_probability__{name}"] = np.asarray(p, dtype=float)
    return out


def _counts(values) -> dict:
    s = pd.Series(values).value_counts()
    return {str(k): int(v) for k, v in s.sort_index().items()}


def _iso(ts) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _exclusions(con: duckdb.DuckDBPyConnection) -> dict:
    def pairs(sql):
        return {str(k): int(v) for k, v in con.execute(sql).fetchall()}

    return {
        "warehouse_events_not_eligible": pairs(
            "SELECT exclusion_reason, count(*) FROM observed_arrival_proxy "
            "WHERE NOT is_eligible GROUP BY 1 ORDER BY 2 DESC, 1"
        ),
        "eligible_event_horizons_without_example": pairs(
            "SELECT missing_reason, count(*) FROM eta_model_example_coverage "
            "WHERE missing_reason IS NOT NULL GROUP BY 1 ORDER BY 1"
        ),
        "examples_by_frame_exclusion": pairs(
            "SELECT coalesce(exclusion_reason, 'kept'), count(*) FROM eta_model_frame "
            "GROUP BY 1 ORDER BY 1"
        ),
        "examples_outside_split_dates_by_service_date": pairs(
            "SELECT CAST(service_date AS VARCHAR), count(*) FROM eta_model_frame "
            "WHERE exclusion_reason = 'outside_split_dates' GROUP BY 1 ORDER BY 1"
        ),
        "kept_examples_by_split": pairs(
            "SELECT split, count(*) FROM eta_model_frame WHERE split IS NOT NULL GROUP BY 1"
        ),
    }


def _warehouse_info(con: duckdb.DuckDBPyConnection) -> dict:
    first, last, n = con.execute(
        "SELECT min(collected_at), max(collected_at), count(*) FROM proxy_snapshot_timeline"
    ).fetchone()
    return {
        "trip_update_snapshots": int(n),
        "first_snapshot_utc": _iso(first) if first else None,
        "last_snapshot_utc": _iso(last) if last else None,
        "eta_revision_config": dict(
            con.execute("SELECT parameter, value FROM eta_revision_config ORDER BY 1").fetchall()
        ),
    }


def _fingerprint(frame: pd.DataFrame, cfg: ModelConfig) -> str:
    cols = ["event_id", "horizon_bucket_s", "split", "eta_revision_seconds", *cfg.features]
    data = frame[cols].to_csv(index=False).encode()
    return hashlib.sha256(data).hexdigest()


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True, timeout=5
        ).stdout.strip()
        return out.stdout.strip() + ("-dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return None


def _manifest(db_path, cfg, feature_report, warehouse, bounds, frame, artifacts) -> dict:
    return {
        "created_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "warehouse": str(db_path),
        "warehouse_data": warehouse,
        "config": cfg.as_dict(),
        "feature_build": feature_report,
        "split_bounds_utc": {
            name: {k: _iso(v) for k, v in b.items()} for name, b in bounds.items()
        },
        "frame_fingerprint_sha256": _fingerprint(frame, cfg),
        "selected_models": artifacts["selected"],
        "versions": {
            "python": platform.python_version(),
            "duckdb": duckdb.__version__,
            "scikit-learn": sklearn.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "git_commit": _git_commit(),
    }


def _write(tmp: Path, metrics: dict, manifest: dict, artifacts: dict) -> None:
    (tmp / "metrics.json").write_text(json.dumps(metrics, indent=1, sort_keys=False) + "\n")
    (tmp / "run_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    artifacts["predictions"].to_parquet(tmp / "predictions.parquet", index=False)
    artifacts["historical_groups"].to_parquet(tmp / "historical_baseline.parquet", index=False)
    pd.concat(
        [g.assign(min_group_size=k) for k, g in artifacts["sensitivity_groups"].items()],
        ignore_index=True,
    ).to_parquet(tmp / "historical_baseline_sensitivity.parquet", index=False)
    artifacts["bootstrap_draws"].to_parquet(tmp / "bootstrap_replicates.parquet", index=False)
    for key, est in artifacts["models"].items():
        task, name = key.split(":", 1)
        joblib.dump(est, tmp / "models" / f"{task}__{name}.joblib")
    write_report(tmp / "report.md", metrics, manifest)
