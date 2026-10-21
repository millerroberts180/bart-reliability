"""Local historical-replay API, tested end to end on deterministic synthetic fixtures.

The warehouse comes from modeling_fixtures (four service days, six trips, BART-like
feeds) and the bundle from the real build command. Nothing touches the network.
"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta

import duckdb
import pytest
from boarding_fixtures import AS_OF as HAYWARD_AS_OF
from boarding_fixtures import build_hayward_warehouse
from fastapi.testclient import TestClient
from modeling_fixtures import (
    ALERT_DAY,
    ALERT_FROM,
    DAYS,
    build_synthetic_warehouse,
    local,
    synthetic_config,
)

import bart_reliability.api.app as api_app
from bart_reliability.api.app import ApiState, create_app, train_prediction
from bart_reliability.api.config import ApiConfigError, load_api_config
from bart_reliability.api.main import main as serve_main
from bart_reliability.api.replay import (
    FEATURE_COLUMNS,
    ReplayEngine,
    allowed_sources,
    prediction_id,
)
from bart_reliability.modeling.features import PROHIBITED_COLUMNS
from bart_reliability.serving.bundle import build_bundle
from bart_reliability.serving.config import load_bundle_config

AS_OF = local(DAYS[3], 8, 16, 30)  # test day, 08:16:30 PDT; latest snapshot 08:16:00
HELD_FROM = local(DAYS[3], 8, 22)  # after AS_OF


def held(day, trip_id, k, now):
    return 300 if (day, trip_id) == (DAYS[3], "T3") and now >= HELD_FROM else 0


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


def api_config(warehouse, bundle_dir, as_of=AS_OF, **overrides):
    # The repository config pins the real local bundle; synthetic bundles opt in.
    return replace(
        load_api_config(),
        as_of=as_of,
        warehouse=warehouse,
        bundle=bundle_dir,
        **({"bundle_id": None} | overrides),
    )


@pytest.fixture(scope="module")
def client(warehouse, bundle):
    return TestClient(create_app(api_config(warehouse, bundle.bundle_dir)))


BOARD_A30 = "/api/v1/stations/A30/predictions?boarding_group=to-A40"


def group_of(station: str) -> str:
    """The synthetic line runs A10 -> A60, so each station's only boarding group leads to
    the next station."""
    return f"to-A{int(station[1:]) + 10}"


def predictions(client, station="A30", group=None):
    r = client.get(
        f"/api/v1/stations/{station}/predictions",
        params={"boarding_group": group or group_of(station)},
    )
    assert r.status_code == 200, r.json()
    return r.json()


# -- TypeScript contract (web/src/domain/types.ts) -----------------------------------

STR, INT, NUM, BOOL, LIST, OBJ, NULL = "string", "int", "number", "bool", "list", "object", "null"
CONTRACT = {
    "Station": {"id": STR, "name": STR, "boardingGroups": LIST, "endOfLine": BOOL},
    "BoardingGroup": {
        "id": STR,
        "label": STR,
        "destinations": LIST,
        "platform": (STR, NULL),
        "gtfsDirectionIds": LIST,
    },
    "TrainPrediction": {
        "predictionId": STR,
        "tripId": STR,
        "lineName": STR,
        "headsign": STR,
        "carCount": (INT, NULL),
        "currentEtaSeconds": INT,
        "currentEtaAt": STR,
        "platform": (STR, NULL),
        "predictedRevisionSeconds": NUM,
        "revisionInterval": OBJ,
        "revisionProbability": NUM,
        "stability": STR,
    },
    "RevisionInterval": {"lowerSeconds": NUM, "upperSeconds": NUM, "level": NUM},
    "PredictionHistoryPoint": {
        "feedTimestamp": STR,
        "publishedEtaAt": STR,
        "publishedEtaSeconds": NUM,
    },
    "AlertContext": {
        "alertId": STR,
        "scope": STR,
        "category": STR,
        "headerText": STR,
        "visibleSince": STR,
    },
    "ModelMetadata": {
        "modelVersion": STR,
        "trainedThrough": STR,
        "revisionThresholdSeconds": NUM,
        "simulated": BOOL,
    },
    "PredictionResponse": {
        "stationId": STR,
        "boardingGroupId": STR,
        "feedTimestamp": STR,
        "generatedAt": STR,
        "trains": LIST,
        "unplacedTrainCount": INT,
        "terminatingTrainCount": INT,
        "alerts": LIST,
        "model": OBJ,
    },
    "HealthStatus": {"status": STR, "latestFeedTimestamp": STR},
}
# Documented in docs/local_api.md ("Contract differences"): model fields are null when a
# train is outside model support or the interval is unavailable, and the latest feed
# time is null only when no feed is loaded.
NULLABLE_DELTAS = {
    ("TrainPrediction", "predictedRevisionSeconds"),
    ("TrainPrediction", "revisionInterval"),
    ("TrainPrediction", "revisionProbability"),
    ("TrainPrediction", "stability"),
    ("HealthStatus", "latestFeedTimestamp"),
}
ENUMS = {
    ("TrainPrediction", "stability"): {"likely_to_hold", "may_be_revised", "likely_to_be_revised"},
    ("AlertContext", "scope"): {"system", "route", "station"},
    ("AlertContext", "category"): {"planned_work", "incident", "unclassified"},
    ("HealthStatus", "status"): {"ok", "degraded"},
}


def _json_type(value):
    if value is None:
        return NULL
    if isinstance(value, bool):
        return BOOL
    if isinstance(value, int):
        return INT
    if isinstance(value, float):
        return NUM
    return {str: STR, list: LIST, dict: OBJ}[type(value)]


def conforms(name: str, obj: dict) -> None:
    for field, expected in CONTRACT[name].items():
        assert field in obj, f"{name}.{field} missing"
        allowed = set(expected) if isinstance(expected, tuple) else {expected}
        if NUM in allowed:
            allowed |= {INT}
        if (name, field) in NULLABLE_DELTAS:
            allowed.add(NULL)
        actual = _json_type(obj[field])
        assert actual in allowed, f"{name}.{field}: {actual} not in {allowed}"
        if (name, field) in ENUMS and obj[field] is not None:
            assert obj[field] in ENUMS[(name, field)]


def test_responses_satisfy_the_typescript_contract(client):
    for station in client.get("/api/v1/stations").json():
        conforms("Station", station)
        for group in station["boardingGroups"]:
            conforms("BoardingGroup", group)
    body = predictions(client)
    conforms("PredictionResponse", body)
    conforms("ModelMetadata", body["model"])
    for train in body["trains"]:
        conforms("TrainPrediction", train)
        if train["revisionInterval"] is not None:
            conforms("RevisionInterval", train["revisionInterval"])
    for alert in body["alerts"]:
        conforms("AlertContext", alert)
    conforms("HealthStatus", client.get("/api/v1/health").json())
    conforms("ModelMetadata", client.get("/api/v1/model/metadata").json())
    pid = body["trains"][0]["predictionId"]
    for point in client.get(f"/api/v1/predictions/{pid}/history").json():
        conforms("PredictionHistoryPoint", point)


def test_supported_trains_have_every_contract_field_non_null(client):
    trains = [t for t in predictions(client)["trains"] if t["predictionStatus"] == "ok"]
    assert trains
    for t in trains:
        assert t["predictedRevisionSeconds"] is not None
        assert t["revisionProbability"] is not None and t["stability"] is not None


# -- replay identification, freshness, model and schema versions ---------------------


def test_every_response_identifies_historical_replay(client):
    paths = [
        "/api/v1/health",
        "/api/v1/stations",
        "/api/v1/model/metadata",
        BOARD_A30,
        "/api/v1/stations/NOPE/predictions?boarding_group=to-A40",
        "/api/v1/nothing",
    ]
    for path in paths:
        r = client.get(path)
        assert r.headers["x-data-mode"] == "historical-replay"
        assert r.headers["x-replay-as-of"] == "2026-10-09T15:16:30Z"
        body = r.json()
        if isinstance(body, dict):
            mode = body.get("dataMode") or body.get("error", {}).get("dataMode")
            assert mode == "historical_replay", path


def test_prediction_response_carries_source_freshness_and_versions(client, bundle):
    body = predictions(client)
    assert body["feedTimestamp"] == "2026-10-09T15:16:00Z"
    assert body["generatedAt"] == "2026-10-09T15:16:30Z"
    replay = body["replay"]
    assert replay == {
        "dataMode": "historical_replay",
        "asOf": "2026-10-09T15:16:30Z",
        "sourceTimestamp": "2026-10-09T15:16:00Z",
        "collectedAt": "2026-10-09T15:16:00Z",
        "freshnessSeconds": 30,
        "stale": False,
        "staleAfterSeconds": 120,
    }
    meta = bundle.metadata
    assert body["model"]["modelVersion"] == meta["model"]["version"]
    assert body["model"]["featureSchemaVersion"] == "eta-revision-features-1"
    assert body["model"]["trainedThrough"] == meta["training_data"]["training_data_cutoff_utc"]
    assert body["model"]["simulated"] is False and body["model"]["provisional"] is True
    health = client.get("/api/v1/health").json()
    assert health["status"] == "ok" and health["problems"] == []
    assert health["latestFeedTimestamp"] == "2026-10-09T15:16:00Z"
    assert health["freshnessSeconds"] == 30


# -- predictions: model outputs and honest fallbacks ---------------------------------


def test_board_statuses_and_presentation_fields(client):
    body = predictions(client, "A30")
    statuses = {t["tripId"]: t["predictionStatus"] for t in body["trains"]}
    assert statuses == {
        "T3": "ok",
        "T4": "ok",
        "T5": "outside_model_horizon",
        "T6": "outside_model_horizon",
    }
    etas = [t["currentEtaSeconds"] for t in body["trains"]]
    assert etas == sorted(etas) and min(etas) >= 0
    t3 = next(t for t in body["trains"] if t["tripId"] == "T3")
    assert t3["lineName"] == "Yellow line" and t3["headsign"] == "Somewhere"
    assert (t3["stationId"], t3["stopId"], t3["gtfsDirectionId"]) == ("A30", "A30-1", "0")
    assert body["boardingGroupId"] == "to-A40" and t3["platform"] is None  # no platform codes
    assert t3["predictionId"] == f"{DAYS[3]}:T3:4"
    # Origin stops are a population the models never saw.
    origin = predictions(client, "A10")["trains"]
    assert origin and {t["predictionStatus"] for t in origin} == {"outside_model_population"}
    assert all("trip origin" in t["statusReason"] for t in origin)


# -- boarding groups: Hayward (docs/boarding_groups.md) ------------------------------


@pytest.fixture(scope="module")
def hayward(tmp_path_factory, bundle):
    db = build_hayward_warehouse(tmp_path_factory.mktemp("hayward"))
    return TestClient(create_app(api_config(db, bundle.bundle_dir, as_of=HAYWARD_AS_OF)))


def test_hayward_groups_follow_the_platforms_not_direction_id(hayward):
    stations = {s["id"]: s for s in hayward.get("/api/v1/stations").json()}
    assert stations["A60"] == {
        "id": "A60",
        "name": "Hayward",
        "endOfLine": False,
        "boardingGroups": [
            {
                "id": "to-A70",
                "label": "Toward Berryessa/North San Jose",
                "destinations": ["Berryessa", "Berryessa/North San Jose"],
                "platform": "1",
                # Both ids on each side, so an old ?direction= link cannot be translated.
                "gtfsDirectionIds": ["0", "1"],
            },
            {
                "id": "to-A50",
                "label": "Toward Daly City and Richmond",
                "destinations": ["Daly City", "Richmond"],
                # The bus bridge stops on platform 1; buses are not trains and do not count.
                "platform": "2",
                "gtfsDirectionIds": ["0", "1"],
            },
        ],
    }
    # Every train at the ends of this little line starts or ends its trip there.
    for end in ("A50", "A70"):
        assert stations[end]["endOfLine"] is True
        assert len(stations[end]["boardingGroups"]) == 1


def test_hayward_boards_never_mix_berryessa_with_daly_city_or_richmond(hayward):
    north = predictions(hayward, "A60", "to-A50")
    south = predictions(hayward, "A60", "to-A70")
    assert north["boardingGroupId"] == "to-A50" and south["boardingGroupId"] == "to-A70"

    def placed(board):
        return {t["tripId"]: (t["headsign"], t["platform"]) for t in board["trains"]}

    assert placed(north) == {"OR_N": ("Richmond", "2"), "GR_S": ("Daly City", "2")}
    assert placed(south) == {
        "OR_S": ("Berryessa/North San Jose", "1"),
        "GR_N": ("Berryessa", "1"),
        # Listed at platform 2 although scheduled at 1: placed by its schedule, and no
        # platform is claimed for it.
        "OR_MOVED": ("Berryessa/North San Jose", None),
    }
    for board in (north, south):
        # Both GTFS direction ids on each board: direction_id does not place trains.
        assert {t["gtfsDirectionId"] for t in board["trains"]} == {"0", "1"}
        # The unmatched train is not given a direction; the train ending here is not boarded.
        assert board["unplacedTrainCount"] == 1
        assert board["terminatingTrainCount"] == 1
    assert "RT_ONLY" not in placed(north) | placed(south)
    assert "GR_END" not in placed(north) | placed(south)


def test_ok_predictions_match_the_bundle_and_derive_consistently(client, bundle):
    from bart_reliability.serving import Predictor

    predictor = Predictor.load(bundle.bundle_dir)
    for t in predictions(client)["trains"]:
        if t["predictionStatus"] != "ok":
            assert t["predictedRevisionSeconds"] is None and t["revisionInterval"] is None
            assert t["revisionProbability"] is None and t["stability"] is None
            assert t["fallbackEtaAt"] == t["currentEtaAt"]
            continue
        current = datetime.fromisoformat(t["currentEtaAt"])
        final = datetime.fromisoformat(t["likelyFinalEtaAt"])
        assert t["likelyFinalEtaSeconds"] == t["currentEtaSeconds"] + t["predictedRevisionSeconds"]
        assert final == current + timedelta(seconds=t["predictedRevisionSeconds"])
        p = t["revisionProbability"]
        expected = (
            "likely_to_be_revised"
            if p >= 0.5
            else "may_be_revised"
            if p >= 0.25
            else "likely_to_hold"
        )
        assert t["stability"] == expected
        assert t["fallbackEtaAt"] is None
    assert predictor.metadata["interval"]["available"] is False  # tiny synthetic sample


def test_unavailable_interval_is_null_with_reasons(client):
    for t in predictions(client)["trains"]:
        if t["predictionStatus"] == "ok":
            assert t["revisionInterval"] is None
            assert t["revisionIntervalStatus"]["available"] is False
            assert t["revisionIntervalStatus"]["unavailableReasons"]


def test_available_interval_is_returned_and_rounded_outward(warehouse, tmp_path):
    lenient = build_bundle(
        warehouse,
        synthetic_config(tmp_path / "run"),
        replace(
            load_bundle_config(),
            output_dir=tmp_path / "b",
            min_calibration_examples_per_horizon=5,
            max_coverage_error=0.99,
        ),
    )
    c = TestClient(create_app(api_config(warehouse, lenient.bundle_dir)))
    ok = [t for t in predictions(c)["trains"] if t["predictionStatus"] == "ok"]
    assert ok
    for t in ok:
        iv = t["revisionInterval"]
        assert iv["level"] == 0.8 and iv["lowerSeconds"] <= iv["upperSeconds"]
        assert isinstance(iv["lowerSeconds"], int) and isinstance(iv["upperSeconds"], int)
        assert t["revisionIntervalStatus"]["provisional"] is True


def test_unknown_category_requires_fallback(warehouse, bundle):
    # 09:05 is an hour the synthetic models never saw, and A50-1 a stop they never saw.
    c = TestClient(
        create_app(api_config(warehouse, bundle.bundle_dir, as_of=local(DAYS[3], 9, 5, 30)))
    )
    fallback = [
        t for t in predictions(c, "A50")["trains"] if t["predictionStatus"] == "fallback_required"
    ]
    assert fallback
    for t in fallback:
        assert t["statusReason"] == "input outside demonstrated model support"
        assert {u["feature"] for u in t["unknownCategories"]} >= {"hour_local"}
        assert t["predictedRevisionSeconds"] is None and t["revisionInterval"] is None
        assert t["revisionProbability"] is None and t["fallbackEtaAt"] == t["currentEtaAt"]


def test_missing_feature_marks_the_train_without_predicting(client, bundle):
    from bart_reliability.serving import Predictor

    predictor = Predictor.load(bundle.bundle_dir)
    engine = client.app.state.api.engine
    row = next(r for r in engine.board("A30", "to-A40")[0] if r["trip_id"] == "T3")
    t = train_prediction({**row, "stops_away": None}, predictor, client.app.state.api.config)
    assert t.prediction_status == "features_unavailable"
    assert "stops_away" in t.status_reason and t.predicted_revision_seconds is None


# -- point-in-time isolation ---------------------------------------------------------


def test_engine_holds_only_allowlisted_data_cut_at_as_of(client):
    engine = client.app.state.api.engine
    # Exactly the allowlist was copied; the only other tables are derived from the schedule.
    assert engine.tables == sorted(allowed_sources(AS_OF, 21600, AS_OF.date()))
    now = sorted(r[0] for r in engine.con.execute("SHOW TABLES").fetchall())
    derived = [
        "boarding_group_exits",
        "static_stop_positions",
        "static_trip_station_visits",
        "static_visits",
    ]
    assert now == sorted([*engine.tables, *derived])
    assert (
        engine.con.execute(
            "SELECT count(*) FROM duckdb_databases() WHERE database_name = 'wh'"
        ).fetchone()[0]
        == 0
    )  # detached
    for forbidden in (
        "observed_arrival_proxy",
        "eta_revision_examples",
        "eta_model_examples",
        "alert_visibility",
        "eta_revision_alert_context",
        "rt_trip_updates",
    ):
        with pytest.raises(duckdb.CatalogException):
            engine.con.execute(f"SELECT * FROM {forbidden} LIMIT 1")
    for table, column in [
        ("asof_predictions", "collected_at"),
        ("asof_feed_snapshots", "collected_at"),
        ("asof_alert_snapshots", "collected_at"),
        ("asof_alert_observations", "collected_at"),
    ]:
        latest = engine.con.execute(f"SELECT max({column}) FROM {table}").fetchone()[0]
        assert latest is not None and latest <= AS_OF
    columns = {r[0] for r in engine.con.execute("DESCRIBE asof_predictions").fetchall()}
    assert columns.isdisjoint(PROHIBITED_COLUMNS - {"trip_id", "service_date"})


def test_responses_do_not_depend_on_anything_after_as_of(warehouse, bundle, client, tmp_path):
    """Holding a train after as_of changes the warehouse, not the replay at as_of."""
    held_db = build_synthetic_warehouse(tmp_path / "wh", perturb=held, with_stations=True)
    other = TestClient(create_app(api_config(held_db, bundle.bundle_dir)))
    for station in ("A20", "A30", "A40"):
        assert predictions(other, station) == predictions(client, station)
        for t in predictions(client, station)["trains"]:
            path = f"/api/v1/predictions/{t['predictionId']}/history"
            assert other.get(path).json() == client.get(path).json()
    # The held train really is different later on.
    later = api_config(warehouse, bundle.bundle_dir, as_of=local(DAYS[3], 8, 26, 30))
    held_later = api_config(held_db, bundle.bundle_dir, as_of=local(DAYS[3], 8, 26, 30))
    a = predictions(TestClient(create_app(later)), "A40")
    b = predictions(TestClient(create_app(held_later)), "A40")
    assert a["trains"] != b["trains"]


def test_alerts_appear_only_once_published(warehouse, bundle):
    def alerts_at(t):
        c = TestClient(create_app(api_config(warehouse, bundle.bundle_dir, as_of=t)))
        return predictions(c, "A30")["alerts"]

    published = local(ALERT_DAY, *ALERT_FROM)
    assert alerts_at(published - timedelta(seconds=30)) == []
    after = alerts_at(published + timedelta(seconds=30))
    assert [a["alertId"] for a in after] == ["BSA_TEST"]
    assert after[0]["scope"] == "system" and after[0]["category"] == "unclassified"
    assert after[0]["visibleSince"] == published.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_history_ends_at_the_replay_snapshot(client):
    body = predictions(client)
    for t in body["trains"]:
        points = client.get(f"/api/v1/predictions/{t['predictionId']}/history").json()
        times = [p["feedTimestamp"] for p in points]
        assert times == sorted(times) and times[-1] == body["feedTimestamp"]
        assert all(datetime.fromisoformat(x) <= AS_OF for x in times)
        assert points[-1]["publishedEtaAt"] == t["currentEtaAt"]
        assert points[-1]["publishedEtaSeconds"] == t["currentEtaSeconds"]
        for p in points:
            delta = datetime.fromisoformat(p["publishedEtaAt"]) - datetime.fromisoformat(
                p["feedTimestamp"]
            )
            assert p["publishedEtaSeconds"] == int(delta.total_seconds())


def test_replay_features_equal_the_training_features(bundle, warehouse):
    """Training/serving parity: at each example's own snapshot, replay computes the
    same feature values the model was trained and evaluated on."""
    with duckdb.connect(str(bundle.run_dir / "features.duckdb"), read_only=True) as con:
        con.execute("SET TimeZone = 'UTC'")
        examples = con.execute(
            "SELECT f.*, e.trip_id FROM eta_model_features f "
            "JOIN eta_model_examples e USING (event_id, published_horizon_bucket_s) "
            "WHERE e.service_date = ? ORDER BY 1, 2",
            [DAYS[3]],
        ).df()
    assert len(examples) == 54
    checked = 0
    for _, ex in examples.iloc[::5].iterrows():
        engine = ReplayEngine(warehouse, ex.prediction_collected_at.to_pydatetime(), 21600)
        rows, *_ = engine.board(ex.stop_id[:3], group_of(ex.stop_id[:3]))
        row = next(r for r in rows if r["trip_id"] == ex.trip_id)
        for name in FEATURE_COLUMNS:
            assert row[name] == ex[name], (ex.event_id, name)
        assert row["population_reason"] is None
        checked += 1
    assert checked >= 10


def test_concurrent_requests_get_their_own_answers(warehouse, bundle):
    """FastAPI runs these endpoints on a thread pool and a browser sends several requests
    at once, so concurrent queries must not read each other's results."""
    engine = ReplayEngine(warehouse, AS_OF, 21600)
    rows, *_ = engine.board("A30", "to-A40")
    ids = [prediction_id(r["event_service_date"], r["trip_id"], r["stop_sequence"]) for r in rows]
    boards = [("A30", "to-A40"), ("A20", "to-A30"), ("A30", "to-X")]
    calls = [("board", b) for b in boards] + [("history", (i,)) for i in ids]
    expected = {call: getattr(engine, call[0])(*call[1]) for call in calls}
    barrier = threading.Barrier(8)

    def run(worker: int) -> list[bool]:
        barrier.wait()
        out = []
        for k in range(40):
            name, args = calls[(worker + k) % len(calls)]
            out.append(getattr(engine, name)(*args) == expected[(name, args)])
        return out

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = [ok for batch in pool.map(run, range(8)) for ok in batch]
    assert len(ids) >= 2 and all(results)


