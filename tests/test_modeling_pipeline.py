"""End-to-end modeling pipeline on a synthetic multi-day warehouse, plus leakage checks.

The simulator in modeling_fixtures is the oracle: expected example snapshots and feature
values are recomputed from it, independently of the SQL.
"""

import hashlib
import json
from datetime import timedelta

import duckdb
import numpy as np
import pandas as pd
import pytest
from modeling_fixtures import (
    ALERT_DAY,
    ALERT_FROM,
    DAYS,
    PERSIST_S,
    arrival,
    build_synthetic_warehouse,
    estimate,
    local,
    scheduled,
    snapshot_times,
    synthetic_config,
)

from bart_reliability.modeling.config import LeakageError
from bart_reliability.modeling.features import AUDIT_COLUMNS, FEATURES, KEY_COLUMNS
from bart_reliability.modeling.leakage import check_model_inputs, single_feature_alarm
from bart_reliability.modeling.pipeline import fit_and_evaluate, load_frame, run_pipeline

CATALOG = [f.name for f in FEATURES]
WINDOW = 3  # stability_window in config/eta_revision.toml
TOLERANCE = 60

# Trip T3 on the last day is held 300 s from 08:22 onward: every later estimate moves.
PERTURB_DAY, PERTURB_TRIP, PERTURB_FROM = DAYS[3], "T3", local(DAYS[3], 8, 22)


def stuck(day, trip_id, k, now):
    return 300 if (day, trip_id) == (PERTURB_DAY, PERTURB_TRIP) and now >= PERTURB_FROM else 0


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory):
    return build_synthetic_warehouse(tmp_path_factory.mktemp("wh"))


@pytest.fixture(scope="module")
def run(warehouse, tmp_path_factory):
    out = tmp_path_factory.mktemp("runs") / "eta_revision"
    return run_pipeline(warehouse, synthetic_config(out))


def query(path, sql, params=None):
    with duckdb.connect(str(path), read_only=True) as con:
        con.execute("SET TimeZone = 'UTC'")
        cursor = con.execute(sql, params or [])
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]


def features_db(run):
    return run.out_dir / "features.duckdb"


def listings(day, trip_id, k, perturb=None):
    """(snapshot time, published ETA) for every snapshot listing stop k of the trip."""
    out = []
    for now in snapshot_times(day):
        if now < scheduled(day, trip_id, 0) - timedelta(minutes=30):
            continue
        eta = estimate(day, trip_id, k, now, perturb)
        if now < max(arrival(day, trip_id, k), eta) + timedelta(seconds=PERSIST_S):
            out.append((now, eta))
    return out


def first_listed_position(day, trip_id, now):
    for k in range(5):
        if any(t == now for t, _ in listings(day, trip_id, k)):
            return k + 1
    raise AssertionError("trip not listed")


def h(now, eta):
    return int((eta - now).total_seconds())


def test_feature_checks_pass_and_every_event_horizon_has_an_example(run):
    checks = run.manifest["feature_build"]["checks"]
    assert checks and all(v == 0 for v in checks.values())
    assert run.manifest["feature_build"]["eligible_events"] == 72  # 3 stops x 6 trips x 4 days
    assert run.manifest["feature_build"]["examples"] == 216
    assert run.manifest["feature_build"]["missing_by_reason"] == {}


@pytest.mark.parametrize("day, trip_id, k", [(DAYS[0], "T5", 2), (DAYS[2], "T2", 3)])
def test_examples_are_chosen_by_published_horizon(run, day, trip_id, k):
    seq = [1, 3, 4, 6, 7, 8][k]
    rows = query(
        features_db(run),
        "SELECT * FROM eta_model_examples WHERE event_id = ? ORDER BY published_horizon_bucket_s",
        [f"{day}:{trip_id}:{seq}"],
    )
    listed = listings(day, trip_id, k)
    usable = listed[:-WINDOW]  # the final window defines the endpoint
    final = listed[-1][1]
    for row in rows:
        b = row["published_horizon_bucket_s"]
        near = [(abs(h(t, e) - b), t, e) for t, e in usable if abs(h(t, e) - b) <= TOLERANCE]
        _, t, e = min(near, key=lambda x: (x[0], x[1]))  # closest; ties to the earlier
        assert row["prediction_collected_at"] == t
        assert row["published_horizon_s"] == h(t, e)
        assert row["final_stable_estimate"] == final
        assert row["eta_revision_seconds"] == int((final - e).total_seconds())
    assert [r["published_horizon_bucket_s"] for r in rows] == [300, 600, 900]


