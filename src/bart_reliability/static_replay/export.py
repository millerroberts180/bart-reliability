"""Export the local historical replay as static JSON files (docs/static_replay.md).

The exporter asks the local API, in process and through its whole request stack, every
question the website can ask at the replay time: health, model metadata, the station
list, every station's boarding-group boards, and the history of every train on those
boards. Each answer is reduced to the fields the website reads (contract.py) and written
as one compact JSON file, so the page fetches a file only when it needs that answer.

Nothing is written unless the inputs match the pins in config/static_replay.toml, the
replay is healthy, every request succeeds and no observed time is after the replay
time. The files are written to a temporary directory, compared with the answers of a
second, independently loaded API, and only then moved into place.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import re
import shutil
import statistics
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlencode

from bart_reliability.api.config import LocalApiConfig
from bart_reliability.api.replay import parse_prediction_id
from bart_reliability.serving.schema import sha256_file
from bart_reliability.static_replay.contract import future_times, omitted_fields, project

SCHEMA_VERSION = "static-replay-1"
LAYOUT_VERSION = "v1"
DEFAULT_SPEC_PATH = Path("config/static_replay.toml")
MANIFEST = "manifest.json"
NOTICE = (
    "A fixed historical replay of recorded BART data, answered as of replay.asOf. "
    "It is not live data and never changes."
)
_ID = re.compile(r"[A-Za-z0-9-]{1,80}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
# Every path an export can contain, so a manifest cannot point outside its directory.
_FILE = re.compile(
    r"(health|model|stations)\.json"
    r"|boards/[A-Za-z0-9-]{1,80}/[A-Za-z0-9-]{1,80}\.json"
    r"|history/\d{4}-\d{2}-\d{2}_[A-Za-z0-9-]{1,80}_\d{1,6}\.json"
)
_GZIP_LEVEL = 6  # a typical web server setting; sizes are estimates of transfer size
# Response models with fields the website does not read (contract.KEEP).
OMITTING_MODELS = (
    "HealthStatus",
    "PredictionResponse",
    "TrainPrediction",
    "AlertContext",
    "ModelMetadata",
    "ReplayInfo",
)


class ExportError(RuntimeError):
    """An input differs from its pin, an answer is unusable, or an export is damaged."""


@dataclass(frozen=True)
class ExportSpec:
    """What the export must be made from (config/static_replay.toml)."""

    as_of: datetime
    source_feed_timestamp: datetime
    model_version: str
    bundle_id: str
    warehouse_sha256: str
    output_dir: Path

    @property
    def name(self) -> str:
        return f"{LAYOUT_VERSION}-{self.as_of.astimezone(UTC):%Y%m%dT%H%M%SZ}"


def load_export_spec(path: Path = DEFAULT_SPEC_PATH) -> ExportSpec:
    """Read a TOML file. Every key is required, so defaults never apply silently."""
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError as e:
        raise ExportError(f"static replay spec not found: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ExportError(f"static replay spec is not valid TOML: {e}") from e
    keys = {
        "as_of",
        "source_feed_timestamp",
        "model_version",
        "bundle_id",
        "warehouse_sha256",
        "output_dir",
    }
    missing, unknown = sorted(keys - raw.keys()), sorted(raw.keys() - keys)
    if missing or unknown:
        raise ExportError(f"missing keys {missing}, unknown keys {unknown}")
    times = {name: _utc(name, raw[name]) for name in ("as_of", "source_feed_timestamp")}
    for name in ("bundle_id", "warehouse_sha256"):
        if not _SHA256.fullmatch(str(raw[name])):
            raise ExportError(f"{name} must be a full 64-character SHA-256")
    if times["source_feed_timestamp"] > times["as_of"]:
        raise ExportError("source_feed_timestamp is after as_of")
    return ExportSpec(
        as_of=times["as_of"],
        source_feed_timestamp=times["source_feed_timestamp"],
        model_version=str(raw["model_version"]),
        bundle_id=str(raw["bundle_id"]),
        warehouse_sha256=str(raw["warehouse_sha256"]),
        output_dir=Path(raw["output_dir"]),
    )


def _utc(name: str, value) -> datetime:
    try:
        ts = datetime.fromisoformat(str(value))
    except ValueError as e:
        raise ExportError(f"{name} is not an ISO-8601 timestamp: {value!r}") from e
    if ts.tzinfo is None:
        raise ExportError(f"{name} must include a UTC offset, e.g. 2026-10-20T17:00:00Z")
    return ts.astimezone(UTC)


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def encode(value) -> bytes:
    """Compact, deterministic JSON: the API's key order, no whitespace, UTF-8."""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def encode_manifest(manifest: dict) -> bytes:
    return json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=1).encode() + b"\n"