class _RecordingConnection:
    """Stands in for the engine's connection and keeps every cursor it hands out."""

    def __init__(self, con):
        self.con, self.opened, self.fail_setup = con, [], False

    def cursor(self):
        cur = self.con.cursor()
        self.opened.append(cur)
        return _FailingSetup(cur) if self.fail_setup else cur


class _FailingSetup:
    def __init__(self, cur):
        self.cur = cur

    def execute(self, *_):
        raise duckdb.InvalidInputException("setup failed")

    def close(self):
        self.cur.close()


def _closed(cur) -> bool:
    try:
        cur.execute("SELECT 1")
    except duckdb.ConnectionException:
        return True
    return False


def test_every_query_cursor_is_closed_even_when_the_query_fails(warehouse):
    engine = ReplayEngine(warehouse, AS_OF, 21600)
    rows, *_ = engine.board("A30", "to-A40")
    pid = prediction_id(rows[0]["event_service_date"], rows[0]["trip_id"], rows[0]["stop_sequence"])
    calls = (
        lambda: engine.board("A30", "to-A40"),
        lambda: engine.history(pid),
        lambda: engine.alerts("A30", [], [], 120),
        engine._load_stations,
    )
    recorder = _RecordingConnection(engine.con)
    engine.con = recorder
    for call in calls:
        call()
    # Every query below now fails inside its `with` block.
    for table in ("asof_predictions", "asof_alert_snapshots", "static_stops"):
        recorder.con.execute(f"ALTER TABLE {table} RENAME TO {table}_gone")
    for call in calls:
        with pytest.raises(duckdb.CatalogException):
            call()
    # And a cursor whose session setup fails is closed before the error propagates.
    recorder.fail_setup = True
    with pytest.raises(duckdb.InvalidInputException):
        engine.history(pid)
    assert len(recorder.opened) == 2 * len(calls) + 1
    assert all(_closed(cur) for cur in recorder.opened)