def test_feature_values_match_the_simulator(run):
    day, trip_id, k = DAYS[0], "T5", 2
    rows = query(
        features_db(run),
        "SELECT * FROM eta_model_features WHERE event_id = ? ORDER BY published_horizon_bucket_s",
        [f"{day}:{trip_id}:4"],
    )
    listed = listings(day, trip_id, k)
    for row in rows:
        now = row["prediction_collected_at"]
        upto = [(t, e) for t, e in listed if t <= now]
        eta = upto[-1][1]
        trailing = [(t, e) for t, e in upto if t >= now - timedelta(seconds=300)]
        changes = [
            int((b - a).total_seconds()) for (_, a), (_, b) in zip(upto, upto[1:], strict=False)
        ]
        assert row["published_horizon_s"] == h(now, eta)
        assert row["published_minus_scheduled_s"] == int(
            (eta - scheduled(day, trip_id, k)).total_seconds()
        )
        assert row["seconds_since_first_seen"] == int((now - upto[0][0]).total_seconds())
        assert row["eta_change_last_snapshot_s"] == (changes[-1] if changes else 0)
        assert row["eta_change_last_5min_s"] == int((eta - trailing[0][1]).total_seconds())
        assert row["eta_change_since_first_seen_s"] == int((eta - upto[0][1]).total_seconds())
        assert row["prior_change_count"] == sum(c != 0 for c in changes)
        assert row["prior_abs_change_sum_s"] == sum(abs(c) for c in changes)
        assert row["stop_position"] == k + 1
        assert row["stops_away"] == k + 1 - first_listed_position(day, trip_id, now)
        assert row["missing_snapshots_so_far"] == 0
        assert row["hour_local"] == (now - timedelta(hours=7)).hour  # PDT
        assert row["service_day_type"] == "weekday"
        assert row["route_short_name"] == "Yellow-S"
        assert row["history_last_collected_at"] == now


def test_alert_context_is_point_in_time(run):
    rows = query(
        features_db(run),
        "SELECT e.service_date, f.prediction_collected_at, f.has_applicable_visible_alert, "
        "f.alert_context_group, f.alert_snapshot_feed_timestamp FROM eta_model_features f "
        "JOIN eta_model_examples e USING (event_id, published_horizon_bucket_s)",
    )
    alert_from = local(ALERT_DAY, *ALERT_FROM)
    for r in rows:
        assert r["alert_snapshot_feed_timestamp"] <= r["prediction_collected_at"]
        visible = r["service_date"] == ALERT_DAY and r["prediction_collected_at"] >= alert_from
        assert r["has_applicable_visible_alert"] == str(visible).lower()
        if visible:
            assert r["alert_context_group"] == "applicable_visible_unclassified"
    assert any(r["has_applicable_visible_alert"] == "true" for r in rows)


def test_observations_after_the_snapshot_never_change_its_features(run, tmp_path):
    """Holding a train after T changes later labels but not features at or before T."""
    perturbed_db = build_synthetic_warehouse(tmp_path / "wh", perturb=stuck)
    perturbed = run_pipeline(perturbed_db, synthetic_config(tmp_path / "run"))
    cols = ", ".join(
        ["event_id", "published_horizon_bucket_s", "prediction_collected_at", *CATALOG]
    )
    sql = f"SELECT {cols} FROM eta_model_features WHERE prediction_collected_at < ? ORDER BY 1, 2"
    before = query(features_db(run), sql, [PERTURB_FROM])
    after = query(features_db(perturbed), sql, [PERTURB_FROM])
    assert before and before == after

    # The perturbation was real: labels of examples published before T moved by at least
    # 300 s (a little more, because the held train keeps accumulating delay).
    lsql = (
        "SELECT event_id, published_horizon_bucket_s, eta_revision_seconds FROM eta_model_examples "
        "WHERE event_id LIKE ? AND prediction_collected_at < ? ORDER BY 1, 2"
    )
    params = [f"{PERTURB_DAY}:{PERTURB_TRIP}:%", PERTURB_FROM]
    a, b = query(features_db(run), lsql, params), query(features_db(perturbed), lsql, params)
    moved = [
        y["eta_revision_seconds"] - x["eta_revision_seconds"] for x, y in zip(a, b, strict=True)
    ]
    assert any(m >= 300 for m in moved)