# -- the files and the requests they answer ------------------------------------------


def _safe(value: str, what: str) -> str:
    if not _ID.fullmatch(value):
        raise ExportError(f"{what} {value!r} is not safe in a file name")
    return value


def board_file(station_id: str, boarding_group: str) -> str:
    return (
        f"boards/{_safe(station_id, 'station id')}/{_safe(boarding_group, 'boarding group')}.json"
    )


def history_file(prediction_id: str) -> str:
    """history/<service date>_<trip id>_<stop sequence>.json: the prediction ID with its
    colons replaced, so a client can find the file from the ID alone."""
    key = parse_prediction_id(prediction_id)
    if key is None or prediction_id != f"{key[0]}:{key[1]}:{key[2]}":
        raise ExportError(f"prediction id {prediction_id!r} is not service_date:trip:sequence")
    day, trip_id, sequence = key
    return f"history/{day}_{_safe(trip_id, 'trip id')}_{sequence}.json"


@dataclass(frozen=True)
class Answer:
    file: str  # path in the export
    request: str  # the API request it answers
    model: str  # response model of the body (of each item for stations and history)
    body: object  # the API's JSON body


async def _get(app, path: str, query: dict[str, str] | None = None) -> tuple[int, object]:
    """One GET through the app's whole ASGI stack (middleware, routing, validation,
    response model, serialization), in process: no server and no port."""
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": quote(path).encode(),
        "root_path": "",
        "query_string": urlencode(query or {}).encode(),
        "headers": [(b"accept", b"application/json")],
        "client": None,
        "server": None,
    }
    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, json.loads(body)


async def _ask_everything(app) -> list[Answer]:
    """Every request the website can make at the replay time, in a fixed order."""
    answers: list[Answer] = []

    async def ask(file: str, model: str, path: str, query: dict | None = None):
        status, body = await _get(app, path, query)
        request = path + (f"?{urlencode(query)}" if query else "")
        if status != 200:
            raise ExportError(f"{request} answered HTTP {status}: {body}")
        answers.append(Answer(file, request, model, body))
        return body

    await ask("health.json", "HealthStatus", "/api/v1/health")
    await ask("model.json", "ModelMetadata", "/api/v1/model/metadata")
    stations = await ask("stations.json", "Station", "/api/v1/stations")
    for station in stations:
        for group in station["boardingGroups"]:
            board = await ask(
                board_file(station["id"], group["id"]),
                "PredictionResponse",
                f"/api/v1/stations/{station['id']}/predictions",
                {"boarding_group": group["id"]},
            )
            for train in board["trains"]:
                pid = train["predictionId"]
                await ask(
                    history_file(pid),
                    "PredictionHistoryPoint",
                    f"/api/v1/predictions/{pid}/history",
                )
    files = Counter(a.file for a in answers)
    if any(n > 1 for n in files.values()):
        raise ExportError(f"requests share a file: {[f for f, n in files.items() if n > 1]}")
    return answers


# -- loading, checking and rendering ---------------------------------------------------


def load_replay(config: LocalApiConfig, spec: ExportSpec):
    """The local API at the pinned replay; refuses any input that differs from a pin."""
    from bart_reliability.api.app import ApiState, create_app

    if config.as_of != spec.as_of:
        raise ExportError(
            f"local API as_of {iso(config.as_of)} is not the pinned {iso(spec.as_of)}"
        )
    if config.bundle_id not in (None, spec.bundle_id):
        raise ExportError("the local API config pins a different bundle_id than the spec")
    if not config.warehouse.is_file():
        raise ExportError(f"warehouse not found: {config.warehouse}")
    digest = sha256_file(config.warehouse)
    if digest != spec.warehouse_sha256:
        raise ExportError(f"warehouse SHA-256 {digest} is not the pinned {spec.warehouse_sha256}")
    state = ApiState.load(config, expected_bundle_id=spec.bundle_id)
    problems = state.problems()
    if problems:
        raise ExportError(f"the replay is not healthy: {problems}")
    version = state.predictor.metadata["model"]["version"]
    if version != spec.model_version:
        raise ExportError(f"model {version} is not the pinned {spec.model_version}")
    feed = state.engine.snapshot.feed_timestamp
    if feed != spec.source_feed_timestamp:
        raise ExportError(
            f"the replay snapshot {iso(feed)} is not the pinned {iso(spec.source_feed_timestamp)}"
        )
    return state, create_app(config, state)


def _when(text: str) -> datetime:
    return datetime.fromisoformat(text)