def test_replay_is_deterministic(warehouse, bundle, client):
    again = TestClient(create_app(api_config(warehouse, bundle.bundle_dir)))
    for path in (
        "/api/v1/stations",
        BOARD_A30,
        "/api/v1/health",
    ):
        assert again.get(path).json() == client.get(path).json()


# -- errors --------------------------------------------------------------------------


def _error(r, status, code):
    assert r.status_code == status, r.json()
    body = r.json()["error"]
    assert body["code"] == code and body["clientCode"] in {"not_found", "unavailable"}
    assert body["message"]
    return body


def test_unknown_station_boarding_group_and_missing_parameter(client):
    base = "/api/v1/stations"
    _error(client.get(f"{base}/NOPE/predictions?boarding_group=to-A40"), 404, "station_not_found")
    # A group of another station, and a direction-style value, are not this station's groups.
    for group in ("to-A30", "to-A20", "0"):
        r = client.get(f"{base}/A30/predictions", params={"boarding_group": group})
        _error(r, 404, "boarding_group_not_found")
    _error(client.get(f"{base}/A30/predictions"), 422, "invalid_request")
    # The old parameter is no longer read, so the required one is missing.
    _error(client.get(f"{base}/A30/predictions?direction_id=0"), 422, "invalid_request")
    _error(
        client.get(f"{base}/A30/predictions", params={"boarding_group": "to A40"}),
        422,
        "invalid_request",
    )


