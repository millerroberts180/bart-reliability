"""The locked model comparison and category support on the synthetic warehouse.

A bundle built from the synthetic run is the "locked" pair. Scored beside a retrained
run with the same split and seed, it must give exactly the same predictions, so every
retrained-minus-locked difference is zero. That pins the mechanics: the locked pair is
loaded, verified and scored on the same rows, and never refitted.
"""

import json
import shutil
from dataclasses import replace

import duckdb
import numpy as np
import pandas as pd
import pytest
from modeling_fixtures import build_synthetic_warehouse, synthetic_config

from bart_reliability.modeling.config import LockedComparisonConfig, ModelConfigError
from bart_reliability.modeling.locked import (
    known_categories,
    load_locked_models,
    outside_support,
    support_report,
)
from bart_reliability.modeling.pipeline import fit_and_evaluate, load_frame, run_pipeline
from bart_reliability.serving import BundleError
from bart_reliability.serving.bundle import build_bundle
from bart_reliability.serving.config import load_bundle_config
from bart_reliability.serving.schema import sha256_file

NAME = "locked_test"


def bundle_config(out_dir):
    # The synthetic validation day has 18 examples per horizon.
    return replace(load_bundle_config(), output_dir=out_dir, min_calibration_examples_per_horizon=5)


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory):
    return build_synthetic_warehouse(tmp_path_factory.mktemp("wh"))


@pytest.fixture(scope="module")
def locked_bundle(warehouse, tmp_path_factory):
    root = tmp_path_factory.mktemp("locked")
    return build_bundle(warehouse, synthetic_config(root / "run"), bundle_config(root / "bundle"))


def locked_config(bundle, out_dir, **overrides):
    locked = LockedComparisonConfig(NAME, bundle.bundle_dir, bundle.metadata["bundle_id"])
    return synthetic_config(out_dir, locked_comparison=locked, **overrides)


def hashes(directory):
    return {p.name: sha256_file(p) for p in sorted(directory.iterdir())}


@pytest.fixture(scope="module")
def run(warehouse, locked_bundle, tmp_path_factory):
    before = hashes(locked_bundle.bundle_dir)
    out = tmp_path_factory.mktemp("runs") / "eta_revision"
    result = run_pipeline(warehouse, locked_config(locked_bundle, out))
    assert hashes(locked_bundle.bundle_dir) == before  # never refitted or rewritten
    return result


def test_locked_pair_is_scored_on_the_same_test_rows(run):
    preds = pd.read_parquet(run.out_dir / "predictions.parquet")
    test = preds[preds["split"] == "test"]
    sel = run.metrics["selection"]
    reg, cls = sel["regression"]["selected"], sel["classification"]["selected"]
    # Same training rows, seed and grid: the locked pair is the same fit.
    assert np.array_equal(test[f"revision_s__{NAME}"], test[f"revision_s__{reg}"])
    assert np.array_equal(
        test[f"large_revision_probability__{NAME}"], test[f"large_revision_probability__{cls}"]
    )
    # Only on test: validation rows have no locked prediction.
    assert preds.loc[preds["split"] == "validation", f"revision_s__{NAME}"].isna().all()
    assert NAME in run.metrics["test"]["regression"]
    assert NAME not in run.metrics["validation"]["regression"]
    assert NAME not in sel["regression"]["scores"]


def test_retrained_minus_locked_differences_are_zero(run):
    unc = run.metrics["uncertainty"]
    for block in ("primary_trip_clustered", "sensitivity_event_clustered"):
        d = unc[block][f"selected_minus_{NAME}"]
        cells = [d["mae_s"]["overall"], *d["mae_s"]["by_horizon"].values(), d["brier"]]
        cells.append(d["pr_auc"])
        for c in cells:
            assert c["observed"] == 0 and c["ci_low"] == 0 and c["ci_high"] == 0
        # The historical comparison is still reported, unchanged in form.
        assert "selected_minus_historical" in unc[block]


def test_locked_comparison_does_not_change_the_primary_results(warehouse, run, tmp_path):
    plain = run_pipeline(warehouse, synthetic_config(tmp_path / "plain"))
    unc, ref = run.metrics["uncertainty"], plain.metrics["uncertainty"]
    for block in ("primary_trip_clustered", "sensitivity_event_clustered"):
        assert unc[block]["selected_minus_historical"] == ref[block]["selected_minus_historical"]
    for task in ("regression", "classification"):
        for name, values in plain.metrics["test"][task].items():
            assert run.metrics["test"][task][name] == values
    assert plain.metrics["locked_comparison"] is None
    assert (
        run.manifest["locked_comparison"]["bundle_id"]
        == run.metrics["locked_comparison"]["bundle_id"]
    )


def test_locked_metadata_is_recorded(run, locked_bundle):
    meta = run.metrics["locked_comparison"]
    assert meta["bundle_id"] == locked_bundle.metadata["bundle_id"]
    assert meta["refitted"] is False and meta["scored_on"] == "test rows only"
    assert {a["filename"]: a["sha256"] for a in meta["artifacts"]} == {
        a["filename"]: a["sha256"] for a in locked_bundle.metadata["artifacts"]
    }
    json.dumps(run.metrics)  # everything recorded is JSON


def test_full_support_needs_no_subset(run):
    support = run.metrics["category_support"]["test"]
    assert set(support["outside_support"]) == {"selected", NAME}
    assert all(d["examples"] == 0 for d in support["outside_support"].values())
    assert support["shared_support"]["examples"] == support["examples"]
    assert run.metrics["shared_support_subset"] == {
        "computed": False,
        "reason": "every test example is inside the shared support",
    }
    preds = pd.read_parquet(run.out_dir / "predictions.parquet")
    assert preds.loc[preds["split"] == "test", "inside_shared_support"].all()


