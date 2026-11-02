"""Offline check of the published showcase files (web/public/showcase).

Like `check_public`, it needs neither the warehouse nor the bundle, so CI and the Pages
workflow can run it. It checks that the showcase files are exactly the four expected,
that their hashes match showcase.json, that they belong to the published replay beside
them, and that every record they name is a supported train of that replay with the same
values, ranked and counted as docs/showcase_replay.md says.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from bart_reliability.static_replay.check import read_index
from bart_reliability.static_replay.export import ExportError

SHOWCASE_FILES = ("showcase.json", "retrospective.json", "largest-changes.json", "network-map.json")
SCHEMA_VERSIONS = {
    "showcase.json": "showcase-1",
    "retrospective.json": "showcase-retrospective-1",
    "largest-changes.json": "showcase-largest-changes-1",
    "network-map.json": "showcase-network-map-1",
}
FORBIDDEN_PHRASES = (
    "actual arrival",
    "true arrival",
    "train lateness",
    "the train was late",
    "corrected arrival",
)
PER_HORIZON_LIMIT = 5


def _trains(replay_root: Path, export: str) -> dict[str, dict]:
    """Every train of the published replay's boards, with its board's station and group."""
    out = {}
    for path in sorted((replay_root / export / "boards").rglob("*.json")):
        board = json.loads(path.read_bytes())
        for t in board["trains"]:
            out[t["predictionId"]] = t | {
                "stationId": board["stationId"],
                "boardingGroupId": board["boardingGroupId"],
            }
    return out


def check_showcase(showcase_dir: Path, replay_root: Path) -> dict:
    """Check the showcase files against the published replay; raises ExportError."""
    problems: list[str] = []
    if not showcase_dir.is_dir():
        raise ExportError(f"{showcase_dir} is not a directory")
    entries = sorted(p.name for p in showcase_dir.iterdir())
    if entries != sorted(SHOWCASE_FILES):
        raise ExportError(f"{showcase_dir} must hold exactly {sorted(SHOWCASE_FILES)}: {entries}")
    raw = {name: (showcase_dir / name).read_bytes() for name in SHOWCASE_FILES}
    docs = {name: json.loads(data) for name, data in raw.items()}
    meta = docs["showcase.json"]

    for name, version in SCHEMA_VERSIONS.items():
        if docs[name].get("schemaVersion") != version:
            problems.append(f"{name}: schemaVersion is not {version}")
        if docs[name].get("dataMode") != "historical_replay":
            problems.append(f"{name}: not labelled as a historical replay")
        if docs[name].get("asOf") != meta.get("asOf"):
            problems.append(f"{name}: asOf is not showcase.json's")
    for name in SHOWCASE_FILES[1:]:
        listed = meta.get("files", {}).get(name)
        actual = {"bytes": len(raw[name]), "sha256": hashlib.sha256(raw[name]).hexdigest()}
        if listed != actual:
            problems.append(f"{name}: size or SHA-256 differs from showcase.json")
    text = b"".join(raw.values()).decode().lower()
    problems += [f"uses the phrase {p!r}" for p in FORBIDDEN_PHRASES if p in text]

    index = read_index(replay_root)
    provenance = meta.get("provenance", {})
    if provenance.get("replayExport") != index["export"]:
        problems.append("showcase.json names another replay export")
    if provenance.get("replayManifestSha256") != index["manifestSha256"]:
        problems.append("showcase.json names another replay manifest")
    if meta.get("asOf") != index["asOf"]:
        problems.append("showcase.json's replay time is not the replay's")

    trains = _trains(replay_root, index["export"])
    unsupported = [p for p, t in trains.items() if t["predictionStatus"] != "ok"]
    if unsupported:
        problems.append(f"the replay lists trains without a supported forecast: {unsupported[:5]}")
    records = {r["predictionId"]: r for r in docs["retrospective.json"]["records"]}
    if set(records) != set(trains):
        problems.append("retrospective.json does not cover exactly the replay's trains")
    for pid, r in records.items():
        t = trains.get(pid)
        if t and r["stationId"] != t["stationId"]:
            problems.append(f"{pid}: retrospective station differs from the replay")
    counts = meta.get("counts", {})
    if counts.get("includedRecords") != len(trains):
        problems.append("showcase.json's includedRecords is not the replay's train count")
    if counts.get("stationsRepresented") != len({t["stationId"] for t in trains.values()}):
        problems.append("showcase.json's stationsRepresented is not the replay's")

    for horizon, rows in docs["largest-changes.json"]["byHorizon"].items():
        if len(rows) > PER_HORIZON_LIMIT:
            problems.append(f"largest changes at {horizon} s: more than {PER_HORIZON_LIMIT} rows")
        if len({r["tripRunId"] for r in rows}) != len(rows):
            problems.append(f"largest changes at {horizon} s: a trip run is listed twice")
        sizes = [abs(r["realizedRevisionSeconds"]) for r in rows]
        if sizes != sorted(sizes, reverse=True):
            problems.append(f"largest changes at {horizon} s: not ranked by realized revision")
        for r in rows:
            t, rec = trains.get(r["predictionId"]), records.get(r["predictionId"])
            if not t or not rec:
                problems.append(f"largest changes: {r['predictionId']} is not in the replay")
                continue
            same = (
                r["horizonSeconds"] == int(horizon)
                and r["bartPublishedEtaSeconds"] == t["currentEtaSeconds"]
                and r["predictedRevisionSeconds"] == t["predictedRevisionSeconds"]
                and r["modelAdjustedEtaSeconds"]
                == t["currentEtaSeconds"] + t["predictedRevisionSeconds"]
                and r["realizedRevisionSeconds"] == rec["realizedRevisionSeconds"]
                and r["stationId"] == t["stationId"]
                and r["boardingGroupId"] == t["boardingGroupId"]
            )
            if not same:
                problems.append(f"largest changes: {r['predictionId']} differs from the replay")

    per_station = Counter(r["stationId"] for r in records.values())
    for s in docs["network-map.json"]["stations"]:
        if s["supportedForecastCount"] != per_station.get(s["stationId"], 0):
            problems.append(f"network map: {s['stationId']} count differs from the replay")
        for key in ("largestPredictedRecord", "largestRealizedRecord"):
            rec = s.get(key)
            train = trains.get(rec["predictionId"], {}) if rec else None
            if rec and (
                train.get("stationId") != s["stationId"]
                or train.get("boardingGroupId") != rec["boardingGroupId"]
            ):
                problems.append(f"network map: {s['stationId']} {key} is not its own train")
    map_trains = {t["predictionId"]: t for t in docs["network-map.json"].get("trains", [])}
    if set(map_trains) != set(trains):
        problems.append("network map: its trains are not exactly the replay's trains")
    for pid, mt in map_trains.items():
        t, rec = trains.get(pid), records.get(pid)
        if (
            t
            and rec
            and (
                mt["stationId"] != t["stationId"]
                or mt["boardingGroupId"] != t["boardingGroupId"]
                or mt["lineName"] != t["lineName"]
                or mt["predictedRevisionSeconds"] != t["predictedRevisionSeconds"]
                or mt["realizedRevisionSeconds"] != rec["realizedRevisionSeconds"]
            )
        ):
            problems.append(f"network map: train {pid} differs from the replay")
    missing = set(per_station) - {s["stationId"] for s in docs["network-map.json"]["stations"]}
    if missing:
        problems.append(f"network map: stations with trains are missing: {sorted(missing)}")

    if problems:
        shown = "; ".join(problems[:10])
        raise ExportError(f"{len(problems)} problem(s) in the published showcase: {shown}")
    return {
        "asOf": meta["asOf"],
        "includedRecords": len(trains),
        "stationsRepresented": counts["stationsRepresented"],
        "files": {name: hashlib.sha256(raw[name]).hexdigest() for name in SHOWCASE_FILES},
    }
