"""The inference bundle: parity, strict records, verification, determinism and intervals.

Bundles are built from the synthetic multi-day warehouse in modeling_fixtures through the
same build command used for real data.
"""

import json
import shutil
from dataclasses import replace
from datetime import datetime, timedelta

import duckdb
import numpy as np
import pandas as pd
import pytest
from modeling_fixtures import DAYS, build_synthetic_warehouse, local, synthetic_config

from bart_reliability.modeling.features import FEATURE_KINDS, PROHIBITED_COLUMNS
from bart_reliability.modeling.pipeline import load_frame
from bart_reliability.serving import BundleError, Predictor, RecordError
from bart_reliability.serving.bundle import build_bundle, served_records, to_record
from bart_reliability.serving.config import load_bundle_config
from bart_reliability.serving.interval import calibrate_interval, coverage, residual_quantiles
from bart_reliability.serving.main import main as cli
from bart_reliability.serving.schema import (
    SCHEMA_PATH,
    SchemaError,
    bundle_id,
    constant,
    load_schema,
    validate,
)

# Trip T3 on the test day is held 300 s from 08:22: every later estimate moves.
HELD_FROM = local(DAYS[3], 8, 22)


def held(day, trip_id, k, now):
    return 300 if (day, trip_id) == (DAYS[3], "T3") and now >= HELD_FROM else 0


def bundle_config(out_dir, **overrides):
    # The synthetic validation day has 18 examples per horizon.
    base = replace(load_bundle_config(), output_dir=out_dir, min_calibration_examples_per_horizon=5)
    return replace(base, **overrides)


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory):
    return build_synthetic_warehouse(tmp_path_factory.mktemp("wh"))


@pytest.fixture(scope="module")
def built(warehouse, tmp_path_factory):
    root = tmp_path_factory.mktemp("bundle")
    return build_bundle(warehouse, synthetic_config(root / "run"), bundle_config(root / "bundle"))


@pytest.fixture(scope="module")
def predictor(built):
    return Predictor.load(built.bundle_dir, expected_bundle_id=built.metadata["bundle_id"])


@pytest.fixture(scope="module")
def records(built):
    cfg = synthetic_config(built.run_dir)
    with duckdb.connect(str(built.run_dir / "features.duckdb"), read_only=True) as con:
        con.execute("SET TimeZone = 'UTC'")
        rows = served_records(con, cfg, built.metadata["feature_schema_version"])
    fields = ["feature_schema_version", "snapshot_collected_at", "published_eta", *cfg.features]
    return rows, [to_record(r, fields) for _, r in rows.iterrows()]


def a_record(records, i=0):
    return dict(records[1][i])


# -- parity -------------------------------------------------------------------------


def test_bundle_matches_pipeline_predictions_exactly(built, predictor, records):
    v = built.metadata["verification"]
    assert v["batch_parity"]["regression_exact"] and v["batch_parity"]["classification_exact"]
    assert v["single_record_parity"]["exact"] and v["single_record_parity"]["rows"] == 108
    assert v["single_record_parity"]["supported_rows"] == 108
    assert v["single_record_parity"]["fallback_required_rows"] == 0
    assert v["batch_parity"]["supported_rows"] == v["batch_parity"]["rows"] == 108

    cfg = synthetic_config(built.run_dir)
    sel = built.metadata["model"]
    preds = pd.read_parquet(built.run_dir / "predictions.parquet")
    with duckdb.connect(str(built.run_dir / "features.duckdb"), read_only=True) as con:
        con.execute("SET TimeZone = 'UTC'")
        frame = load_frame(con, cfg)
    frame = frame[frame["split"] != "train"].merge(
        preds, on=["event_id", "horizon_bucket_s", "split"], validate="one_to_one"
    )
    reg, prob = predictor._predict_frame(frame[list(cfg.features)])
    assert np.array_equal(reg, frame[f"revision_s__{sel['regression']['candidate']}"])
    assert np.array_equal(
        prob, frame[f"large_revision_probability__{sel['classification']['candidate']}"]
    )
    # Every record, one at a time, equals the batch prediction for its row.
    rows, recs = records
    by_key = frame.set_index(["event_id", "horizon_bucket_s"])
    for (_, row), record in zip(rows.iterrows(), recs, strict=True):
        out = predictor.predict(record)
        assert out["status"] == "ok"
        ref = by_key.loc[(row["event_id"], row["horizon_bucket_s"])]
        assert (
            out["predicted_eta_revision_seconds"]
            == ref[f"revision_s__{sel['regression']['candidate']}"]
        )
        assert (
            out["probability_absolute_revision_over_60_seconds"]
            == ref[f"large_revision_probability__{sel['classification']['candidate']}"]
        )


