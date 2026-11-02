"""The curated showcase replay: selection by coverage, supported records only, the
retrospective outcome kept apart, rankings by realized revision, and the contracts.

Built on the synthetic replay of tests/test_local_api.py; nothing touches the network.
The last test pins the real local artifacts when they are present.
"""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from modeling_fixtures import DAYS, build_synthetic_warehouse, synthetic_config
from referencing import Registry, Resource
from test_local_api import AS_OF, api_config, held
from test_static_replay import spec_for

from bart_reliability.api.replay import ReplayEngine, Snapshot
from bart_reliability.serving.bundle import build_bundle
from bart_reliability.serving.config import load_bundle_config
from bart_reliability.static_replay.check import check_public
from bart_reliability.static_replay.export import export_replay, history_file
from bart_reliability.static_replay.showcase import (
    DISCLOSURE,
    SCHEMATIC_GRID,
    Candidate,
    ShowcaseError,
    candidate_at,
    export_moment,
    largest_changes,
    rank_snapshots,
    select_moment,
)

REPO = Path(__file__).resolve().parents[1]
# The synthetic line A10 -> A60, one schematic cell apart.
SYNTH_GRID = {f"A{10 * i}": (0, i) for i in range(1, 7)}
SCHEMAS = REPO / "docs" / "contracts" / "showcase"
RETROSPECTIVE_KEYS = {
    "finalPublishedEtaAt",
    "finalPublishedEtaSeconds",
    "finalPublishedEtaKnownAt",
    "realizedRevisionSeconds",
    "modelErrorSeconds",
    "directionMatch",
}
FORBIDDEN = (
    "actual arrival",
    "true arrival",
    "train lateness",
    "the train was late",
    "corrected arrival",
)