def replay_problems(answers: list[Answer], spec: ExportSpec) -> list[str]:
    """No observed time after as_of anywhere in the API's full answers (omitted fields
    included), and every board and history from the pinned snapshot or before it."""
    problems = []
    for a in answers:
        problems += future_times(a.body, spec.as_of, a.request)
        if a.model == "HealthStatus":
            if a.body["status"] != "ok" or a.body["problems"]:
                problems.append(f"{a.request}: the replay is not healthy")
            latest = a.body["latestFeedTimestamp"]
            if latest is None or _when(latest) != spec.source_feed_timestamp:
                problems.append(f"{a.request}: latestFeedTimestamp is not the pinned snapshot")
        elif a.model == "PredictionResponse":
            if _when(a.body["feedTimestamp"]) != spec.source_feed_timestamp:
                problems.append(f"{a.request}: feedTimestamp is not the pinned snapshot")
            if _when(a.body["generatedAt"]) != spec.as_of:
                problems.append(f"{a.request}: generatedAt is not the replay time")
        elif a.model == "PredictionHistoryPoint":
            if any(_when(p["feedTimestamp"]) > spec.source_feed_timestamp for p in a.body):
                problems.append(f"{a.request}: a point is after the pinned snapshot")
    return problems


def render(answers: list[Answer], spec: ExportSpec) -> dict[str, bytes]:
    problems = replay_problems(answers, spec)
    files = {a.file: encode(project(a.model, a.body, a.request, problems)) for a in answers}
    if problems:
        shown = "; ".join(problems[:10])
        raise ExportError(f"{len(problems)} problem(s), nothing exported: {shown}")
    return files


def _records(body) -> int:
    if isinstance(body, list):
        return len(body)
    return len(body["trains"]) if "trains" in body else 1


def build_manifest(
    answers: list[Answer], files: dict[str, bytes], state, config: LocalApiConfig, spec: ExportSpec
) -> dict:
    meta, engine = state.predictor.metadata, state.engine
    with engine.con.cursor() as cur:
        schedules = cur.execute(
            "SELECT archive_label, archive_sha256, feed_version FROM static_feed_load ORDER BY ALL"
        ).fetchall()
    by_file = {a.file: a for a in answers}
    boards = [a.body for a in answers if a.model == "PredictionResponse"]
    trains = [t for b in boards for t in b["trains"]]
    histories = [a.body for a in answers if a.model == "PredictionHistoryPoint"]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "dataMode": "historical_replay",
        "notice": NOTICE,
        "replay": {
            "asOf": iso(spec.as_of),
            "sourceFeedTimestamp": iso(engine.snapshot.feed_timestamp),
            "sourceCollectedAt": iso(engine.snapshot.collected_at),
            "serviceDate": str(engine.service_date),
        },
        "provenance": {
            "model": {
                "modelVersion": meta["model"]["version"],
                "bundleId": meta["bundle_id"],
                "featureSchemaVersion": meta["feature_schema_version"],
                "trainingDataCutoff": meta["training_data"]["training_data_cutoff_utc"],
                "calibrationDataCutoff": meta["training_data"]["calibration_data_cutoff_utc"],
            },
            "warehouse": {"file": config.warehouse.name, "sha256": spec.warehouse_sha256},
            "staticSchedule": [
                {"archiveLabel": label, "archiveSha256": sha, "feedVersion": version}
                for label, sha, version in schedules
            ],
            "replaySettings": {
                "historyLookbackSeconds": config.history_lookback_seconds,
                "staleAfterSeconds": config.stale_after_seconds,
                "stabilityMayBeRevised": config.stability_may_be_revised,
                "stabilityLikelyToBeRevised": config.stability_likely_to_be_revised,
            },
            "responses": (
                "Local API responses (bart-serve-local), each reduced to the fields "
                "web/src/data/apiDecode.ts reads"
            ),
        },
        "counts": {
            "files": len(files),
            "bytes": sum(len(b) for b in files.values()),
            "stations": len(by_file["stations.json"].body),
            "boards": len(boards),
            "emptyBoards": sum(not b["trains"] for b in boards),
            "trains": len(trains),
            "trainsByStatus": dict(sorted(Counter(t["predictionStatus"] for t in trains).items())),
            "trainsWithInterval": sum(t["revisionInterval"] is not None for t in trains),
            "alerts": len({a["alertId"] for b in boards for a in b["alerts"]}),
            "historyFiles": len(histories),
            "historyPoints": sum(len(h) for h in histories),
        },
        "files": {
            path: {
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "records": _records(by_file[path].body),
            }
            for path, data in sorted(files.items())
        },
    }


# -- verification -----------------------------------------------------------------------


