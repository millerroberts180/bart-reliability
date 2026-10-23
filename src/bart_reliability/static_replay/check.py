"""The published static replay (web/public/replay): publishing it, and checking it offline.

`publish` copies a verified export next to a small index.json that tells the website
which export to read and which schema it uses. `check` needs neither the warehouse nor
the bundle: it re-derives everything from the published files, so CI and the Pages
workflow can refuse a damaged or inconsistent replay before it is built or deployed.
It checks:

- the index and the manifest: shape, schema version, data mode, and the manifest's
  SHA-256;
- the files: paths, sizes and hashes match the manifest, and nothing else is present;
- schemas: every file holds exactly the kept fields (contract.KEEP), strictly typed;
- consistency, the rules the website's decoder relies on, and cross-references. Every
  boarding group has its board, every train its history, and nothing is orphaned;
- the counts and per-file record counts, recomputed;
- no future data: no observed time after the replay time, and every board, history
  and health answer from the replay's source snapshot or before it.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from bart_reliability.static_replay.contract import (
    KEEP,
    NESTED,
    api_fields,
    future_times,
    static_model,
)
from bart_reliability.static_replay.export import (
    MANIFEST,
    SCHEMA_VERSION,
    ExportError,
    board_file,
    counts,
    encode,
    history_file,
    read_manifest,
    records,
)

PUBLIC_ROOT = Path("web/public/replay")
INDEX = "index.json"
INDEX_KEYS = ("schemaVersion", "dataMode", "export", "asOf", "manifestSha256")
_EXPORT_NAME = re.compile(r"v1-\d{8}T\d{6}Z")
_SHA256 = re.compile(r"[0-9a-f]{64}")
# File kind (first path segment) -> response model of the file (of each item for lists).
_MODELS = {
    "health.json": "HealthStatus",
    "model.json": "ModelMetadata",
    "stations.json": "Station",
    "boards": "PredictionResponse",
    "history": "PredictionHistoryPoint",
}


def build_index(export_dir: Path) -> dict:
    manifest = (export_dir / MANIFEST).read_bytes()
    return {
        "schemaVersion": SCHEMA_VERSION,
        "dataMode": "historical_replay",
        "export": export_dir.name,
        "asOf": json.loads(manifest)["replay"]["asOf"],
        "manifestSha256": hashlib.sha256(manifest).hexdigest(),
    }


def read_index(public_root: Path) -> dict:
    """index.json, once its shape and values are what the website accepts."""
    try:
        index = json.loads((public_root / INDEX).read_bytes())
    except FileNotFoundError as e:
        raise ExportError(f"no {INDEX} in {public_root}") from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ExportError(f"{INDEX} is not valid JSON: {e}") from e
    if not isinstance(index, dict) or list(index) != list(INDEX_KEYS):
        raise ExportError(f"{INDEX} must have exactly the keys {list(INDEX_KEYS)}, in order")
    if not all(isinstance(v, str) for v in index.values()):
        raise ExportError(f"every value in {INDEX} must be a string")
    if index["schemaVersion"] != SCHEMA_VERSION:
        raise ExportError(f"unsupported schemaVersion {index['schemaVersion']!r}")
    if index["dataMode"] != "historical_replay":
        raise ExportError("dataMode must be historical_replay")
    if not _EXPORT_NAME.fullmatch(index["export"]):
        raise ExportError(f"export {index['export']!r} is not an export directory name")
    if not _SHA256.fullmatch(index["manifestSha256"]):
        raise ExportError("manifestSha256 must be a full 64-character SHA-256")
    if _time(index["asOf"]) is None:
        raise ExportError("asOf is not a timestamp with a time zone")
    return index


def check_public(public_root: Path = PUBLIC_ROOT) -> dict:
    """Check the published replay offline; raises ExportError listing what is wrong."""
    index = read_index(public_root)
    entries = sorted(p.name for p in public_root.iterdir())
    if entries != sorted([INDEX, index["export"]]):
        raise ExportError(f"{public_root} must hold only {INDEX} and {index['export']}: {entries}")
    export_dir = public_root / index["export"]
    if export_dir.is_symlink() or not export_dir.is_dir():
        raise ExportError(f"{index['export']} is not a directory")
    manifest = read_manifest(export_dir)
    if hashlib.sha256((export_dir / MANIFEST).read_bytes()).hexdigest() != index["manifestSha256"]:
        raise ExportError(f"the manifest's SHA-256 is not the one {INDEX} names")
    problems = check_files(export_dir, manifest)
    if manifest["replay"].get("asOf") != index["asOf"]:
        problems.append(f"{INDEX} asOf is not the manifest's replay time")
    if problems:
        shown = "; ".join(problems[:10])
        raise ExportError(f"{len(problems)} problem(s) in the published replay: {shown}")
    return {
        "export": index["export"],
        "schemaVersion": index["schemaVersion"],
        "asOf": index["asOf"],
        "sourceFeedTimestamp": manifest["replay"]["sourceFeedTimestamp"],
        "manifestSha256": index["manifestSha256"],
        "model": manifest["provenance"]["model"],
        "warehouse": manifest["provenance"]["warehouse"],
        "counts": manifest["counts"],
    }


def check_files(export_dir: Path, manifest: dict) -> list[str]:
    """Schemas, consistency, cross-references, counts and no future data, from the files."""
    problems: list[str] = []
    replay = manifest["replay"]
    as_of, source = _time(replay.get("asOf")), _time(replay.get("sourceFeedTimestamp"))
    if as_of is None or source is None or source > as_of:
        return ["manifest replay.asOf and replay.sourceFeedTimestamp must be ordered timestamps"]
    files = {rel: (export_dir / rel).read_bytes() for rel in manifest["files"]}
    bodies = {}
    for rel, data in files.items():
        try:
            bodies[rel] = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            problems.append(f"{rel}: not valid JSON ({e})")
            continue
        if encode(bodies[rel]) != data:
            problems.append(f"{rel}: not in the exporter's compact form")
        problems += _schema(rel, bodies[rel])
        problems += future_times(bodies[rel], as_of, rel)
    if problems:
        return problems  # the checks below assume well-formed files

    def when(text: str) -> datetime:
        return _time(text)

    health, model, stations = bodies["health.json"], bodies["model.json"], bodies["stations.json"]
    if health["status"] != "ok" or when(health["asOf"]) != as_of:
        problems.append("health.json: not an ok answer at the replay time")
    if health["latestFeedTimestamp"] is None or when(health["latestFeedTimestamp"]) != source:
        problems.append("health.json: latestFeedTimestamp is not the source snapshot")
    if health["dataMode"] != "historical_replay":
        problems.append("health.json: dataMode is not historical_replay")
    problems += _duplicates("stations.json", [s["id"] for s in stations], "station")

    expected_boards, expected_histories = set(), set()
    for station in stations:
        groups = [g["id"] for g in station["boardingGroups"]]
        problems += _duplicates(f"stations.json {station['id']}", groups, "boarding group")
        for group in groups:
            try:
                expected_boards.add(board_file(station["id"], group))
            except ExportError as e:
                problems.append(f"stations.json: {e}")
    boards = {rel: b for rel, b in bodies.items() if rel.startswith("boards/")}
    problems += [
        f"{rel}: listed in stations.json but missing"
        for rel in sorted(expected_boards - boards.keys())
    ]
    problems += [
        f"{rel}: not a boarding group in stations.json"
        for rel in sorted(boards.keys() - expected_boards)
    ]
    seen_ids = []
    for rel, board in sorted(boards.items()):
        if rel != f"boards/{board['stationId']}/{board['boardingGroupId']}.json":
            problems.append(
                f"{rel}: holds the board of {board['stationId']} {board['boardingGroupId']}"
            )
        if board["dataMode"] != "historical_replay" or when(board["replay"]["asOf"]) != as_of:
            problems.append(f"{rel}: not labelled as the historical replay at the replay time")
        if when(board["generatedAt"]) != as_of or when(board["feedTimestamp"]) != source:
            problems.append(f"{rel}: not generated at the replay time from the source snapshot")
        if board["model"] != model:
            problems.append(f"{rel}: model block differs from model.json")
        for train in board["trains"]:
            problems += _train(rel, train)
            seen_ids.append(train["predictionId"])
            try:
                expected_histories.add(history_file(train["predictionId"]))
            except ExportError as e:
                problems.append(f"{rel}: {e}")
    problems += _duplicates("boards", seen_ids, "prediction")
    histories = {rel: h for rel, h in bodies.items() if rel.startswith("history/")}
    problems += [
        f"{rel}: a train's history is missing"
        for rel in sorted(expected_histories - histories.keys())
    ]
    problems += [
        f"{rel}: no train on any board" for rel in sorted(histories.keys() - expected_histories)
    ]
    for rel, points in sorted(histories.items()):
        if not points:
            problems.append(f"{rel}: empty history")
        problems += _duplicates(rel, [p["feedTimestamp"] for p in points], "snapshot")
        for p in points:
            seconds = (when(p["publishedEtaAt"]) - when(p["feedTimestamp"])).total_seconds()
            if when(p["feedTimestamp"]) > source:
                problems.append(f"{rel}: a point is after the source snapshot")
            if seconds != p["publishedEtaSeconds"]:
                problems.append(f"{rel}: publishedEtaSeconds is not publishedEtaAt - feedTimestamp")

    recount = counts(files, bodies)
    if recount != manifest["counts"]:
        changed = sorted(
            k
            for k in recount.keys() | manifest["counts"].keys()
            if recount.get(k) != manifest["counts"].get(k)
        )
        problems.append(f"manifest counts differ from the files: {changed}")
    for rel, body in bodies.items():
        if records(body) != manifest["files"][rel]["records"]:
            problems.append(f"{rel}: manifest records differ from the file")
    return problems


def _schema(rel: str, body) -> list[str]:
    model = _MODELS[rel.split("/")[0]]
    items = body if model in ("Station", "PredictionHistoryPoint") else [body]
    if not isinstance(items, list):
        return [f"{rel}: expected a list"]
    problems = []
    for i, item in enumerate(items):
        try:
            static_model(model).model_validate(item)
        except ValidationError as e:
            first = e.errors()[0]
            where = ".".join(str(p) for p in first["loc"])
            problems.append(f"{rel}[{i}].{where}: {first['msg']} ({e.error_count()} error(s))")
            continue
        problems += _order(rel, model, item)
    return problems


def _order(rel: str, model: str, value) -> list[str]:
    """Kept fields in the API's order, at every level."""
    if not isinstance(value, dict):
        return []
    expected = [f for f in api_fields(model) if f in KEEP[model]]
    problems = [] if list(value) == expected else [f"{rel}: {model} fields out of order"]
    for key, item in value.items():
        nested = NESTED.get((model, key))
        for part in item if isinstance(item, list) else [item]:
            if nested and part is not None:
                problems += _order(rel, nested, part)
    return problems