def tree(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def digests(root: Path) -> dict[str, str]:
    return {k: hashlib.sha256(v).hexdigest() for k, v in tree(root).items()}


def keys_in(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys_in(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys_in(v)}
    return set()


def validator(name: str) -> Draft202012Validator:
    registry = Registry().with_resources(
        (p.name, Resource.from_contents(json.loads(p.read_text())))
        for p in SCHEMAS.glob("*.schema.json")
    )
    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=registry)


# -- fixtures -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory):
    return build_synthetic_warehouse(tmp_path_factory.mktemp("wh"), with_stations=True)


@pytest.fixture(scope="module")
def bundle(warehouse, tmp_path_factory):
    root = tmp_path_factory.mktemp("bundle")
    cfg = replace(
        load_bundle_config(), output_dir=root / "bundle", min_calibration_examples_per_horizon=5
    )
    return build_bundle(warehouse, synthetic_config(root / "run"), cfg)


@pytest.fixture(scope="module")
def setup(warehouse, bundle, tmp_path_factory):
    config = api_config(warehouse, bundle.bundle_dir)
    spec = spec_for(warehouse, bundle, tmp_path_factory.mktemp("spec"))
    snapshot = ReplayEngine(warehouse, AS_OF, 21600).snapshot
    return config, spec, snapshot


@pytest.fixture(scope="module")
def built(setup, bundle, warehouse, tmp_path_factory):
    config, spec, snapshot = setup
    before = {"warehouse": digests(warehouse.parent), "bundle": digests(bundle.bundle_dir)}
    out = tmp_path_factory.mktemp("showcase") / "showcase"
    result = export_moment(config, spec, candidate_at(config, spec, snapshot), out, grid=SYNTH_GRID)
    after = {"warehouse": digests(warehouse.parent), "bundle": digests(bundle.bundle_dir)}
    return result, before, after


def replay_dir(result) -> Path:
    index = json.loads((result.out_root / "replay" / "index.json").read_text())
    return result.out_root / "replay" / index["export"]


def showcase_file(result, name: str) -> dict:
    return json.loads((result.out_root / "showcase" / name).read_text())


def boards(result) -> list[dict]:
    return [
        json.loads(p.read_text()) for p in sorted((replay_dir(result) / "boards").rglob("*.json"))
    ]


# -- selection ----------------------------------------------------------------------------


def candidate(t: datetime, supported, stations=1, trips=1, median=0.0, bound=None):
    return Candidate(t, t, bound or supported, supported, supported, stations, trips, median, {})


def test_snapshots_rank_by_coverage_then_the_earliest_time():
    t0 = datetime(2026, 10, 19, 15, tzinfo=UTC)
    stats = {
        t0: (80, 30, 40, 10.0),
        t0 + timedelta(minutes=1): (82, 30, 40, 10.0),
        t0 + timedelta(minutes=2): (82, 31, 40, 10.0),  # more stations wins
        t0 + timedelta(minutes=3): (82, 31, 40, 12.0),  # then the median breaks the tie
        t0 + timedelta(minutes=4): (82, 31, 40, 12.0),  # a full tie: the earlier time wins
    }
    snaps = {Snapshot(t, t): s[0] for t, s in stats.items()}
    ranked, scan = rank_snapshots(
        snaps, lambda s, b: candidate(s.collected_at, *stats[s.collected_at]), top=5
    )
    assert [c.collected_at for c in ranked] == [t0 + timedelta(minutes=m) for m in (3, 4, 2, 1, 0)]
    assert scan["snapshotsEvaluatedExactly"] == 5


def test_the_bound_skips_only_snapshots_that_cannot_reach_the_top():
    t0 = datetime(2026, 10, 19, 15, tzinfo=UTC)
    supported = [90, 88, 87, 85, 84, 70, 60]
    bounds = [92, 90, 89, 88, 85, 84, 70]  # each bound >= its exact count
    snaps = {
        Snapshot(t0 + timedelta(minutes=i), t0 + timedelta(minutes=i)): b
        for i, b in enumerate(bounds)
    }
    exact = {s.collected_at: n for s, n in zip(snaps, supported, strict=True)}
    seen = []

    def score(s, b):
        seen.append(b)
        return candidate(s.collected_at, exact[s.collected_at], bound=b)

    ranked, scan = rank_snapshots(snaps, score, top=3)
    assert [c.supported for c in ranked] == [90, 88, 87]
    # The third best has 87, so bounds 85, 84 and 70 cannot reach it; 88 had to be tried.
    assert seen == [92, 90, 89, 88]
    assert (scan["stoppedAtBound"], scan["topCutoffSupported"]) == (85, 87)


def test_a_supported_count_above_its_bound_is_an_error(setup):
    config, spec, snapshot = setup
    from bart_reliability.serving.predictor import load_predictor
    from bart_reliability.static_replay.showcase import evaluate, snapshot_trains

    trains = snapshot_trains(config.warehouse, snapshot, load_predictor(config.bundle), config)
    with pytest.raises(ShowcaseError, match="upper bound"):
        evaluate(trains, snapshot, upper_bound=0)


def test_selection_on_the_synthetic_day_is_the_best_coverage(setup):
    config, spec, _ = setup
    ranked, scan = select_moment(config, spec, service_date=DAYS[3], top=3, log=lambda m: None)
    assert ranked == sorted(ranked, key=Candidate.key)
    assert ranked[0].supported == max(c.supported for c in ranked) > 0
    assert (
        scan["snapshotsEvaluatedExactly"] + scan["snapshotsSkippedByBound"]
        == scan["snapshotsOnServiceDay"]
    )
    assert "Accuracy and outcomes are not read" in scan["rule"]


# -- the curated replay -------------------------------------------------------------------


def test_every_exported_train_has_a_supported_forecast(built):
    result, _, _ = built
    trains = [t for b in boards(result) for t in b["trains"]]
    assert trains
    for t in trains:
        assert t["predictionStatus"] == "ok", t["predictionId"]
        # The website shows "BART ETA only" exactly when a train has no forecast.
        assert isinstance(t["predictedRevisionSeconds"], int)
        assert isinstance(t["revisionProbability"], float)
        assert t["stability"] is not None and t["statusReason"] is None


def test_counts_disclose_what_is_left_out(built):
    result, _, _ = built
    counts = showcase_file(result, "showcase.json")["counts"]
    trains = [t for b in boards(result) for t in b["trains"]]
    assert counts["includedRecords"] == len(trains)
    assert (
        counts["includedRecords"] + counts["excludedSupportedWithoutFinalEta"]
        == counts["supportedForecasts"]
    )
    assert (
        counts["supportedForecasts"] + sum(counts["notSupportedByStatus"].values())
        == counts["boardEntries"]
    )
    assert showcase_file(result, "showcase.json")["disclosure"] == DISCLOSURE


def test_every_train_has_its_history_and_only_kept_stations_remain(built):
    result, _, _ = built
    root = replay_dir(result)
    kept = {t["predictionId"] for b in boards(result) for t in b["trains"]}
    histories = {p.relative_to(root).as_posix() for p in (root / "history").rglob("*.json")}
    assert histories == {history_file(p) for p in kept}
    stations = json.loads((root / "stations.json").read_text())
    groups = {(b["stationId"], b["boardingGroupId"]) for b in boards(result)}
    assert {(s["id"], g["id"]) for s in stations for g in s["boardingGroups"]} == groups
    assert all(b["trains"] for b in boards(result))


def test_the_published_replay_passes_the_offline_check(built):
    result, _, _ = built
    summary = check_public(result.out_root / "replay")
    assert summary["counts"]["trainsByStatus"] == {"ok": summary["counts"]["trains"]}


def test_curated_files_are_the_full_api_answers_filtered(built, setup, tmp_path):
    result, _, _ = built
    config, spec, snapshot = setup
    as_of = snapshot.collected_at
    full = export_replay(
        replace(config, as_of=as_of),
        replace(spec, as_of=as_of, source_feed_timestamp=snapshot.feed_timestamp),
        tmp_path,
    )
    ours, theirs = tree(replay_dir(result)), tree(full.out_dir)
    for rel, data in ours.items():
        if rel.startswith("history/"):
            assert data == theirs[rel]
        elif rel.startswith("boards/"):
            mine, api = json.loads(data), json.loads(theirs[rel])
            by_id = {t["predictionId"]: t for t in api["trains"]}
            assert all(t == by_id[t["predictionId"]] for t in mine["trains"])
            assert {k: v for k, v in mine.items() if k != "trains"} == {
                k: v for k, v in api.items() if k != "trains"
            }
        elif rel in ("health.json", "model.json"):
            assert data == theirs[rel]


def test_the_retrospective_outcome_is_stored_apart(built):
    result, _, _ = built
    for rel, data in tree(replay_dir(result)).items():
        assert not keys_in(json.loads(data)) & RETROSPECTIVE_KEYS, rel
    retro = showcase_file(result, "retrospective.json")
    trains = {t["predictionId"]: t for b in boards(result) for t in b["trains"]}
    assert {r["predictionId"] for r in retro["records"]} == set(trains)
    as_of = datetime.fromisoformat(retro["asOf"])
    for r in retro["records"]:
        t = trains[r["predictionId"]]
        bart = datetime.fromisoformat(t["currentEtaAt"])
        final = datetime.fromisoformat(r["finalPublishedEtaAt"])
        assert r["realizedRevisionSeconds"] == (final - bart).total_seconds()
        assert (
            r["modelErrorSeconds"] == t["predictedRevisionSeconds"] - r["realizedRevisionSeconds"]
        )
        # Confirmed only after the replay moment: the model could not have known it.
        assert datetime.fromisoformat(r["finalPublishedEtaKnownAt"]) > as_of
        assert r["directionMatch"] == (r["predictedDirection"] == r["realizedDirection"])


def test_forecasts_do_not_depend_on_anything_after_the_snapshot(built, setup, bundle, tmp_path):
    """Holding a train after the snapshot changes later ETAs, never a forecast.

    Every train's board entry and ETA history are the same bytes. Only two things may
    differ, both retrospective and disclosed: the final published ETAs, and so which
    trains have a tier-A final ETA and are kept.
    """
    result, _, _ = built
    config, spec, snapshot = setup
    held_db = build_synthetic_warehouse(tmp_path / "wh", perturb=held, with_stations=True)
    other_config = api_config(held_db, bundle.bundle_dir)
    other_spec = replace(spec, warehouse_sha256=hashlib.sha256(held_db.read_bytes()).hexdigest())
    other = export_moment(
        other_config,
        other_spec,
        candidate_at(other_config, other_spec, snapshot),
        tmp_path / "o",
        grid=SYNTH_GRID,
    )
    a, b = tree(replay_dir(result)), tree(replay_dir(other))
    for name in ("health.json", "model.json"):
        assert a[name] == b[name]
    trains_a = {t["predictionId"]: t for x in boards(result) for t in x["trains"]}
    trains_b = {t["predictionId"]: t for x in boards(other) for t in x["trains"]}
    shared = trains_a.keys() & trains_b.keys()
    assert shared
    for p in shared:
        assert trains_a[p] == trains_b[p]
        assert a[history_file(p)] == b[history_file(p)]
    # The scan's coverage at the snapshot is computed before any outcome exists.
    assert candidate_at(config, spec, snapshot) == candidate_at(other_config, other_spec, snapshot)
    # Trains kept in one export only differ in the retrospective condition alone.
    ra = {r["predictionId"]: r for r in showcase_file(result, "retrospective.json")["records"]}
    rb = {r["predictionId"]: r for r in showcase_file(other, "retrospective.json")["records"]}
    assert set(ra) == set(trains_a) and set(rb) == set(trains_b)
    changed = {p for p in ra.keys() ^ rb.keys()} | {
        p for p in shared if ra[p]["finalPublishedEtaAt"] != rb[p]["finalPublishedEtaAt"]
    }
    assert changed and all(":T3:" in p for p in changed)


def test_no_model_is_fitted(setup, monkeypatch, tmp_path):
    import sklearn.ensemble
    import sklearn.linear_model
    import sklearn.pipeline

    import bart_reliability.modeling.pipeline as modeling
    import bart_reliability.serving.bundle as serving

    def refuse(*args, **kwargs):
        raise AssertionError("a model was fitted or a bundle built")

    for target, name in [
        (sklearn.pipeline.Pipeline, "fit"),
        (sklearn.ensemble.HistGradientBoostingRegressor, "fit"),
        (sklearn.ensemble.HistGradientBoostingClassifier, "fit"),
        (sklearn.linear_model.HuberRegressor, "fit"),
        (sklearn.linear_model.LogisticRegression, "fit"),
        (modeling, "run_pipeline"),
        (modeling, "fit_and_evaluate"),
        (serving, "build_bundle"),
    ]:
        monkeypatch.setattr(target, name, refuse)
    config, spec, snapshot = setup
    select_moment(config, spec, service_date=DAYS[3], top=2, log=lambda m: None)
    export_moment(
        config, spec, candidate_at(config, spec, snapshot), tmp_path / "s", grid=SYNTH_GRID
    )


def test_the_warehouse_and_bundle_are_unchanged(built):
    _, before, after = built
    assert before == after


# -- rankings -----------------------------------------------------------------------------


def row(pid, horizon, realized, bart_eta, predicted=10):
    return {
        "predictionId": pid,
        "tripRunId": pid.rsplit(":", 1)[0],
        "horizonSeconds": horizon,
        "realizedRevisionSeconds": realized,
        "bartPublishedEtaSeconds": bart_eta,
        "predictedRevisionSeconds": predicted,
    }


def test_rankings_use_the_realized_revision_not_time_away():
    rows = [
        row("2026-10-19:A:1", 900, realized=5, bart_eta=960),  # farthest away, small change
        row("2026-10-19:B:1", 900, realized=-140, bart_eta=850),
        row("2026-10-19:C:1", 900, realized=95, bart_eta=880, predicted=200),
    ]
    ranked = largest_changes(rows)["900"]
    assert [r["predictionId"] for r in ranked] == [
        "2026-10-19:B:1",
        "2026-10-19:C:1",
        "2026-10-19:A:1",
    ]
    assert [r["rank"] for r in ranked] == [1, 2, 3]
    assert ranked[0]["realizedRevisionSeconds"] == -140  # the sign is kept


def test_rankings_are_per_horizon_with_one_row_per_trip_run():
    rows = [
        row(f"2026-10-19:T{i}:{s}", h, realized=10 * i + s, bart_eta=h)
        for h in (300, 600, 900)
        for i in range(4)
        for s in (1, 2)
    ]
    out = largest_changes(rows, per_horizon=5)
    assert set(out) == {"300", "600", "900"}
    for h, ranked in out.items():
        assert all(r["horizonSeconds"] == int(h) for r in ranked)
        assert len(ranked) == 4  # four trip runs, though eight rows
        assert len({r["tripRunId"] for r in ranked}) == len(ranked)
        sizes = [abs(r["realizedRevisionSeconds"]) for r in ranked]
        assert sizes == sorted(sizes, reverse=True)
    # The same trip run may appear once in each horizon.
    assert {r["tripRunId"] for r in out["300"]} == {r["tripRunId"] for r in out["900"]}
    assert len(largest_changes(rows, per_horizon=2)["600"]) == 2


def test_the_published_rankings_follow_the_rules(built):
    result, _, _ = built
    changes = showcase_file(result, "largest-changes.json")
    retro = {r["predictionId"]: r for r in showcase_file(result, "retrospective.json")["records"]}
    assert changes["byHorizon"]
    for h, ranked in changes["byHorizon"].items():
        assert len(ranked) <= 5 and len({r["tripRunId"] for r in ranked}) == len(ranked)
        sizes = [abs(r["realizedRevisionSeconds"]) for r in ranked]
        assert sizes == sorted(sizes, reverse=True)
        best_possible = sorted(
            (abs(r["realizedRevisionSeconds"]) for p, r in retro.items()), reverse=True
        )
        assert not ranked or sizes[0] <= best_possible[0]
        for r in ranked:
            assert r["horizonSeconds"] == int(h)
            assert (
                r["modelAdjustedEtaSeconds"]
                == r["bartPublishedEtaSeconds"] + r["predictedRevisionSeconds"]
            )
            assert (
                r["finalPublishedEtaSeconds"] - r["bartPublishedEtaSeconds"]
                == r["realizedRevisionSeconds"]
            )
            assert (
                r["modelErrorSeconds"]
                == r["predictedRevisionSeconds"] - r["realizedRevisionSeconds"]
            )


def test_network_map_greys_stations_without_a_forecast(built):
    result, _, _ = built
    network = showcase_file(result, "network-map.json")
    stations = {s["stationId"]: s for s in network["stations"]}
    served = {sid for r in network["routes"] for sid in r["stationIds"]}
    assert served <= set(stations)
    counts = {}
    for t in showcase_file(result, "retrospective.json")["records"]:
        counts[t["stationId"]] = counts.get(t["stationId"], 0) + 1
    for sid, s in stations.items():
        assert s["supportedForecastCount"] == counts.get(sid, 0)
        if not s["supportedForecastCount"]:
            assert (
                s["largestPredictedRecord"] is None and s["medianRealizedRevisionSeconds"] is None
            )
        w, h = network["viewBox"][2:]
        assert 0 <= s["x"] <= w and 0 <= s["y"] <= h


# -- contracts and wording ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "schema"),
    [
        ("showcase.json", "showcase"),
        ("retrospective.json", "retrospective"),
        ("largest-changes.json", "largest-changes"),
        ("network-map.json", "network-map"),
    ],
)
def test_showcase_files_validate_against_their_schemas(built, name, schema):
    result, _, _ = built
    v, doc = validator(schema), showcase_file(result, name)
    assert not list(v.iter_errors(doc))
    assert not v.is_valid(doc | {"actualArrival": "2026-10-19T15:00:00Z"})