def test_unavailable_history(client):
    _error(
        client.get(f"/api/v1/predictions/{DAYS[3]}:T9:4/history"),
        404,
        "prediction_history_unavailable",
    )
    _error(
        client.get("/api/v1/predictions/not-an-id/history"), 404, "prediction_history_unavailable"
    )


def test_missing_model_bundle(warehouse, tmp_path):
    c = TestClient(create_app(api_config(warehouse, tmp_path / "no-bundle")))
    _error(c.get(BOARD_A30), 503, "model_bundle_unavailable")
    _error(c.get("/api/v1/model/metadata"), 503, "model_bundle_unavailable")
    assert c.get("/api/v1/stations").status_code == 200  # the schedule needs no model
    health = c.get("/api/v1/health").json()
    assert health["status"] == "degraded" and health["modelVersion"] is None
    assert any(p.startswith("model bundle:") for p in health["problems"])


def test_missing_warehouse(bundle, tmp_path):
    c = TestClient(create_app(api_config(tmp_path / "missing.duckdb", bundle.bundle_dir)))
    _error(c.get("/api/v1/stations"), 503, "warehouse_unavailable")
    _error(c.get(BOARD_A30), 503, "warehouse_unavailable")
    _error(c.get(f"/api/v1/predictions/{DAYS[3]}:T3:4/history"), 503, "warehouse_unavailable")
    health = c.get("/api/v1/health").json()
    assert health["status"] == "degraded" and health["latestFeedTimestamp"] is None