def test_prediction_output_fields(built, predictor, records):
    record = a_record(records)
    out = predictor.predict(record)
    meta = built.metadata
    assert out["feature_schema_version"] == "eta-revision-features-1"
    assert out["model"]["name"] == "bart_eta_revision"
    assert out["model"]["version"] == meta["model"]["version"]
    assert out["model"]["bundle_id"] == meta["bundle_id"]
    assert out["training_data_cutoff"] == meta["training_data"]["training_data_cutoff_utc"]
    assert out["provisional"] is True and out["unknown_categories"] == []
    assert out["status"] == "ok" and out["reason"] is None and out["fallback"] is None
    published = datetime.fromisoformat(record["published_eta"])
    expected = published + timedelta(seconds=out["predicted_eta_revision_seconds"])
    final = datetime.fromisoformat(out["predicted_final_published_eta"])
    assert abs((final - expected).total_seconds()) <= 0.5
    assert 0 <= out["probability_absolute_revision_over_60_seconds"] <= 1
    assert isinstance(out["revision_intervals"], list) and len(out["revision_intervals"]) == 1


# -- strict records ------------------------------------------------------------------


def _bad(record, **changes):
    r = dict(record)
    for k, v in changes.items():
        if v is _DROP:
            r.pop(k)
        else:
            r[k] = v
    return r


_DROP = object()


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"stops_away": _DROP}, "missing fields \\['stops_away'\\]"),
        ({"final_stable_estimate": "2026-10-09T15:00:00+00:00"}, "unexpected fields"),
        ({"eta_revision_seconds": 30}, "unexpected fields"),
        ({"trip_id": "T1"}, "unexpected fields"),
        ({"feature_schema_version": "eta-revision-features-0"}, "feature_schema_version"),
        ({"stops_away": "2"}, "must be a number"),
        ({"stops_away": True}, "must be a number"),
        ({"stops_away": float("nan")}, "must be finite"),
        ({"stops_away": None}, "must be a number"),
        ({"stop_id": 7}, "non-empty string"),
        ({"stop_id": ""}, "non-empty string"),
        ({"hour_local": "8"}, "must be an integer"),
        ({"published_horizon_bucket_s": 450}, "not a served horizon"),
        ({"published_horizon_bucket_s": 900}, "outside the bucket's tolerance"),
        ({"published_horizon_s": 1}, "outside the bucket's tolerance"),
        ({"snapshot_collected_at": "2026-10-09 15:00:00"}, "timezone-aware"),
        ({"published_eta": "soon"}, "ISO-8601"),
        ({"hour_local": 23}, "Pacific hour"),
    ],
)
def test_mismatched_records_are_rejected(predictor, records, changes, message):
    record = next(r for r in records[1] if r["published_horizon_bucket_s"] == 300)
    with pytest.raises(RecordError, match=message):
        predictor.predict(_bad(record, **changes))


def test_inconsistent_derived_feature_is_rejected(predictor, records):
    record = a_record(records)
    later = datetime.fromisoformat(record["published_eta"]) + timedelta(seconds=30)
    with pytest.raises(RecordError, match="does not equal published_eta minus"):
        predictor.predict(_bad(record, published_eta=later.isoformat()))


