"""Response models matching the website's TypeScript contracts (web/src/domain/types.ts).

Every field of the TypeScript types is present, in camelCase. Fields the contract does
not have are additions; a client written against the contract can ignore them. The only
departures are nullable model fields, needed to stay honest (see docs/local_api.md,
"Contract differences"): a train the models cannot support gets no model numbers, and an
unavailable interval is null rather than invented.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

DATA_MODE = "historical_replay"

StabilityClass = Literal["likely_to_hold", "may_be_revised", "likely_to_be_revised"]
PredictionStatus = Literal[
    "ok",
    "fallback_required",
    "outside_model_horizon",
    "outside_model_population",
    "features_unavailable",
]


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Direction(ApiModel):
    id: str
    label: str
    destinations: list[str]


class Station(ApiModel):
    id: str
    name: str
    directions: list[Direction]


class RevisionInterval(ApiModel):
    lower_seconds: int
    upper_seconds: int
    level: float


class RevisionIntervalStatus(ApiModel):
    """Why an interval is or is not present (addition)."""

    available: bool
    provisional: bool
    method: str | None
    nominal_level: float | None
    unavailable_reasons: list[str]
    empirical_test_coverage: float | None
    calibration_split: str | None
    independently_calibrated: bool


class UnknownCategory(ApiModel):
    feature: str
    value: str | int


class TrainPrediction(ApiModel):
    # Contract fields
    prediction_id: str
    trip_id: str
    line_name: str
    headsign: str
    car_count: int | None
    current_eta_seconds: int
    current_eta_at: str
    predicted_revision_seconds: int | None
    revision_interval: RevisionInterval | None
    revision_probability: float | None
    stability: StabilityClass | None
    # Additions
    prediction_status: PredictionStatus
    status_reason: str | None
    fallback_eta_at: str | None
    likely_final_eta_seconds: int | None
    likely_final_eta_at: str | None
    published_time_horizon_seconds: int | None
    revision_interval_status: RevisionIntervalStatus | None
    unknown_categories: list[UnknownCategory]
    route_id: str | None
    route_short_name: str | None
    direction_id: str
    station_id: str
    station_name: str | None
    stop_id: str
    scheduled_headsign: str | None


class AlertContext(ApiModel):
    alert_id: str
    scope: Literal["system", "route", "station"]
    category: Literal["planned_work", "incident", "unclassified"]
    header_text: str
    visible_since: str
    # Addition: BART's headers are often generic ("BART.gov Alert").
    description_text: str | None


class ModelMetadata(ApiModel):
    # Contract fields
    model_version: str
    trained_through: str
    revision_threshold_seconds: int
    simulated: bool
    # Additions
    feature_schema_version: str
    bundle_id: str
    provisional: bool
    interval_available: bool
    served_horizons_seconds: list[int]
    horizon_tolerance_seconds: int
    data_mode: str = DATA_MODE


class ReplayInfo(ApiModel):
    data_mode: str = DATA_MODE
    as_of: str
    source_timestamp: str
    collected_at: str
    freshness_seconds: int
    stale: bool
    stale_after_seconds: int


class AlertState(ApiModel):
    known: bool
    snapshot_timestamp: str | None
    age_seconds: int | None


class PredictionResponse(ApiModel):
    # Contract fields
    station_id: str
    direction_id: str
    feed_timestamp: str
    generated_at: str
    trains: list[TrainPrediction]
    alerts: list[AlertContext]
    model: ModelMetadata
    # Additions
    data_mode: str = DATA_MODE
    replay: ReplayInfo
    alert_state: AlertState
    unplaced_train_count: int


class PredictionHistoryPoint(ApiModel):
    feed_timestamp: str
    published_eta_at: str
    published_eta_seconds: int


class HealthStatus(ApiModel):
    # Contract fields (latestFeedTimestamp is null only when no feed is loaded)
    status: Literal["ok", "degraded"]
    latest_feed_timestamp: str | None
    # Additions
    data_mode: str = DATA_MODE
    as_of: str
    freshness_seconds: int | None
    problems: list[str]
    model_version: str | None
    feature_schema_version: str | None
    bundle_id: str | None


class ErrorDetail(ApiModel):
    code: str
    client_code: Literal["not_found", "unavailable", "not_implemented"]
    message: str
    data_mode: str = DATA_MODE
    as_of: str


class ErrorResponse(ApiModel):
    error: ErrorDetail