def test_stale_and_missing_feed(warehouse, bundle):
    stale = TestClient(
        create_app(api_config(warehouse, bundle.bundle_dir, as_of=local(DAYS[3], 12, 0)))
    )
    body = _error(stale.get(BOARD_A30), 503, "feed_stale")
    assert "does not cover as_of" in body["message"]
    assert stale.get("/api/v1/health").json()["status"] == "degraded"
    before = TestClient(
        create_app(api_config(warehouse, bundle.bundle_dir, as_of=local(DAYS[0], 6, 0)))
    )
    _error(before.get(BOARD_A30), 503, "feed_unavailable")


def test_feature_schema_mismatch(warehouse, bundle, monkeypatch):
    monkeypatch.setattr(api_app, "FEATURE_SCHEMA_VERSION", "eta-revision-features-2")
    c = TestClient(create_app(api_config(warehouse, bundle.bundle_dir)))
    body = _error(c.get(BOARD_A30), 503, "feature_schema_mismatch")
    assert "eta-revision-features-1" in body["message"]
    assert any(p.startswith("feature schema:") for p in c.get("/api/v1/health").json()["problems"])


# -- local only ----------------------------------------------------------------------


ALLOWED_ORIGINS = [
    "http://localhost:5173",  # Vite dev server
    "http://localhost:4173",  # Vite preview
    "http://localhost",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:4173",
    "http://[::1]:5173",
]
REFUSED_ORIGINS = [
    "https://example.com",
    "http://localhost.evil.test",
    "https://localhost:5173",  # the dev servers are plain http
    "http://192.168.1.5:5173",
    "http://127.0.0.2:5173",
    "null",
]


