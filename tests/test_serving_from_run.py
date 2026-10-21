"""Packaging a finished modeling run into a bundle without refitting anything.

The run comes from the synthetic warehouse. Packaging it must give the same models,
interval, known categories and parity results as the build that ran the pipeline, must
never run the pipeline, and must never write to the run directory.
"""

import os
import stat
from dataclasses import replace
from datetime import date

import pytest
from modeling_fixtures import build_synthetic_warehouse, synthetic_config

import bart_reliability.serving.bundle as bundle_module
from bart_reliability.serving import BundleError, Predictor
from bart_reliability.serving.bundle import build_bundle, build_bundle_from_run
from bart_reliability.serving.config import load_bundle_config
from bart_reliability.serving.main import main as cli
from bart_reliability.serving.schema import sha256_file


def bundle_config(out_dir):
    # The synthetic validation day has 18 examples per horizon.
    return replace(load_bundle_config(), output_dir=out_dir, min_calibration_examples_per_horizon=5)


def tree_state(directory):
    """Every file's bytes hash, size and modification time, by relative path."""
    out = {}
    for p in sorted(directory.rglob("*")):
        if p.is_file():
            st = p.stat()
            out[str(p.relative_to(directory))] = (sha256_file(p), st.st_size, st.st_mtime_ns)
    return out


def read_only(directory):
    for p in [directory, *directory.rglob("*")]:
        mode = p.stat().st_mode
        os.chmod(p, mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def writable(directory):
    for p in [directory, *directory.rglob("*")]:
        os.chmod(p, p.stat().st_mode | stat.S_IWUSR)


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory):
    return build_synthetic_warehouse(tmp_path_factory.mktemp("wh"))


@pytest.fixture(scope="module")
def built(warehouse, tmp_path_factory):
    root = tmp_path_factory.mktemp("built")
    return build_bundle(warehouse, synthetic_config(root / "run"), bundle_config(root / "bundle"))


@pytest.fixture(scope="module")
def packaged(built, tmp_path_factory, monkeypatch_module):
    """The same run packaged again, read-only, with the pipeline made unavailable."""

    def no_pipeline(*args, **kwargs):
        raise AssertionError("packaging a run must not run the modeling pipeline")

    monkeypatch_module.setattr(bundle_module, "run_pipeline", no_pipeline)
    root = tmp_path_factory.mktemp("packaged")
    read_only(built.run_dir)
    before = tree_state(built.run_dir)
    try:
        result = build_bundle_from_run(
            built.run_dir, synthetic_config(built.run_dir), bundle_config(root / "bundle")
        )
        after = tree_state(built.run_dir)
    finally:
        writable(built.run_dir)
    assert after == before  # nothing in the frozen run was written or touched
    return result


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def without(meta, *keys):
    meta = dict(meta)
    for k in keys:
        meta.pop(k)
    return meta


def test_packaging_reproduces_the_built_bundle(built, packaged):
    a, b = built.metadata, packaged.metadata
    assert a["artifacts"] == b["artifacts"]
    assert a["model"] == b["model"]  # same model version, estimators and candidates
    assert a["interval"] == b["interval"]
    assert a["categorical_handling"] == b["categorical_handling"]
    assert a["training_data"] == b["training_data"]
    va, vb = a["verification"], b["verification"]
    assert without(va, "reference") == without(vb, "reference")
    assert vb["reference"] == "predictions.parquet of the frozen modeling run"
    assert without(a, "bundle_id", "verification") == without(b, "bundle_id", "verification")
    for role in ("regression", "classification"):
        name = f"{role}.joblib"
        assert sha256_file(packaged.bundle_dir / name) == sha256_file(built.bundle_dir / name)


def test_packaged_bundle_loads_with_exact_parity(packaged):
    predictor = Predictor.load(packaged.bundle_dir, packaged.metadata["bundle_id"])
    parity = predictor.metadata["verification"]
    assert parity["batch_parity"]["regression_exact"]
    assert parity["batch_parity"]["classification_exact"]
    assert parity["single_record_parity"]["exact"]


@pytest.mark.parametrize(
    "change",
    [
        {"seed": 7},
        {
            "split": {
                "train": (date(2026, 10, 6), date(2026, 10, 6)),
                "validation": (date(2026, 10, 8), date(2026, 10, 8)),
                "test": (date(2026, 10, 9), date(2026, 10, 9)),
            }
        },
        {"baseline_min_group_size": 6},
    ],
)
def test_a_different_model_configuration_is_refused(built, tmp_path, change):
    cfg = replace(synthetic_config(built.run_dir), **change)
    with pytest.raises(BundleError, match="different model configuration"):
        build_bundle_from_run(built.run_dir, cfg, bundle_config(tmp_path / "bundle"))
    assert not (tmp_path / "bundle").exists()


def test_where_the_run_was_written_does_not_matter(built, tmp_path):
    cfg = synthetic_config(tmp_path / "elsewhere")
    result = build_bundle_from_run(built.run_dir, cfg, bundle_config(tmp_path / "bundle"))
    assert result.metadata["artifacts"] == built.metadata["artifacts"]


def test_an_unfinished_run_is_refused(built, tmp_path):
    with pytest.raises(BundleError, match="not a finished modeling run"):
        build_bundle_from_run(tmp_path, synthetic_config(tmp_path), bundle_config(tmp_path / "b"))


def test_cli_packages_a_run(built, tmp_path, monkeypatch):
    out = tmp_path / "bundle"
    monkeypatch.setattr(
        "bart_reliability.serving.main.load_model_config",
        lambda path: synthetic_config(built.run_dir),
    )
    monkeypatch.setattr(
        "bart_reliability.serving.main.load_bundle_config", lambda path: bundle_config(out)
    )
    assert cli(["build", "--from-run", str(built.run_dir)]) == 0
    assert (out / "bundle.json").is_file()
    with pytest.raises(SystemExit) as exc:
        cli(["build", "--from-run", str(built.run_dir), "--run-dir", str(tmp_path / "r")])
    assert exc.value.code == 2