def test_record_must_be_a_mapping(predictor):
    with pytest.raises(RecordError, match="mapping"):
        predictor.predict([("stop_id", "A20-1")])


# -- unknown categories: fallback, never a model prediction -------------------------

FALLBACK_KEYS = {
    "status",
    "reason",
    "feature_schema_version",
    "model",
    "training_data_cutoff",
    "calibration_data_cutoff",
    "provisional",
    "published_eta",
    "predicted_eta_revision_seconds",
    "probability_absolute_revision_over_60_seconds",
    "predicted_final_published_eta",
    "revision_intervals",
    "unknown_categories",
    "fallback",
}


def assert_fallback(out, built, record, unknown):
    assert set(out) == FALLBACK_KEYS
    assert out["status"] == "fallback_required"
    assert out["reason"] == "input outside demonstrated model support"
    assert out["unknown_categories"] == unknown
    # No model output of any kind.
    assert out["predicted_eta_revision_seconds"] is None
    assert out["probability_absolute_revision_over_60_seconds"] is None
    assert out["predicted_final_published_eta"] is None
    assert out["revision_intervals"] == []
    # The caller falls back to BART's unadjusted published ETA.
    published = datetime.fromisoformat(record["published_eta"])
    assert out["fallback"]["action"] == "use_published_eta"
    assert datetime.fromisoformat(out["fallback"]["eta"]) == published
    assert out["model"]["version"] == built.metadata["model"]["version"]
    assert out["feature_schema_version"] == built.metadata["feature_schema_version"]


@pytest.mark.parametrize("field, value", [("route_short_name", "Purple-N"), ("stop_id", "Z99-1")])
def test_unknown_route_or_stop_requires_fallback(built, predictor, records, field, value):
    record = _bad(a_record(records), **{field: value})
    assert_fallback(predictor.predict(record), built, record, [{"feature": field, "value": value}])


def test_every_unknown_category_and_value_is_listed(built, predictor, records):
    record = _bad(a_record(records), route_short_name="Purple-N", stop_id="Z99-1")
    assert_fallback(
        predictor.predict(record),
        built,
        record,
        [
            {"feature": "route_short_name", "value": "Purple-N"},
            {"feature": "stop_id", "value": "Z99-1"},
        ],
    )


def test_unseen_hour_inside_the_domain_requires_fallback(built, predictor, records):
    record = a_record(records)  # synthetic training hours are 7 and 8 only
    shift = timedelta(hours=3)
    moved = _bad(
        record,
        snapshot_collected_at=(
            datetime.fromisoformat(record["snapshot_collected_at"]) + shift
        ).isoformat(),
        published_eta=(datetime.fromisoformat(record["published_eta"]) + shift).isoformat(),
        hour_local=record["hour_local"] + 3,
    )
    out = predictor.predict(moved)
    assert_fallback(
        out, built, moved, [{"feature": "hour_local", "value": record["hour_local"] + 3}]
    )


def test_known_records_are_ok_and_never_fall_back(predictor, records):
    for record in records[1]:
        out = predictor.predict(record)
        assert out["status"] == "ok" and out["reason"] is None and out["fallback"] is None
        assert out["unknown_categories"] == []
        assert set(out) == FALLBACK_KEYS


def test_invalid_records_are_rejected_before_any_fallback(predictor, records):
    """Fallback is only for valid records; labels or future fields are never accepted."""
    unknown = _bad(a_record(records), stop_id="Z99-1")
    for extra in (
        "final_stable_estimate",
        "eta_revision_seconds",
        "confirmed_absent_at",
        "last_seen_at",
        "time_to_proxy_s",
        "target_horizon_s",
    ):
        with pytest.raises(RecordError, match="unexpected fields"):
            predictor.predict({**unknown, extra: 0})
    with pytest.raises(RecordError, match="missing fields"):
        predictor.predict(_bad(unknown, stops_away=_DROP))


# -- metadata and artifact verification ----------------------------------------------


def _copy(built, tmp_path):
    target = tmp_path / "bundle"
    shutil.copytree(built.bundle_dir, target)
    return target