def _exposed(response) -> set[str]:
    raw = response.headers.get("access-control-expose-headers", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _browser_paths(client):
    pid = predictions(client)["trains"][0]["predictionId"]
    return [
        "/api/v1/health",
        "/api/v1/stations",
        "/api/v1/model/metadata",
        BOARD_A30,
        f"/api/v1/predictions/{pid}/history",
        "/api/v1/stations/NOPE/predictions?boarding_group=to-A40",  # an error body too
    ]


@pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
def test_browser_request_from_an_allowed_origin_can_read_replay_headers(client, origin):
    for path in _browser_paths(client):
        r = client.get(path, headers={"Origin": origin})
        assert r.headers["access-control-allow-origin"] == origin, path
        assert r.headers["x-data-mode"] == "historical-replay"
        assert r.headers["x-replay-as-of"] == "2026-10-09T15:16:30Z"
        assert {"x-data-mode", "x-replay-as-of"} <= _exposed(r), path
        assert "access-control-allow-credentials" not in r.headers
        assert "origin" in r.headers["vary"].lower()


@pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
def test_preflight_from_an_allowed_origin_permits_get_only(client, origin):
    headers = {"Origin": origin, "Access-Control-Request-Method": "GET"}
    r = client.options("/api/v1/stations", headers=headers)
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == origin
    assert r.headers["access-control-allow-methods"] == "GET"
    post = client.options(
        "/api/v1/stations", headers={**headers, "Access-Control-Request-Method": "POST"}
    )
    assert post.status_code == 400


@pytest.mark.parametrize("origin", REFUSED_ORIGINS)
def test_unapproved_origin_gets_no_cors_permission(client, origin):
    for path in _browser_paths(client):
        r = client.get(path, headers={"Origin": origin})
        assert not any(k.startswith("access-control-") for k in r.headers), (path, r.headers)
    pre = client.options(
        "/api/v1/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"}
    )
    assert pre.status_code == 400
    assert "access-control-allow-origin" not in pre.headers