def read_manifest(export_dir: Path) -> dict:
    """The manifest, once it is well formed and the files on disk are exactly the files
    it lists, with its sizes and hashes."""
    try:
        manifest = json.loads((export_dir / MANIFEST).read_bytes())
    except FileNotFoundError as e:
        raise ExportError(f"no {MANIFEST} in {export_dir}") from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ExportError(f"{MANIFEST} is not valid JSON: {e}") from e
    shape = {
        "schemaVersion": str,
        "dataMode": str,
        "notice": str,
        "replay": dict,
        "provenance": dict,
        "counts": dict,
        "files": dict,
    }
    if not isinstance(manifest, dict) or set(manifest) != set(shape):
        raise ExportError(f"{MANIFEST} must have exactly the keys {sorted(shape)}")
    wrong = [k for k, kind in shape.items() if not isinstance(manifest[k], kind)]
    if wrong:
        raise ExportError(f"{MANIFEST} has values of the wrong type: {wrong}")
    if manifest["schemaVersion"] != SCHEMA_VERSION:
        raise ExportError(f"unsupported schemaVersion {manifest['schemaVersion']!r}")
    if manifest["dataMode"] != "historical_replay":
        raise ExportError("dataMode must be historical_replay")
    problems = []
    for rel, entry in manifest["files"].items():
        if not _FILE.fullmatch(rel):
            problems.append(f"{rel}: not a path an export contains")
            continue
        if not _valid_entry(entry):
            problems.append(f"{rel}: malformed entry {entry!r}")
            continue
        path = export_dir / rel
        if path.is_symlink() or not path.is_file():
            problems.append(f"{rel}: listed but missing")
            continue
        data = path.read_bytes()
        if len(data) != entry["bytes"]:
            problems.append(f"{rel}: {len(data)} bytes, manifest says {entry['bytes']}")
        elif hashlib.sha256(data).hexdigest() != entry["sha256"]:
            problems.append(f"{rel}: SHA-256 differs from the manifest")
    on_disk = {
        p.relative_to(export_dir).as_posix()
        for p in export_dir.rglob("*")
        if not p.is_dir() or p.is_symlink()
    }
    problems += [
        f"{p}: not in the manifest" for p in sorted(on_disk - {MANIFEST} - manifest["files"].keys())
    ]
    if manifest["counts"].get("files") != len(manifest["files"]):
        problems.append("counts.files is not the number of files listed")
    if problems:
        raise ExportError(f"{len(problems)} manifest problem(s): {'; '.join(problems[:10])}")
    return manifest


def _valid_entry(entry) -> bool:
    return (
        isinstance(entry, dict)
        and set(entry) == {"bytes", "sha256", "records"}
        and all(type(entry[k]) is int and entry[k] >= 0 for k in ("bytes", "records"))
        and isinstance(entry["sha256"], str)
        and _SHA256.fullmatch(entry["sha256"]) is not None
    )