def test_report_has_locked_and_support_sections(run):
    text = (run.out_dir / "report.md").read_text()
    assert f"retrained models minus the locked models (`{NAME}`)" in text
    assert "## Category support and fallback (test)" in text
    assert "Not computed: every test example is inside the shared support." in text


def test_wrong_bundle_id_fails_before_any_output(warehouse, locked_bundle, tmp_path):
    cfg = locked_config(locked_bundle, tmp_path / "out")
    cfg = replace(cfg, locked_comparison=replace(cfg.locked_comparison, bundle_id="0" * 64))
    with pytest.raises(BundleError, match="not the pinned build"):
        run_pipeline(warehouse, cfg)
    assert not any(tmp_path.iterdir())


def test_altered_locked_artifact_is_rejected(warehouse, locked_bundle, tmp_path):
    copy = tmp_path / "bundle"
    shutil.copytree(locked_bundle.bundle_dir, copy)
    with (copy / "regression.joblib").open("ab") as f:
        f.write(b"\0")
    cfg = locked_config(locked_bundle, tmp_path / "out")
    cfg = replace(cfg, locked_comparison=replace(cfg.locked_comparison, bundle_dir=copy))
    with pytest.raises(BundleError, match="SHA-256"):
        run_pipeline(warehouse, cfg)
    assert not (tmp_path / "out").exists()


def test_locked_features_must_match_the_configuration(locked_bundle, tmp_path):
    cfg = locked_config(locked_bundle, tmp_path / "out")
    cfg = replace(cfg, numeric_features=cfg.numeric_features[:-1])
    with pytest.raises(ModelConfigError, match="locked bundle features"):
        load_locked_models(cfg)


def test_unseen_categories_define_the_shared_support_subset(run, locked_bundle):
    """Rows with a stop no model saw fall outside support; the subset excludes them."""
    cfg = locked_config(locked_bundle, run.out_dir)
    with duckdb.connect(str(run.out_dir / "features.duckdb"), read_only=True) as con:
        con.execute("SET TimeZone = 'UTC'")
        frame = load_frame(con, cfg)
    test_idx = frame.index[frame["split"] == "test"]
    trip = frame.loc[test_idx, "trip_run_key"].iloc[0]
    moved = test_idx[(frame.loc[test_idx, "trip_run_key"] == trip).to_numpy()]
    frame.loc[moved, "stop_id"] = "Z99-1"

    metrics, artifacts = fit_and_evaluate(frame, cfg, load_locked_models(cfg))
    support = metrics["category_support"]["test"]
    n_test = int((frame["split"] == "test").sum())
    for model in ("selected", NAME):
        d = support["outside_support"][model]
        assert d["examples"] == len(moved) and d["trips"] == 1
        assert d["unseen_values_by_feature"] == {"stop_id": {"Z99-1": len(moved)}}
    assert support["shared_support"]["examples"] == n_test - len(moved)

    subset = metrics["shared_support_subset"]
    assert subset["computed"] and subset["sample"]["examples"] == n_test - len(moved)
    preds = artifacts["predictions"]
    test = preds[preds["split"] == "test"]
    inside = test[test["inside_shared_support"]]
    reg = metrics["selection"]["regression"]["selected"]
    expected = float(np.abs(inside[f"revision_s__{reg}"] - inside["eta_revision_seconds"]).mean())
    # Reported metrics are rounded to 0.01 s.
    assert subset["metrics"]["regression"][reg]["overall"]["mae_s"] == pytest.approx(
        expected, abs=0.005
    )
    for block in ("primary_trip_clustered", "sensitivity_event_clustered"):
        assert {"selected_minus_historical", f"selected_minus_{NAME}"} <= set(subset[block])


def test_support_helpers_by_hand():
    rows = pd.DataFrame(
        {
            "event_id": ["e1", "e1", "e2", "e3"],
            "trip_run_key": ["t1", "t1", "t1", "t2"],
            "stop_id": ["A", "B", "A", "C"],
            "hour_local": ["7", "7", "8", "9"],
        }
    )
    known = {"a": {"stop_id": {"A", "B"}, "hour_local": {"7", "8", "9"}}}
    known["b"] = {"stop_id": {"A", "B", "C"}, "hour_local": {"7"}}
    assert outside_support(rows, known["a"]).tolist() == [False, False, False, True]
    assert outside_support(rows, known["b"]).tolist() == [False, False, True, True]
    report, shared = support_report(rows, known)
    assert shared.tolist() == [True, True, False, False]
    assert report["outside_support"]["a"]["unseen_values_by_feature"] == {"stop_id": {"C": 1}}
    assert report["outside_support"]["b"]["unseen_values_by_feature"] == {
        "hour_local": {"8": 1, "9": 1}
    }
    assert report["shared_support"] == {
        "examples": 2,
        "events": 1,
        "trips": 1,
        "share_of_examples": 0.5,
    }


def test_known_categories_come_from_the_fitted_encoders(locked_bundle):
    cfg = locked_config(locked_bundle, locked_bundle.run_dir)
    models = load_locked_models(cfg)
    cats = locked_bundle.metadata["categorical_handling"]["known_categories"]
    got = known_categories(models.regression, list(cfg.categorical_features))
    assert got == {k: set(v) for k, v in cats.items()}