def test_non_browser_requests_still_work(client):
    for path in _browser_paths(client)[:-1]:
        r = client.get(path)  # no Origin header, like curl or a server-side client
        assert r.status_code == 200, path
        assert r.headers["x-data-mode"] == "historical-replay"
        assert not any(k.startswith("access-control-") for k in r.headers)


def test_repository_config_replays_october_20_with_model_0_2():
    cfg = load_api_config()
    assert cfg.as_of == datetime.fromisoformat("2026-10-20T17:00:00+00:00")
    assert str(cfg.warehouse) == "data/warehouse/bart_checkpoint_2026-10-20.duckdb"
    assert str(cfg.bundle) == "data/models/eta_revision_bundle_2026-10-20"
    assert cfg.bundle_id == "db2382848a9ff29a298aa6d320623daf532ac4d813475bf30a8e052e84ed6087"


def test_pinned_bundle_id_accepts_only_that_build(warehouse, bundle):
    pinned = api_config(warehouse, bundle.bundle_dir, bundle_id=bundle.metadata["bundle_id"])
    health = TestClient(create_app(pinned)).get("/api/v1/health").json()
    assert health["status"] == "ok" and health["bundleId"] == bundle.metadata["bundle_id"]
    other = api_config(warehouse, bundle.bundle_dir, bundle_id="0" * 64)
    health = TestClient(create_app(other)).get("/api/v1/health").json()
    assert health["status"] == "degraded" and health["modelVersion"] is None
    assert any("not the pinned build" in p for p in health["problems"])