def test_validation_and_test_labels_cannot_change_fitted_models(run):
    cfg = synthetic_config(run.out_dir)
    with duckdb.connect(str(features_db(run)), read_only=True) as con:
        con.execute("SET TimeZone = 'UTC'")
        frame = load_frame(con, cfg)
    metrics, artifacts = fit_and_evaluate(frame, cfg)

    scrambled = frame.copy()
    later = scrambled["split"] != "train"
    scrambled.loc[later, "eta_revision_seconds"] = -scrambled.loc[later, "eta_revision_seconds"] + 7
    scrambled.loc[later, "large_revision"] = 1 - scrambled.loc[later, "large_revision"]
    _, scrambled_artifacts = fit_and_evaluate(scrambled, cfg)

    pd.testing.assert_frame_equal(
        artifacts["historical_groups"], scrambled_artifacts["historical_groups"]
    )
    # Every predeclared sensitivity setting is fitted on training rows only too.
    assert set(artifacts["sensitivity_groups"]) == set(cfg.baseline_sensitivity_min_group_sizes)
    for size, groups in artifacts["sensitivity_groups"].items():
        pd.testing.assert_frame_equal(groups, scrambled_artifacts["sensitivity_groups"][size])
    model_cols = [
        c
        for c in artifacts["predictions"]
        if c.startswith(("revision_s__", "large_revision_probability__"))
    ]
    val = artifacts["predictions"]["split"] == "validation"
    pd.testing.assert_frame_equal(
        artifacts["predictions"].loc[val, model_cols],
        scrambled_artifacts["predictions"].loc[val, model_cols],
    )

    # Sensitivity: changing training labels does change the fit.
    shifted = frame.copy()
    shifted.loc[shifted["split"] == "train", "eta_revision_seconds"] += 50
    _, shifted_artifacts = fit_and_evaluate(shifted, cfg)
    assert not artifacts["historical_groups"].equals(shifted_artifacts["historical_groups"])


def test_selected_models_alone_are_scored_on_test(run):
    m = run.metrics
    selected = m["selection"]
    assert set(m["test"]["regression"]) == {
        "no_revision",
        "historical",
        selected["regression"]["selected"],
    }
    assert set(m["test"]["classification"]) == {
        "no_revision",
        "historical",
        selected["classification"]["selected"],
    }
    assert len(m["validation"]["regression"]) == 2 + len(selected["regression"]["scores"])
    preds = pd.read_parquet(run.out_dir / "predictions.parquet")
    test = preds[preds["split"] == "test"]
    for task, prefix in (
        ("regression", "revision_s__"),
        ("classification", "large_revision_probability__"),
    ):
        for name in selected[task]["scores"]:
            column = test[f"{prefix}{name}"]
            assert (
                column.notna().all() if name == selected[task]["selected"] else column.isna().all()
            )


def test_metrics_carry_sample_sizes_and_dates(run):
    m = run.metrics
    assert m["provisional"] is True
    assert m["samples"]["test"]["service_dates"] == [str(DAYS[3]), str(DAYS[3])]
    for split in ("validation", "test"):
        for task in ("regression", "classification"):
            for block in m[split][task].values():
                for b in [block["overall"], *block["by_horizon"].values()]:
                    assert b["examples"] > 0 and b["events"] > 0 and len(b["service_dates"]) == 2
            assert set(next(iter(m[split][task].values()))["by_horizon"]) == {"300", "600", "900"}
    assert m["single_feature_alarm"]["single_feature_roc_auc_train"]


def test_artifacts_are_written(run):
    names = {p.name for p in run.out_dir.iterdir()}
    assert names == {
        "features.duckdb",
        "predictions.parquet",
        "historical_baseline.parquet",
        "models",
        "metrics.json",
        "report.md",
        "run_manifest.json",
        "historical_baseline_sensitivity.parquet",
        "bootstrap_replicates.parquet",
    }
    assert len(list((run.out_dir / "models").glob("*.joblib"))) == 10
    assert json.loads((run.out_dir / "metrics.json").read_text()) == run.metrics
    assert "Provisional" in (run.out_dir / "report.md").read_text()