def test_showcase_lists_the_sha256_of_every_other_file(built):
    result, _, _ = built
    files = showcase_file(result, "showcase.json")["files"]
    for name, entry in files.items():
        data = (result.out_root / "showcase" / name).read_bytes()
        assert entry == {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def test_no_file_uses_physical_arrival_language(built):
    result, _, _ = built
    texts = [p.read_text().lower() for p in (result.out_root / "showcase").glob("*.json")]
    texts.append((REPO / "docs" / "showcase_replay.md").read_text().lower())
    for phrase in FORBIDDEN:
        assert not any(phrase in t for t in texts), phrase


# -- the real local artifacts (skipped where they are not present, as in CI) ---------------

REAL_BUNDLE = REPO / "data" / "models" / "eta_revision_bundle_2026-10-20"
PINNED = {
    "bundle.json": "60f14143548fb4f1911ca051807e8ee4c8f165f3ee52f41f4736c803ee2aab30",
    "classification.joblib": "a89547ce41224f997280ec72b4ba32bd9a51f7ae9a1a3199d14fb31856de950d",
    "regression.joblib": "cdfaa60609eeb15745133a77e62f74a73f3825e60250d4edf861b2e2f24ee917",
}


@pytest.mark.skipif(not REAL_BUNDLE.is_dir(), reason="the local serving bundle is not present")
def test_the_real_bundle_and_model_files_are_unchanged():
    from bart_reliability.serving.predictor import load_predictor
    from bart_reliability.static_replay.export import load_export_spec

    assert {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in REAL_BUNDLE.iterdir()
    } == PINNED
    spec = load_export_spec()
    predictor = load_predictor(REAL_BUNDLE, spec.bundle_id)
    assert predictor.metadata["model"]["version"] == "0.2.0+886fcd260732" == spec.model_version
    warehouse = REPO / "data" / "warehouse" / "bart_checkpoint_2026-10-20.duckdb"
    assert hashlib.sha256(warehouse.read_bytes()).hexdigest() == spec.warehouse_sha256


def test_the_schematic_grid_follows_every_published_route():
    """Every station on the published map has a cell, and consecutive stations of each
    route are neighbouring cells: one step across, down or diagonally, or a short run."""
    network = json.loads((REPO / "web" / "public" / "showcase" / "network-map.json").read_text())
    stations = {s["stationId"] for s in network["stations"]}
    assert stations <= SCHEMATIC_GRID.keys()
    for route in network["routes"]:
        for a, b in zip(route["stationIds"], route["stationIds"][1:], strict=False):
            (ca, ra), (cb, rb) = SCHEMATIC_GRID[a], SCHEMATIC_GRID[b]
            dc, dr = abs(ca - cb), abs(ra - rb)
            assert (dc, dr) != (0, 0), (a, b)
            # Straight or 45 degrees, so the drawing is octilinear.
            assert dc == 0 or dr == 0 or dc == dr, (route["routeShortName"], a, b)
            assert max(dc, dr) <= 3, (route["routeShortName"], a, b)