def test_bundle_id_must_be_a_full_sha256(warehouse, bundle):
    with pytest.raises(ApiConfigError, match="64-character"):
        api_config(warehouse, bundle.bundle_dir, bundle_id="db2382848a9f")


def test_replay_inside_the_models_data_is_reported(warehouse, bundle):
    """Before the calibration cutoff the models or their interval used the replayed
    period, so predictions there would be in-sample."""
    cutoff = bundle.metadata["training_data"]["calibration_data_cutoff_utc"]
    inside = api_config(warehouse, bundle.bundle_dir, as_of=local(DAYS[2], 8, 16, 30))
    assert inside.as_of < datetime.fromisoformat(cutoff)
    problems = TestClient(create_app(inside)).get("/api/v1/health").json()["problems"]
    assert len(problems) == 1 and problems[0].startswith("model: as_of")
    assert cutoff in problems[0]
    after = TestClient(create_app(api_config(warehouse, bundle.bundle_dir)))
    assert after.get("/api/v1/health").json()["problems"] == []


def test_only_loopback_hosts_are_accepted(warehouse, bundle):
    cfg = api_config(warehouse, bundle.bundle_dir)
    assert cfg.host == "127.0.0.1"  # the default
    for host in ("0.0.0.0", "192.168.1.5", "::", "example.com"):
        with pytest.raises(ApiConfigError, match="loopback"):
            replace(cfg, host=host)
    assert serve_main(["--host", "0.0.0.0"]) == 2  # refused before anything starts


def test_records_never_carry_labels_or_future_fields(client):
    body = json.dumps(predictions(client))
    for label in (
        "finalStableEstimate",
        "final_stable_estimate",
        "etaRevisionSeconds",
        "lastSeenAt",
        "confirmedAbsentAt",
        "timeToProxy",
        "qualityTier",
    ):
        assert label not in body
    state: ApiState = client.app.state.api
    assert set(state.predictor.features) == set(FEATURE_COLUMNS) | {"published_horizon_bucket_s"}
