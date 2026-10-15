"""Local prediction API in historical-replay mode (docs/local_api.md).

Everything the API returns is computed as of a configured past moment from the ignored
local warehouse and the exported model bundle. Nothing contacts BART. Every response
says it is historical replay: object bodies carry `dataMode: "historical_replay"`, and
every response, arrays and errors included, carries the `X-Data-Mode` and
`X-Replay-As-Of` headers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from bart_reliability.api.config import LocalApiConfig
from bart_reliability.api.replay import (
    FEATURE_COLUMNS,
    FEATURE_SCHEMA_VERSION,
    ReplayEngine,
    WarehouseUnavailable,
    destination,
    prediction_id,
)
from bart_reliability.api.schemas import (
    DATA_MODE,
    AlertContext,
    AlertState,
    ErrorDetail,
    ErrorResponse,
    HealthStatus,
    ModelMetadata,
    PredictionHistoryPoint,
    PredictionResponse,
    ReplayInfo,
    RevisionInterval,
    RevisionIntervalStatus,
    Station,
    TrainPrediction,
    UnknownCategory,
)
from bart_reliability.serving.predictor import BundleError, Predictor, RecordError, load_predictor

# Browsers on this machine only: http://localhost:<port>, 127.0.0.1 or [::1].
LOCAL_ORIGIN_REGEX = r"^http://(localhost|127\.0\.0\.1|\[::1\])(:\d{1,5})?$"
DATA_MODE_HEADER = "X-Data-Mode"
AS_OF_HEADER = "X-Replay-As-Of"
ALERT_SNAPSHOT_MAX_AGE_S = 120


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ApiError(Exception):
    def __init__(self, status: int, code: str, client_code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.client_code, self.message = status, code, client_code, message


@dataclass
class ApiState:
    config: LocalApiConfig
    engine: ReplayEngine | None
    engine_error: str | None
    predictor: Predictor | None
    predictor_error: str | None
    schema_error: str | None

    @classmethod
    def load(cls, config: LocalApiConfig, expected_bundle_id: str | None = None) -> ApiState:
        engine = predictor = None
        engine_error = predictor_error = schema_error = None
        try:
            engine = ReplayEngine(config.warehouse, config.as_of, config.history_lookback_seconds)
        except WarehouseUnavailable as e:
            engine_error = str(e)
        try:
            predictor = load_predictor(config.bundle, expected_bundle_id)
        except (BundleError, FileNotFoundError, OSError) as e:
            predictor_error = str(e)
        if predictor is not None:
            served = set(predictor.features)
            computed = set(FEATURE_COLUMNS) | {"published_horizon_bucket_s"}
            if predictor.metadata["feature_schema_version"] != FEATURE_SCHEMA_VERSION:
                schema_error = (
                    f"bundle requires feature schema "
                    f"{predictor.metadata['feature_schema_version']!r}; this API computes "
                    f"{FEATURE_SCHEMA_VERSION!r}"
                )
            elif served != computed:
                schema_error = (
                    f"bundle features {sorted(served ^ computed)} differ from the features "
                    "this API computes"
                )
        return cls(config, engine, engine_error, predictor, predictor_error, schema_error)

    def problems(self) -> list[str]:
        out = []
        if self.engine_error:
            out.append(f"warehouse: {self.engine_error}")
        elif self.engine is not None:
            out += [
                f"warehouse: {p}" for p in self.engine.problems(self.config.stale_after_seconds)
            ]
        if self.predictor_error:
            out.append(f"model bundle: {self.predictor_error}")
        if self.schema_error:
            out.append(f"feature schema: {self.schema_error}")
        return out

    def require_engine(self) -> ReplayEngine:
        if self.engine is None:
            raise ApiError(
                503,
                "warehouse_unavailable",
                "unavailable",
                f"The replay warehouse is unavailable: {self.engine_error}",
            )
        return self.engine

    def require_fresh_snapshot(self) -> ReplayEngine:
        engine = self.require_engine()
        if engine.snapshot is None:
            raise ApiError(
                503,
                "feed_unavailable",
                "unavailable",
                "The warehouse has no trip-update snapshot at or before as_of.",
            )
        age = engine.freshness_seconds()
        if age > self.config.stale_after_seconds:
            raise ApiError(
                503,
                "feed_stale",
                "unavailable",
                f"The latest snapshot at or before as_of is {age} s old (limit "
                f"{self.config.stale_after_seconds} s); the warehouse does not cover as_of.",
            )
        return engine

    def require_predictor(self) -> Predictor:
        if self.predictor is None:
            raise ApiError(
                503,
                "model_bundle_unavailable",
                "unavailable",
                f"The model bundle is unavailable: {self.predictor_error}",
            )
        if self.schema_error:
            raise ApiError(503, "feature_schema_mismatch", "unavailable", self.schema_error)
        return self.predictor


def model_metadata(predictor: Predictor) -> ModelMetadata:
    meta = predictor.metadata
    return ModelMetadata(
        model_version=meta["model"]["version"],
        trained_through=meta["training_data"]["training_data_cutoff_utc"],
        revision_threshold_seconds=meta["model_configuration"]["modeling"][
            "large_revision_threshold_s"
        ],
        simulated=False,
        feature_schema_version=meta["feature_schema_version"],
        bundle_id=meta["bundle_id"],
        provisional=True,
        interval_available=meta["interval"]["available"],
        served_horizons_seconds=meta["domain"]["published_horizon_buckets_s"],
        horizon_tolerance_seconds=meta["domain"]["horizon_tolerance_s"],
    )


def stability(probability: float, config: LocalApiConfig) -> str:
    """Same cutoffs as classifyStability in web/src/domain/eta.ts."""
    if probability >= config.stability_likely_to_be_revised:
        return "likely_to_be_revised"
    if probability >= config.stability_may_be_revised:
        return "may_be_revised"
    return "likely_to_hold"


def served_bucket(horizon: int, predictor: Predictor) -> int | None:
    domain = predictor.metadata["domain"]
    for bucket in domain["published_horizon_buckets_s"]:
        if abs(horizon - bucket) <= domain["horizon_tolerance_s"]:
            return bucket
    return None


def train_prediction(row: dict, predictor: Predictor, config: LocalApiConfig) -> TrainPrediction:
    current_at = row["predicted_arrival"]
    base = dict(
        prediction_id=prediction_id(
            row["event_service_date"], row["trip_id"], row["stop_sequence"]
        ),
        trip_id=row["trip_id"],
        line_name=f"{(row['route_short_name'] or 'Unknown').split('-')[0]} line",
        headsign=destination(row["trip_headsign"]),
        car_count=None,  # BART's GTFS-RT feed carries no consist length
        current_eta_seconds=row["current_eta_seconds"],
        current_eta_at=iso(current_at),
        predicted_revision_seconds=None,
        revision_interval=None,
        revision_probability=None,
        stability=None,
        fallback_eta_at=iso(current_at),
        likely_final_eta_seconds=None,
        likely_final_eta_at=None,
        published_time_horizon_seconds=None,
        revision_interval_status=None,
        unknown_categories=[],
        route_id=row["route_id"],
        route_short_name=row["route_short_name"],
        direction_id=row["direction_id"],
        station_id=row["station_id"],
        station_name=row["stop_name"],
        stop_id=row["stop_id"],
        scheduled_headsign=row["trip_headsign"],
    )

    def unsupported(status: str, reason: str, **extra) -> TrainPrediction:
        return TrainPrediction(**(base | extra), prediction_status=status, status_reason=reason)

    if row["population_reason"]:
        return unsupported("outside_model_population", row["population_reason"])
    bucket = served_bucket(row["published_horizon_s"], predictor)
    if bucket is None:
        return unsupported(
            "outside_model_horizon",
            f"BART's ETA was {row['published_horizon_s']} s away; the models serve only "
            "published-time horizons of 5, 10 and 15 minutes (within 60 s)",
        )
    missing = sorted(n for n in FEATURE_COLUMNS if row[n] is None)
    if missing:
        return unsupported("features_unavailable", f"missing features: {missing}")
    record = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "snapshot_collected_at": iso(row["collected_at"]),
        "published_eta": iso(current_at),
        "published_horizon_bucket_s": bucket,
        **{n: row[n] for n in FEATURE_COLUMNS},
    }
    try:
        out = predictor.predict(record)
    except RecordError as e:
        return unsupported("features_unavailable", f"record rejected by the bundle: {e}")
    if out["status"] != "ok":
        return unsupported(
            "fallback_required",
            out["reason"],
            published_time_horizon_seconds=bucket,
            unknown_categories=[UnknownCategory(**u) for u in out["unknown_categories"]],
        )
    revision = math.floor(out["predicted_eta_revision_seconds"] + 0.5)
    interval = out["revision_intervals"][0]
    status = RevisionIntervalStatus(
        available=interval["available"],
        provisional=interval["status"] == "provisional",
        method=interval["method"],
        nominal_level=interval["nominal_coverage"],
        unavailable_reasons=interval["unavailable_reasons"],
        empirical_test_coverage=interval["empirical_test_coverage"]["this_horizon"],
        calibration_split=interval["calibration"]["split"],
        independently_calibrated=interval["independently_calibrated"],
    )
    probability = out["probability_absolute_revision_over_60_seconds"]
    return TrainPrediction(
        **(
            base
            | dict(
                predicted_revision_seconds=revision,
                revision_probability=probability,
                stability=stability(probability, config),
                # Rounded outward so the stated coverage is not overstated.
                revision_interval=RevisionInterval(
                    lower_seconds=math.floor(interval["lower_revision_seconds"]),
                    upper_seconds=math.ceil(interval["upper_revision_seconds"]),
                    level=interval["nominal_coverage"],
                )
                if interval["available"]
                else None,
                revision_interval_status=status,
                fallback_eta_at=None,
                likely_final_eta_seconds=row["current_eta_seconds"] + revision,
                likely_final_eta_at=iso(current_at + timedelta(seconds=revision)),
                published_time_horizon_seconds=bucket,
            )
        ),
        prediction_status="ok",
        status_reason=None,
    )


def create_app(config: LocalApiConfig, state: ApiState | None = None) -> FastAPI:
    state = state or ApiState.load(config)
    as_of = iso(config.as_of)
    app = FastAPI(
        title="BART ETA revision API (local historical replay)",
        description="Local only. Historical replay of BART feeds; never live data.",
        version="0.1.0",
    )
    app.state.api = state
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=LOCAL_ORIGIN_REGEX,
        allow_methods=["GET"],
        allow_headers=[],
        allow_credentials=False,
        expose_headers=[DATA_MODE_HEADER, AS_OF_HEADER],
    )

    @app.middleware("http")
    async def replay_headers(request: Request, call_next):
        # Runs outside the CORS middleware, so it also labels CORS and error responses.
        response = await call_next(request)
        response.headers[DATA_MODE_HEADER] = "historical-replay"
        response.headers[AS_OF_HEADER] = as_of
        if "access-control-allow-origin" not in response.headers:
            # Starlette adds the expose list for any Origin; without an allowed origin it
            # grants nothing, so drop it rather than send a misleading CORS header.
            if "access-control-expose-headers" in response.headers:
                del response.headers["access-control-expose-headers"]
        return response

    def error(status: int, code: str, client_code: str, message: str) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorDetail(code=code, client_code=client_code, message=message, as_of=as_of)
        )
        return JSONResponse(status_code=status, content=body.model_dump(by_alias=True))

    @app.exception_handler(ApiError)
    async def api_error(_: Request, e: ApiError):
        return error(e.status, e.code, e.client_code, e.message)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, e: RequestValidationError):
        fields = sorted({".".join(str(p) for p in err["loc"][1:]) for err in e.errors()})
        return error(
            422, "invalid_request", "unavailable", f"invalid or missing parameters: {fields}"
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, e: StarletteHTTPException):
        code = "not_found" if e.status_code == 404 else "method_not_allowed"
        return error(
            e.status_code,
            code,
            "not_found" if e.status_code == 404 else "unavailable",
            str(e.detail),
        )

    @app.get("/api/v1/health", response_model=HealthStatus)
    def health() -> HealthStatus:
        problems = state.problems()
        engine, predictor = state.engine, state.predictor
        snapshot = engine.snapshot if engine else None
        return HealthStatus(
            status="degraded" if problems else "ok",
            latest_feed_timestamp=iso(snapshot.feed_timestamp) if snapshot else None,
            as_of=as_of,
            freshness_seconds=engine.freshness_seconds() if engine else None,
            problems=problems,
            model_version=predictor.metadata["model"]["version"] if predictor else None,
            feature_schema_version=(
                predictor.metadata["feature_schema_version"] if predictor else None
            ),
            bundle_id=predictor.metadata["bundle_id"] if predictor else None,
        )

    @app.get("/api/v1/model/metadata", response_model=ModelMetadata)
    def metadata() -> ModelMetadata:
        return model_metadata(state.require_predictor())

    @app.get("/api/v1/stations", response_model=list[Station])
    def stations() -> list[Station]:
        return [Station(**s) for s in state.require_engine().stations()]

    @app.get("/api/v1/stations/{station_id}/predictions", response_model=PredictionResponse)
    def predictions(
        station_id: str, direction_id: str = Query(..., pattern=r"^[01]$")
    ) -> PredictionResponse:
        engine = state.require_engine()
        station = next((s for s in engine.stations() if s["id"] == station_id), None)
        if station is None:
            raise ApiError(
                404,
                "station_not_found",
                "not_found",
                f"No station {station_id!r} has service on the replay date.",
            )
        if direction_id not in {d["id"] for d in station["directions"]}:
            raise ApiError(
                404,
                "direction_not_found",
                "not_found",
                f"Station {station_id!r} has no direction {direction_id!r}.",
            )
        engine = state.require_fresh_snapshot()
        predictor = state.require_predictor()
        rows, unplaced = engine.board(station_id, direction_id)
        trains = [train_prediction(r, predictor, config) for r in rows]
        alerts = engine.alerts(
            station_id,
            sorted({r["route_id"] for r in rows if r["route_id"]}),
            sorted({r["trip_id"] for r in rows}),
            ALERT_SNAPSHOT_MAX_AGE_S,
        )
        snap = engine.snapshot
        return PredictionResponse(
            station_id=station_id,
            direction_id=direction_id,
            feed_timestamp=iso(snap.feed_timestamp),
            generated_at=as_of,  # the replay clock: the model runs "as of" this time
            trains=trains,
            alerts=[
                AlertContext(**(a | {"visible_since": iso(a["visible_since"])}))
                for a in alerts["alerts"]
            ],
            model=model_metadata(predictor),
            replay=ReplayInfo(
                as_of=as_of,
                source_timestamp=iso(snap.feed_timestamp),
                collected_at=iso(snap.collected_at),
                freshness_seconds=engine.freshness_seconds(),
                stale=False,
                stale_after_seconds=config.stale_after_seconds,
            ),
            alert_state=AlertState(
                known=alerts["known"],
                snapshot_timestamp=iso(alerts["snapshot"]) if alerts["snapshot"] else None,
                age_seconds=alerts["age_seconds"],
            ),
            unplaced_train_count=unplaced,
        )

    @app.get(
        "/api/v1/predictions/{prediction_id}/history", response_model=list[PredictionHistoryPoint]
    )
    def history(prediction_id: str) -> list[PredictionHistoryPoint]:
        engine = state.require_fresh_snapshot()
        points = engine.history(prediction_id)
        if not points:
            raise ApiError(
                404,
                "prediction_history_unavailable",
                "not_found",
                f"No published ETAs for {prediction_id!r} at or before as_of.",
            )
        return [
            PredictionHistoryPoint(
                feed_timestamp=iso(p["feed_timestamp"]),
                published_eta_at=iso(p["published_eta_at"]),
                published_eta_seconds=p["published_eta_seconds"],
            )
            for p in points
        ]

    return app


__all__ = ["DATA_MODE", "ApiState", "create_app"]
