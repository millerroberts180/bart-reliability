"""What a static replay file holds, and which of its times may lie after the replay time.

Each file is the local API's JSON body for one GET request (api/schemas.py), reduced to
the fields the website reads (web/src/data/apiDecode.ts). Kept fields stay in the API's
order with the API's values. The website decodes nothing else, so nothing else is
published: bundle IDs, interval diagnostics, route and stop IDs, alert descriptions and
replay freshness details stay in the local API.
"""

from __future__ import annotations

from datetime import datetime

from bart_reliability.api import schemas

# Fields kept per response model, by their JSON (camelCase) names.
KEEP: dict[str, tuple[str, ...]] = {
    "Station": ("id", "name", "boardingGroups", "endOfLine"),
    "BoardingGroup": ("id", "label", "destinations", "platform", "gtfsDirectionIds"),
    "PredictionResponse": (
        "stationId",
        "boardingGroupId",
        "feedTimestamp",
        "generatedAt",
        "trains",
        "alerts",
        "model",
        "dataMode",
        "replay",
        "unplacedTrainCount",
        "terminatingTrainCount",
    ),
    "TrainPrediction": (
        "predictionId",
        "tripId",
        "lineName",
        "headsign",
        "carCount",
        "currentEtaSeconds",
        "currentEtaAt",
        "predictedRevisionSeconds",
        "revisionInterval",
        "revisionProbability",
        "stability",
        "predictionStatus",
        "statusReason",
        "platform",
    ),
    "RevisionInterval": ("lowerSeconds", "upperSeconds", "level"),
    "AlertContext": ("alertId", "scope", "category", "headerText", "visibleSince"),
    "ModelMetadata": ("modelVersion", "trainedThrough", "revisionThresholdSeconds", "simulated"),
    "ReplayInfo": ("asOf",),
    "PredictionHistoryPoint": ("feedTimestamp", "publishedEtaAt", "publishedEtaSeconds"),
    "HealthStatus": ("status", "latestFeedTimestamp", "dataMode", "asOf"),
}
# Kept fields that hold another response model.
NESTED: dict[tuple[str, str], str] = {
    ("Station", "boardingGroups"): "BoardingGroup",
    ("PredictionResponse", "trains"): "TrainPrediction",
    ("PredictionResponse", "alerts"): "AlertContext",
    ("PredictionResponse", "model"): "ModelMetadata",
    ("PredictionResponse", "replay"): "ReplayInfo",
    ("TrainPrediction", "revisionInterval"): "RevisionInterval",
}

# Times of things observed or decided by the replay time: none may be after it.
OBSERVED_TIMES = frozenset(
    {
        "asOf",
        "generatedAt",
        "feedTimestamp",
        "sourceTimestamp",
        "collectedAt",
        "snapshotTimestamp",
        "latestFeedTimestamp",
        "visibleSince",
        "trainedThrough",
    }
)
# BART's published estimates and the model's forecast of them: clock times that may be
# after the replay time, though each was published or computed by then.
ESTIMATED_TIMES = frozenset({"currentEtaAt", "publishedEtaAt", "fallbackEtaAt", "likelyFinalEtaAt"})
_TIME_SUFFIXES = ("At", "Timestamp", "Since", "Through")


def api_fields(model: str) -> tuple[str, ...]:
    """Every JSON field the local API returns for a response model, in its order."""
    fields = getattr(schemas, model).model_fields
    return tuple(info.alias or name for name, info in fields.items())


def omitted_fields(model: str) -> tuple[str, ...]:
    return tuple(f for f in api_fields(model) if f not in KEEP[model])


def project(model: str, value, path: str, problems: list[str]):
    """The kept fields of an API value (an object or a list of them), in the API's order.
    A missing kept field or a field the API model does not define is a problem."""
    if isinstance(value, list):
        return [project(model, v, f"{path}[{i}]", problems) for i, v in enumerate(value)]
    if value is None:
        return None
    if not isinstance(value, dict):
        problems.append(f"{path}: expected a {model} object")
        return value
    known, keep = set(api_fields(model)), KEEP[model]
    problems += [f"{path}.{k}: not a field of {model}" for k in value if k not in known]
    problems += [f"{path}.{k}: missing" for k in keep if k not in value]
    out = {}
    for key, item in value.items():
        if key in keep:
            nested = NESTED.get((model, key))
            out[key] = project(nested, item, f"{path}.{key}", problems) if nested else item
    return out


def future_times(value, as_of: datetime, path: str = "$") -> list[str]:
    """Observed times after as_of anywhere in a JSON value, and any time field that is
    neither an observed time nor a published estimate, so a new one cannot slip by."""
    problems = []
    if isinstance(value, list):
        for i, item in enumerate(value):
            problems += future_times(item, as_of, f"{path}[{i}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            where = f"{path}.{key}"
            if key in OBSERVED_TIMES:
                ts = _timestamp(item)
                if item is not None and ts is None:
                    problems.append(f"{where}: not a timestamp with a time zone")
                elif ts is not None and ts > as_of:
                    problems.append(f"{where}: {item} is after the replay time")
            elif key in ESTIMATED_TIMES:
                pass
            elif key.endswith(_TIME_SUFFIXES):
                problems.append(f"{where}: unclassified time field")
            else:
                problems += future_times(item, as_of, where)
    return problems


def _timestamp(value) -> datetime | None:
    try:
        ts = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None
    return ts if ts is not None and ts.tzinfo is not None else None