def _rewrite(bundle, edit, recompute_id=True):
    path = bundle / "bundle.json"
    meta = json.loads(path.read_text())
    edit(meta)
    if recompute_id:
        meta["bundle_id"] = bundle_id(meta)
    path.write_text(json.dumps(meta))


def test_artifact_bytes_are_verified_before_loading(built, tmp_path):
    bundle = _copy(built, tmp_path)
    data = bytearray((bundle / "regression.joblib").read_bytes())
    data[len(data) // 2] ^= 0xFF
    (bundle / "regression.joblib").write_bytes(bytes(data))
    with pytest.raises(BundleError, match="regression.joblib does not match its recorded SHA-256"):
        Predictor.load(bundle)


@pytest.mark.parametrize(
    "edit, recompute, message",
    [
        (lambda m: m["model"].update(name="other"), False, "altered"),
        (lambda m: m["features"].reverse(), True, "committed constant"),
        (lambda m: m.update(producer="someone-else"), True, "committed constant"),
        (lambda m: m["fallback_behavior"].update(missing_field="fill"), True, "committed constant"),
        (lambda m: m.update(extra_field=1), True, "unexpected keys"),
        (lambda m: m["environment"].update({"scikit-learn": "0.24.2"}), True, "scikit-learn"),
        (lambda m: m["artifacts"][0].update(sha256="0" * 64), True, "SHA-256"),
        (
            lambda m: (
                m["artifacts"].reverse()
                or [
                    a.update(role=r)
                    for a, r in zip(m["artifacts"], ("regression", "classification"), strict=True)
                ]
            ),
            True,
            "wrong kind",
        ),
    ],
)
def test_metadata_tampering_is_rejected(built, tmp_path, edit, recompute, message):
    bundle = _copy(built, tmp_path)
    _rewrite(bundle, edit, recompute)
    with pytest.raises(BundleError, match=message):
        Predictor.load(bundle)


def test_bundle_files_must_match_the_metadata(built, tmp_path):
    bundle = _copy(built, tmp_path)
    (bundle / "notes.txt").write_text("x")
    with pytest.raises(BundleError, match="unexpected \\['notes.txt'\\]"):
        Predictor.load(bundle)
    (bundle / "notes.txt").unlink()
    (bundle / "classification.joblib").unlink()
    with pytest.raises(BundleError, match="missing \\['classification.joblib'\\]"):
        Predictor.load(bundle)


def test_pinned_bundle_id(built):
    Predictor.load(built.bundle_dir, expected_bundle_id=built.metadata["bundle_id"])
    with pytest.raises(BundleError, match="not the pinned build"):
        Predictor.load(built.bundle_dir, expected_bundle_id="f" * 64)


def test_committed_schema_validates_the_metadata(built):
    schema = load_schema(SCHEMA_PATH)
    validate(built.metadata, schema)
    assert constant(schema, "feature_schema_version") == built.metadata["feature_schema_version"]
    names = [f["name"] for f in constant(schema, "features")]
    assert names == list(synthetic_config(built.run_dir).features)
    with pytest.raises(SchemaError):
        # Bundles in the old format (unknown categories took the trees' missing branch)
        # are refused.
        validate({**built.metadata, "bundle_format_version": 1}, schema)


# -- deterministic rebuilding --------------------------------------------------------


def test_rebuild_is_byte_identical(warehouse, built, tmp_path):
    again = build_bundle(
        warehouse, synthetic_config(tmp_path / "run"), bundle_config(tmp_path / "bundle")
    )
    for name in ("bundle.json", "regression.joblib", "classification.joblib"):
        assert (again.bundle_dir / name).read_bytes() == (built.bundle_dir / name).read_bytes()
    assert again.metadata["bundle_id"] == built.metadata["bundle_id"]


# -- interval ------------------------------------------------------------------------


def test_coverage_and_quantiles_by_hand():
    assert coverage([1, 2, 3], [1, 0, 4], [1, 1, 5]) == pytest.approx(1 / 3)  # inclusive
    with pytest.raises(ValueError, match="lower bound above upper"):
        coverage([1], [2], [1])
    assert residual_quantiles(np.arange(101.0), 0.8) == (10.0, 90.0)
    assert residual_quantiles(np.arange(10.0), 0.8) == (0.0, 9.0)  # rounded outward


def _interval_rows(n, residual, bucket=300, trips=None):
    rows = pd.DataFrame(
        {
            "horizon_bucket_s": bucket,
            "predicted_revision_s": 50.0,
            "eta_revision_seconds": 50.0 + residual,
            "service_date": pd.Timestamp("2026-10-13"),
            "trip_run_key": trips if trips is not None else [f"2026-10-13:T{i}" for i in range(n)],
        }
    )
    return rows


def test_calibrate_interval_uses_validation_and_measures_test():
    val = _interval_rows(101, np.arange(-50.0, 51.0))  # residual quantiles -40 .. +40
    test = _interval_rows(10, np.array([-45, -40, -20, 0, 10, 20, 30, 40, 45, 60.0]))
    out = calibrate_interval(val, test, 0.8, 50, 0.05, 50, 1, 0.95)
    h = out["by_horizon"]["300"]
    assert h["residual_quantiles_s"] == [-40.0, 40.0]
    assert h["test_coverage"] == 0.7  # -40 .. 40 inclusive: 7 of 10
    assert out["calibration"]["uses_test_outcomes"] is False
    assert out["calibration"]["reused_for_model_selection"] is True
    assert out["available"] is False and len(out["unavailable_reasons"]) == 2  # horizon, overall
    lenient = calibrate_interval(val, test, 0.8, 50, 0.2, 50, 1, 0.95)
    assert lenient["available"] is True and lenient["unavailable_reasons"] == []
    few = calibrate_interval(val, test, 0.8, 1000, 1.0, 50, 1, 0.95)
    assert few["available"] is False and "fewer than 1000" in few["unavailable_reasons"][0]
    # Test outcomes do not move the calibrated quantiles.
    other = calibrate_interval(val, _interval_rows(10, np.zeros(10)), 0.8, 50, 0.05, 50, 1, 0.95)
    assert other["by_horizon"]["300"]["residual_quantiles_s"] == h["residual_quantiles_s"]


def test_unavailable_interval_returns_no_bounds(built, predictor, records):
    assert built.metadata["interval"]["available"] is False  # 18 synthetic rows per horizon
    iv = predictor.predict(a_record(records))["revision_intervals"][0]
    assert iv["available"] is False and iv["unavailable_reasons"]
    for k in (
        "lower_revision_seconds",
        "upper_revision_seconds",
        "lower_final_published_eta",
        "upper_final_published_eta",
    ):
        assert iv[k] is None
    assert iv["nominal_coverage"] == 0.8 and iv["status"] == "provisional"
    assert iv["empirical_test_coverage"]["this_horizon"] is not None
    assert iv["calibration"]["split"] == "validation"
    assert iv["independently_calibrated"] is False


def test_available_interval_is_ordered_and_matches_calibration(warehouse, built, tmp_path):
    lenient = build_bundle(
        warehouse,
        synthetic_config(tmp_path / "run"),
        bundle_config(tmp_path / "bundle", max_coverage_error=0.99),
    )
    assert lenient.metadata["interval"]["available"] is True
    # Same fitted models, different interval policy: same model version, new bundle_id.
    assert lenient.metadata["model"]["version"] == built.metadata["model"]["version"]
    assert lenient.metadata["bundle_id"] != built.metadata["bundle_id"]
    p = Predictor.load(lenient.bundle_dir)
    with duckdb.connect(str(lenient.run_dir / "features.duckdb"), read_only=True) as con:
        con.execute("SET TimeZone = 'UTC'")
        cfg = synthetic_config(lenient.run_dir)
        rows = served_records(con, cfg, "eta-revision-features-1")
    fields = ["feature_schema_version", "snapshot_collected_at", "published_eta", *cfg.features]
    for _, row in rows.iterrows():
        out = p.predict(to_record(row, fields))
        iv = out["revision_intervals"][0]
        q_lo, q_hi = lenient.metadata["interval"]["by_horizon"][
            str(row["published_horizon_bucket_s"])
        ]["residual_quantiles_s"]
        assert iv["lower_revision_seconds"] <= iv["upper_revision_seconds"]
        assert iv["lower_revision_seconds"] == out["predicted_eta_revision_seconds"] + q_lo
        assert iv["upper_revision_seconds"] == out["predicted_eta_revision_seconds"] + q_hi
        assert iv["lower_final_published_eta"] <= iv["upper_final_published_eta"]
    # Even with an available interval, an unknown category gets no interval at all.
    record = to_record(rows.iloc[0], fields)
    for field, value in (("stop_id", "Z99-1"), ("route_short_name", "Purple-N")):
        out = p.predict({**record, field: value})
        assert out["status"] == "fallback_required" and out["revision_intervals"] == []


# -- no final estimates or future information ----------------------------------------


def test_inference_inputs_are_point_in_time_only(predictor, records):
    required = set(predictor._context) | set(predictor.features)
    assert required.isdisjoint(PROHIBITED_COLUMNS)
    assert set(predictor.features) <= FEATURE_KINDS.keys()
    assert set(records[1][0]) == required  # records are built without any label column
    assert predictor._context == [
        "feature_schema_version",
        "snapshot_collected_at",
        "published_eta",
    ]


def test_predictions_do_not_depend_on_what_happens_after_the_snapshot(built, records, tmp_path):
    """Holding a train on the test day changes later outcomes, not earlier predictions."""
    held_db = build_synthetic_warehouse(tmp_path / "wh", perturb=held)
    other = build_bundle(held_db, synthetic_config(tmp_path / "run"), bundle_config(tmp_path / "b"))
    # Training rows are untouched, so the fitted models are identical...
    for name in ("regression.joblib", "classification.joblib"):
        assert (other.bundle_dir / name).read_bytes() == (built.bundle_dir / name).read_bytes()
    a, b = Predictor.load(built.bundle_dir), Predictor.load(other.bundle_dir)
    rows, recs = records
    before = [r for r in recs if datetime.fromisoformat(r["snapshot_collected_at"]) < HELD_FROM]
    assert before
    for record in before:
        x, y = a.predict(record), b.predict(record)
        assert x["predicted_eta_revision_seconds"] == y["predicted_eta_revision_seconds"]
        assert (
            x["probability_absolute_revision_over_60_seconds"]
            == y["probability_absolute_revision_over_60_seconds"]
        )
    # ... while the held train's later outcomes did change.
    keys = ["event_id", "horizon_bucket_s"]
    labels = [
        pd.read_parquet(b.run_dir / "predictions.parquet").query("split == 'test'")[
            [*keys, "eta_revision_seconds"]
        ]
        for b in (built, other)
    ]
    joined = labels[0].merge(labels[1], on=keys, suffixes=("", "_held"))
    assert (joined["eta_revision_seconds_held"] - joined["eta_revision_seconds"] >= 300).any()


# -- command line --------------------------------------------------------------------


def test_cli_verify_and_predict(built, records, tmp_path, capsys):
    assert (
        cli(
            [
                "verify",
                "--bundle",
                str(built.bundle_dir),
                "--expected-bundle-id",
                built.metadata["bundle_id"],
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["verified"] is True
    path = tmp_path / "record.json"
    path.write_text(json.dumps(a_record(records)))
    assert cli(["predict", "--bundle", str(built.bundle_dir), "--record", str(path)]) == 0
    assert "predicted_eta_revision_seconds" in json.loads(capsys.readouterr().out)
    path.write_text(json.dumps(_bad(a_record(records), stops_away=_DROP)))
    assert cli(["predict", "--bundle", str(built.bundle_dir), "--record", str(path)]) == 1