def first_difference(a, b, path: str = "$") -> str | None:
    if type(a) is not type(b):
        return f"{path}: {a!r} != {b!r}"
    if isinstance(a, dict):
        if list(a) != list(b):
            return f"{path}: fields {list(a)} != {list(b)}"
        for key in a:
            found = first_difference(a[key], b[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: {len(a)} items != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            found = first_difference(x, y, f"{path}[{i}]")
            if found:
                return found
        return None
    return None if a == b else f"{path}: {a!r} != {b!r}"


@dataclass
class ParityReport:
    """An export compared with a freshly loaded API's answers to the same requests."""

    requests: int = 0
    identical: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    differences: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    manifest_identical: bool = False

    @property
    def ok(self) -> bool:
        return (
            not (self.differences or self.missing or self.extra)
            and self.manifest_identical
            and self.identical == self.requests
        )

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "requests": self.requests,
            "identical": self.identical,
            "byKind": self.by_kind,
            "differences": self.differences,
            "missingFiles": self.missing,
            "extraFiles": self.extra,
            "manifestIdentical": self.manifest_identical,
            # Removed from every answer by design (contract.py), never compared.
            "omittedFields": {m: list(omitted_fields(m)) for m in OMITTING_MODELS},
        }


def verify_export(export_dir: Path, config: LocalApiConfig, spec: ExportSpec) -> ParityReport:
    """Check the manifest and every file, then ask a freshly loaded API every request
    again and compare each file with its reduced answer, byte for byte."""
    manifest = read_manifest(export_dir)
    state, app = load_replay(config, spec)
    answers = asyncio.run(_ask_everything(app))
    expected = render(answers, spec)
    stored = {rel: (export_dir / rel).read_bytes() for rel in manifest["files"]}
    report = ParityReport(requests=len(answers))
    report.missing = sorted(expected.keys() - stored.keys())
    report.extra = sorted(stored.keys() - expected.keys())
    kinds = Counter()
    for a in answers:
        kinds[a.file.split("/")[0].removesuffix(".json")] += 1
        if a.file not in stored:
            continue
        if stored[a.file] == expected[a.file]:
            report.identical += 1
        else:
            found = first_difference(json.loads(stored[a.file]), json.loads(expected[a.file]))
            report.differences.append(f"{a.file}: {found or 'same values, different bytes'}")
    report.by_kind = dict(sorted(kinds.items()))
    fresh = build_manifest(answers, expected, state, config, spec)
    report.manifest_identical = (export_dir / MANIFEST).read_bytes() == encode_manifest(fresh)
    return report


# -- export -------------------------------------------------------------------------------


@dataclass(frozen=True)
class ExportResult:
    out_dir: Path
    manifest: dict
    parity: ParityReport


def export_replay(
    config: LocalApiConfig, spec: ExportSpec, out_root: Path | None = None
) -> ExportResult:
    """Write the export to <out_root>/<spec.name>, replacing any earlier one only after
    the new one has passed verification."""
    out_dir = (out_root or spec.output_dir) / spec.name
    state, app = load_replay(config, spec)
    answers = asyncio.run(_ask_everything(app))
    files = render(answers, spec)
    manifest = build_manifest(answers, files, state, config, spec)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_dir.with_name(f".{out_dir.name}.building")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        for rel, data in files.items():
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / rel).write_bytes(data)
        (tmp / MANIFEST).write_bytes(encode_manifest(manifest))
        parity = verify_export(tmp, config, spec)
        if not parity.ok:
            raise ExportError(f"parity check failed, nothing exported: {parity.as_dict()}")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    old = out_dir.with_name(f".{out_dir.name}.old")
    shutil.rmtree(old, ignore_errors=True)
    if out_dir.exists():
        out_dir.rename(old)
    tmp.rename(out_dir)
    shutil.rmtree(old, ignore_errors=True)
    return ExportResult(out_dir, manifest, parity)


# -- sizes --------------------------------------------------------------------------------


def size_report(export_dir: Path, manifest: dict) -> dict:
    """Bytes on disk and gzip-compressed (an estimate of what a host that compresses JSON
    sends) per kind of file, and the files the website fetches on its first view."""

    def gz(rel: str) -> int:
        data = (export_dir / rel).read_bytes()
        return len(gzip.compress(data, compresslevel=_GZIP_LEVEL, mtime=0))

    sizes = {rel: (entry["bytes"], gz(rel)) for rel, entry in manifest["files"].items()}
    kinds: dict[str, list[str]] = {}
    for rel in sizes:
        kinds.setdefault(rel.split("/")[0].removesuffix(".json"), []).append(rel)

    def total(rels) -> dict:
        raw = [sizes[r][0] for r in rels]
        return {
            "files": len(rels),
            "bytes": sum(raw),
            "gzipBytes": sum(sizes[r][1] for r in rels),
            "minBytes": min(raw),
            "medianBytes": int(statistics.median(raw)),
            "maxBytes": max(raw),
        }

    manifest_bytes = (export_dir / MANIFEST).stat().st_size
    return {
        "total": total(list(sizes)) | {"manifestBytes": manifest_bytes},
        "byKind": {kind: total(rels) for kind, rels in sorted(kinds.items())},
        "largest": [
            {"file": rel, "bytes": b, "gzipBytes": g}
            for rel, (b, g) in sorted(sizes.items(), key=lambda kv: (-kv[1][0], kv[0]))[:5]
        ],
        "firstView": _first_view(export_dir, sizes),
    }


def _first_view(export_dir: Path, sizes: dict[str, tuple[int, int]]) -> dict:
    """With no station in the address, the website asks for health and the station list,
    shows the first station's first boarding group and selects its earliest train, whose
    history it then fetches (web/src/components/PredictionExample.tsx)."""
    stations = json.loads((export_dir / "stations.json").read_bytes())
    station = stations[0]
    group = station["boardingGroups"][0]
    rels = ["health.json", "stations.json", board_file(station["id"], group["id"])]
    trains = json.loads((export_dir / rels[-1]).read_bytes())["trains"]
    if trains:
        rels.append(history_file(trains[0]["predictionId"]))
    return {
        "station": station["id"],
        "boardingGroup": group["id"],
        "files": rels,
        "bytes": sum(sizes[r][0] for r in rels),
        "gzipBytes": sum(sizes[r][1] for r in rels),
    }