def test_rerun_is_reproducible(run, warehouse, tmp_path):
    again = run_pipeline(warehouse, synthetic_config(tmp_path / "again"))
    assert again.metrics == run.metrics
    for name in ("predictions.parquet", "historical_baseline.parquet"):
        pd.testing.assert_frame_equal(
            pd.read_parquet(again.out_dir / name), pd.read_parquet(run.out_dir / name)
        )
    assert again.manifest["frame_fingerprint_sha256"] == run.manifest["frame_fingerprint_sha256"]


def test_warehouse_is_never_modified(warehouse, tmp_path):
    before = hashlib.sha256(warehouse.read_bytes()).hexdigest()
    run_pipeline(warehouse, synthetic_config(tmp_path / "out"))
    assert hashlib.sha256(warehouse.read_bytes()).hexdigest() == before


def test_failed_run_keeps_the_previous_output(run, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("previous run")
    with pytest.raises(FileNotFoundError):
        run_pipeline(tmp_path / "missing.duckdb", synthetic_config(out))
    assert (out / "keep.txt").read_text() == "previous run"
    assert not (tmp_path / ".out.building").exists()


def test_feature_table_holds_only_keys_catalog_and_audit_columns(run):
    columns = [r["column_name"] for r in query(features_db(run), "DESCRIBE eta_model_features")]
    assert set(columns) == set(KEY_COLUMNS) | set(CATALOG) | set(AUDIT_COLUMNS)


def test_single_feature_alarm_catches_a_label_copy(run):
    cfg = synthetic_config(run.out_dir)
    with duckdb.connect(str(features_db(run)), read_only=True) as con:
        con.execute("SET TimeZone = 'UTC'")
        frame = load_frame(con, cfg)
    train = frame[frame["split"] == "train"].copy()
    assert max(single_feature_alarm(train, cfg).values()) < 0.95
    train["published_horizon_s"] = train["large_revision"] * 1000.0 + np.arange(len(train)) % 3
    with pytest.raises(LeakageError, match="implausibly well"):
        single_feature_alarm(train, cfg)


def test_model_inputs_must_match_the_configured_features(run):
    cfg = synthetic_config(run.out_dir)
    check_model_inputs(list(cfg.features), cfg)
    with pytest.raises(LeakageError):
        check_model_inputs([*cfg.features, "eta_revision_seconds"], cfg)


def test_trip_clustered_bootstrap_is_primary_and_event_is_sensitivity(run):
    unc = run.metrics["uncertainty"]
    assert unc["replicates"] == 300 and unc["seed"] == synthetic_config(run.out_dir).seed
    # Test day: 6 trip runs, each with 3 stop-arrival events at 3 published-time horizons.
    assert (unc["trips"], unc["events"], unc["examples"]) == (6, 18, 54)
    assert unc["service_dates"] == [str(DAYS[3]), str(DAYS[3])]
    trip, event = unc["primary_trip_clustered"], unc["sensitivity_event_clustered"]
    assert (trip["cluster_column"], trip["clusters"]) == ("trip_run_key", 6)
    assert (event["cluster_column"], event["clusters"]) == ("event_id", 18)
    for phrase in (
        "conditional on the single test day",
        "day-to-day variability",
        "system-wide conditions",
        "cannot establish generalization",
    ):
        assert phrase in unc["scope"] and phrase in trip["note"]
    assert "correlated" in event["note"]
    test = run.metrics["test"]
    reg = run.metrics["selection"]["regression"]["selected"]
    observed_mae = (
        test["regression"][reg]["overall"]["mae_s"]
        - test["regression"]["historical"]["overall"]["mae_s"]
    )
    for block in (trip, event):
        d = block["selected_minus_historical"]
        assert set(d) == {"mae_s", "brier", "pr_auc"}
        assert set(d["mae_s"]["by_horizon"]) == {"300", "600", "900"}
        assert d["mae_s"]["overall"]["observed"] == pytest.approx(observed_mae, abs=0.01)
        for b in (d["mae_s"]["overall"], d["brier"], d["pr_auc"]):
            assert b["ci_low"] <= b["observed"] <= b["ci_high"]
            assert 0 <= b["share_of_replicates_model_better"] <= 1
    # Same observed differences, different resampling: the intervals differ.
    assert (
        trip["selected_minus_historical"]["mae_s"]["overall"]["ci_low"]
        != event["selected_minus_historical"]["mae_s"]["overall"]["ci_low"]
    )
    draws = pd.read_parquet(run.out_dir / "bootstrap_replicates.parquet")
    assert draws["clustering"].value_counts().to_dict() == {"trip": 300, "event": 300}


def test_trip_runs_are_keyed_by_service_date_and_trip(run):
    cfg = synthetic_config(run.out_dir)
    with duckdb.connect(str(features_db(run)), read_only=True) as con:
        con.execute("SET TimeZone = 'UTC'")
        frame = load_frame(con, cfg)
    # The same six trip_ids run on all four days: 24 distinct trip runs, never merged.
    assert frame["trip_id"].nunique() == 6
    assert frame["trip_run_key"].nunique() == 24
    assert frame.groupby("trip_run_key")["service_date"].nunique().eq(1).all()
    assert frame.groupby("event_id")["trip_run_key"].nunique().eq(1).all()
    assert (frame["trip_run_key"] == frame["event_id"].str.rsplit(":", n=1).str[0]).all()
    assert "trip_id" not in cfg.features and "trip_run_key" not in cfg.features


def test_sensitivity_keeps_the_primary_setting_and_reports_every_size(run):
    sens = run.metrics["historical_baseline_sensitivity"]
    assert sens["primary_min_group_size"] == 3
    assert list(sens["settings"]) == ["3", "6", "12", "40"]
    assert [s["primary"] for s in sens["settings"].values()] == [True, False, False, False]
    primary = sens["settings"]["3"]["test"]
    assert (
        primary["historical_mae_s"]
        == (run.metrics["test"]["regression"]["historical"]["overall"]["mae_s"])
    )
    # Sensitivity intervals use the primary (trip-clustered) resampling.
    assert (
        primary["paired_trip_bootstrap"]
        == run.metrics["uncertainty"]["primary_trip_clustered"]["selected_minus_historical"]
    )
    # Larger minimum sizes push rows to coarser fallback levels; the largest has no
    # bucket x route x stop group at all.
    largest = sens["settings"]["40"]
    assert (
        "published_horizon_bucket_s+route_short_name+stop_id"
        not in largest["fitted_groups_by_level"]
    )
    assert set(sens["test_conclusion_same_for_every_setting"]) >= {"mae_s", "brier", "pr_auc"}


def test_report_terminology_is_accurate(run):
    report = (run.out_dir / "report.md").read_text()
    sel = run.metrics["selection"]
    reg, cls = sel["regression"]["selected"], sel["classification"]["selected"]
    for phrase in [
        "published-time horizon",
        "not independently observed time before physical arrival",
        "Huber regression is a robust linear comparator",
        "does not directly optimize MAE",
        f"The regression model `{reg}` was selected using validation MAE",
        f"the classifier `{cls}` using validation Brier score",
        "Models were not refitted on validation data",
        "descriptive operating point, not an optimized deployment threshold",
        "explicit rider or product cost",
        "## Test uncertainty (primary): trip-clustered bootstrap",
        "## Sensitivity: event-clustered bootstrap",
        "conditional on the single test day",
        "do not capture day-to-day variability",
        "system-wide conditions shared by many trips",
        "cannot establish generalization to future service days",
        "narrower than the trip-clustered ones because events from the same trip are correlated",
        "Intervals are trip-clustered",
        "not proof that leakage is absent",
    ]:
        assert phrase in report, phrase
    assert "closer to the MAE objective" not in report
    # No linear candidate is labelled as selected when the tree was selected.
    assert not reg.startswith("linear")
    for line in report.splitlines():
        if line.startswith("| linear_huber"):
            assert "| linear comparator |" in line
    assert (
        f"## Linear comparator (not selected): `{run.metrics['linear_comparator']['model']}`"
        in report
    )