def _train(rel: str, t: dict) -> list[str]:
    """The website decoder's rules for one train (web/src/data/apiDecode.ts)."""
    where = f"{rel} {t['predictionId']}"
    problems = [] if t["currentEtaSeconds"] >= 0 else [f"{where}: ETA in the past"]
    model_fields = (
        "predictedRevisionSeconds",
        "revisionInterval",
        "revisionProbability",
        "stability",
    )
    if t["predictionStatus"] == "ok":
        if t["statusReason"] is not None or any(
            t[f] is None for f in model_fields if f != "revisionInterval"
        ):
            problems.append(f"{where}: an ok train without its forecast")
        elif not 0 <= t["revisionProbability"] <= 1:
            problems.append(f"{where}: revisionProbability outside 0 to 1")
        interval = t["revisionInterval"]
        if interval and not (
            interval["lowerSeconds"] <= interval["upperSeconds"] and 0 < interval["level"] <= 1
        ):
            problems.append(f"{where}: invalid revisionInterval")
    elif any(t[f] is not None for f in model_fields):
        problems.append(f"{where}: model numbers on a train without a forecast")
    return problems


def _duplicates(where: str, values: list[str], what: str) -> list[str]:
    return [f"{where}: duplicate {what} {v!r}" for v, n in Counter(values).items() if n > 1]


def _time(text) -> datetime | None:
    try:
        ts = datetime.fromisoformat(text) if isinstance(text, str) else None
    except ValueError:
        return None
    return ts if ts is not None and ts.tzinfo is not None else None


def publish(export_dir: Path, public_root: Path = PUBLIC_ROOT) -> dict:
    """Replace `public_root` with a copy of an export (verified first by the caller) and
    its index.json, after the copy passes the offline check."""
    read_manifest(export_dir)
    tmp = public_root.with_name(f".{public_root.name}.building")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        shutil.copytree(export_dir, tmp / export_dir.name)
        (tmp / INDEX).write_bytes(encode(build_index(export_dir)) + b"\n")
        summary = check_public(tmp)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    old = public_root.with_name(f".{public_root.name}.old")
    shutil.rmtree(old, ignore_errors=True)
    if public_root.exists():
        public_root.rename(old)
    tmp.rename(public_root)
    shutil.rmtree(old, ignore_errors=True)
    return summary
