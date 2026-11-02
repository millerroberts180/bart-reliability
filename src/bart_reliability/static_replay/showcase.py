"""The curated historical showcase replay (docs/showcase_replay.md).

A presentation layer over the existing model: no model is fitted, compared or changed.
Bundle 0.2.0+886fcd260732 serves every forecast through the existing local API, at one
feed snapshot of the held-out service day 2026-10-19.

1. **Select the moment.** Every feed snapshot of the day is ranked by coverage alone:
   model-supported forecasts, then stations, then trip runs, then the median absolute
   predicted revision, then the earliest time. A cheap SQL upper bound on each snapshot's
   supported forecasts lets the exact API evaluation stop once no unevaluated snapshot
   could still enter the top ten. Nothing about outcomes or accuracy is read.
2. **Export the replay.** The pinned local API answers at that snapshot, as for the
   existing static replay, reduced to the supported trains that have a tier-A final
   published ETA. Their stations, boarding groups and ETA histories are kept; nothing
   else is.
3. **Add the retrospective outcome, separately.** BART's final stable published ETA for
   each kept train comes from the warehouse's observed-arrival proxy, which the replay
   engine never sees. It goes in its own file and is never a model input.

Three ETAs, never mixed up:
- **BART published ETA:** what BART said at the replay snapshot.
- **Model-adjusted ETA:** BART's ETA plus the model's predicted revision.
- **Final published ETA:** the final stable ETA BART published later. It is a
  retrospective outcome, not a physical arrival time.

    python -m bart_reliability.static_replay.showcase build [--out PATH]
    python -m bart_reliability.static_replay.showcase publish [--out PATH] [--public web/public]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import shutil
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb

from bart_reliability.api.app import train_prediction
from bart_reliability.api.config import DEFAULT_API_CONFIG_PATH, LocalApiConfig, load_api_config
from bart_reliability.api.replay import PACIFIC, ReplayEngine, Snapshot, service_date_of
from bart_reliability.serving.predictor import Predictor, load_predictor
from bart_reliability.static_replay.check import build_index, check_public, publish
from bart_reliability.static_replay.export import (
    DEFAULT_SPEC_PATH,
    MANIFEST,
    Answer,
    ExportError,
    ExportSpec,
    _ask_everything,
    build_manifest,
    encode,
    encode_manifest,
    history_file,
    iso,
    load_export_spec,
    load_replay,
    render,
    sha256_file,
)
from bart_reliability.static_replay.showcase_check import check_showcase
from bart_reliability.warehouse.eta_revision import EXCLUDED_ROUTE_IDS, EXCLUDED_STOP_PREFIXES

SHOWCASE_DATE = date(2026, 10, 19)
DEFAULT_OUT = Path("data/static_replay/showcase")
TOP_CANDIDATES = 10
LARGEST_PER_HORIZON = 5
# The final published ETA is the observed-arrival proxy of these label-quality tiers: the
# same definition as the model's training and evaluation label.
OUTCOME_TIERS = ("A",)
DISCLOSURE = (
    "This curated replay shows only trains eligible for the model’s 5-, 10- and 15-minute "
    "forecast windows."
)
NOT_PHYSICAL = "The model predicts revisions to BART’s published ETA, not physical arrival times."
RETROSPECTIVE_NOTICE = (
    "Final published ETAs are retrospective: BART published them after the replay moment. "
    "The model did not know them, and they are not physical arrival times."
)
TERMS = {
    "bartPublishedEta": "What BART said at the replay snapshot.",
    "modelAdjustedEta": "BART’s published ETA plus the model’s predicted revision.",
    "finalPublishedEta": (
        "The final stable ETA BART published later: a retrospective outcome, not a "
        "physical arrival time."
    ),
    "predictedRevision": "Model-adjusted ETA minus BART published ETA.",
    "realizedRevision": "Final published ETA minus BART published ETA.",
    "modelError": "Model-adjusted ETA minus final published ETA.",
}
SCHEMA_VERSIONS = {
    "showcase": "showcase-1",
    "retrospective": "showcase-retrospective-1",
    "largest_changes": "showcase-largest-changes-1",
    "network_map": "showcase-network-map-1",
}


class ShowcaseError(RuntimeError):
    """The showcase cannot be built as specified; nothing is written."""


# -- 1. selecting the replay moment -------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    collected_at: datetime
    feed_timestamp: datetime
    upper_bound: int
    board_entries: int
    supported: int
    stations: int
    trip_runs: int
    median_abs_predicted_revision_s: float
    status_counts: dict

    def key(self) -> tuple:
        """Ranking order: more coverage first; the earliest time breaks the last tie."""
        return (
            -self.supported,
            -self.stations,
            -self.trip_runs,
            -self.median_abs_predicted_revision_s,
            self.collected_at,
        )

    def describe(self) -> dict:
        local = self.collected_at.astimezone(PACIFIC)
        return {
            "collectedAt": iso(self.collected_at),
            "feedTimestamp": iso(self.feed_timestamp),
            "localTime": local.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "boardEntries": self.board_entries,
            "supportedForecasts": self.supported,
            "stationsWithSupportedForecasts": self.stations,
            "tripRuns": self.trip_runs,
            "medianAbsPredictedRevisionSeconds": self.median_abs_predicted_revision_s,
            "upperBound": self.upper_bound,
            "statusCounts": self.status_counts,
        }


def day_snapshots(con: duckdb.DuckDBPyConnection, service_date: date) -> list[Snapshot]:
    """Every trip-update snapshot of a service day (03:00 to 03:00 Pacific), in order."""
    start = datetime(service_date.year, service_date.month, service_date.day, tzinfo=UTC)
    rows = con.execute(
        "SELECT feed_timestamp, collected_at FROM rt_feed_snapshots "
        "WHERE collected_at >= ? AND collected_at < ? ORDER BY collected_at, feed_timestamp",
        [start, start + timedelta(days=2)],
    ).fetchall()
    return [Snapshot(f, c) for f, c in rows if service_date_of(c) == service_date]


def upper_bounds(
    con: duckdb.DuckDBPyConnection, snapshots: list[Snapshot], buckets, tolerance_s: int
) -> dict[Snapshot, int]:
    """Per snapshot, an upper bound on its model-supported forecasts.

    It counts upcoming listings within the served horizons (one second of slack for the
    integer cast), outside the excluded lines, with a usable schedule match and not at a
    trip origin. Each is a necessary condition of a supported forecast in the API, so the
    count can only overstate. The exact evaluation checks this for every snapshot it
    evaluates.
    """
    if not snapshots:
        return {}
    horizon = " OR ".join(
        f"abs(epoch(p.predicted_arrival) - epoch(p.collected_at) - {b}) <= {tolerance_s + 1}"
        for b in buckets
    )
    stops = " OR ".join(f"p.stop_id LIKE '{x}%'" for x in EXCLUDED_STOP_PREFIXES)
    routes = ", ".join(f"'{r}'" for r in EXCLUDED_ROUTE_IDS)
    rows = con.execute(
        f"""
        WITH sp AS (
            SELECT trip_id, stop_sequence,
                   row_number() OVER (PARTITION BY trip_id ORDER BY stop_sequence) AS pos
            FROM static_stop_times
        )
        SELECT p.feed_timestamp, p.collected_at, count(*)
        FROM rt_predictions_enriched p
        LEFT JOIN sp ON sp.trip_id = p.trip_id AND sp.stop_sequence = p.scheduled_stop_sequence
        WHERE p.collected_at BETWEEN ? AND ?
          AND epoch(p.predicted_arrival) - epoch(p.feed_timestamp) >= 0
          AND ({horizon})
          AND NOT coalesce({stops}, false)
          AND NOT coalesce(p.route_id IN ({routes}), false)
          AND NOT coalesce(p.match_status <> 'matched', false)
          AND NOT coalesce(p.is_ambiguous_match, false)
          AND NOT coalesce(NOT p.include_in_primary_metrics, false)
          AND NOT coalesce(sp.pos = 1, false)
        GROUP BY 1, 2
        """,
        [snapshots[0].collected_at, snapshots[-1].collected_at],
    ).fetchall()
    found = {Snapshot(f, c): int(n) for f, c, n in rows}
    return {s: found.get(s, 0) for s in snapshots}


def snapshot_trains(
    warehouse: Path, snapshot: Snapshot, predictor: Predictor, config: LocalApiConfig
) -> list:
    """Every board entry at a snapshot, as the API's predictions endpoint builds it."""
    as_of = snapshot.collected_at
    engine = ReplayEngine(warehouse, as_of, config.history_lookback_seconds)
    if engine.snapshot != snapshot:
        raise ShowcaseError(f"the replay at {iso(as_of)} is not snapshot {snapshot}")
    cfg = replace(config, as_of=as_of)
    try:
        trains = []
        for station in engine.stations():
            for group in station["boarding_groups"]:
                rows, _, _ = engine.board(station["id"], group["id"])
                trains += [train_prediction(r, predictor, cfg) for r in rows]
    finally:
        engine.con.close()
    return trains


def trip_run_of(prediction_id: str) -> str:
    return prediction_id.rsplit(":", 1)[0]


def evaluate(trains: list, snapshot: Snapshot, upper_bound: int) -> Candidate:
    ok = [t for t in trains if t.prediction_status == "ok"]
    if len(ok) > upper_bound:
        raise ShowcaseError(
            f"snapshot {iso(snapshot.collected_at)}: {len(ok)} supported forecasts exceed "
            f"the upper bound {upper_bound}; the bound is not valid"
        )
    revisions = [abs(t.predicted_revision_seconds) for t in ok]
    return Candidate(
        collected_at=snapshot.collected_at,
        feed_timestamp=snapshot.feed_timestamp,
        upper_bound=upper_bound,
        board_entries=len(trains),
        supported=len(ok),
        stations=len({t.station_id for t in ok}),
        trip_runs=len({trip_run_of(t.prediction_id) for t in ok}),
        median_abs_predicted_revision_s=float(statistics.median(revisions)) if revisions else 0.0,
        status_counts=dict(sorted(Counter(t.prediction_status for t in trains).items())),
    )


def rank_snapshots(
    bounds: dict[Snapshot, int],
    score,
    top: int = TOP_CANDIDATES,
) -> tuple[list[Candidate], dict]:
    """The `top` best snapshots by Candidate.key, evaluating as few as possible.

    Snapshots are evaluated (score(snapshot, bound) -> Candidate) in decreasing bound
    order. Once `top` are evaluated and the next bound is below the `top`-th best
    supported count, no remaining snapshot can enter or tie its way into the top: its
    supported count is at most its bound.
    """
    order = sorted(bounds, key=lambda s: (-bounds[s], s.collected_at))
    evaluated: list[Candidate] = []
    stopped = {"stoppedAtBound": None, "topCutoffSupported": None}
    for snap in order:
        if len(evaluated) >= top:
            cutoff = sorted(evaluated, key=Candidate.key)[top - 1].supported
            if bounds[snap] < cutoff:
                stopped = {"stoppedAtBound": bounds[snap], "topCutoffSupported": cutoff}
                break
        evaluated.append(score(snap, bounds[snap]))
    ranked = sorted(evaluated, key=Candidate.key)[:top]
    return ranked, {
        "snapshotsOnServiceDay": len(order),
        "snapshotsEvaluatedExactly": len(evaluated),
        "snapshotsSkippedByBound": len(order) - len(evaluated),
        **stopped,
        "rule": (
            "Ranked by supported forecasts, then stations with supported forecasts, then "
            "trip runs, then the median absolute predicted revision (all descending), then "
            "the earliest time. Accuracy and outcomes are not read."
        ),
    }


# -- 2. the curated replay ----------------------------------------------------------------


def final_published_etas(
    con: duckdb.DuckDBPyConnection, event_ids: list[str], tiers=OUTCOME_TIERS
) -> dict[str, dict]:
    """BART's final stable published ETA per event, for eligible events of `tiers`."""
    if not event_ids:
        return {}
    con.execute("CREATE OR REPLACE TEMP TABLE _wanted (event_id VARCHAR)")
    con.executemany("INSERT INTO _wanted VALUES (?)", [(e,) for e in event_ids])
    rows = con.execute(
        """
        SELECT p.event_id, p.proxy_arrival, p.confirmed_absent_at, p.quality_tier,
               p.is_eligible, p.exclusion_reason, p.stop_id
        FROM wh.observed_arrival_proxy p JOIN _wanted USING (event_id)
        """
    ).fetchall()
    out = {}
    for event_id, final, known_at, tier, eligible, reason, stop_id in rows:
        out[event_id] = {
            "stop_id": stop_id,
            "final": final if eligible and tier in tiers else None,
            "known_at": known_at,
            "tier": tier,
            "reason": reason if not eligible else (None if tier in tiers else f"tier_{tier}"),
        }
    return out


def event_id_of(train: dict) -> str:
    """The warehouse event of a board entry: service date, trip and scheduled stop
    sequence, which is exactly its predictionId (warehouse/eta_revision.py)."""
    return train["predictionId"]


def direction(seconds: int) -> str:
    return "later" if seconds > 0 else "earlier" if seconds < 0 else "unchanged"


def retrospective_record(train: dict, final: datetime, known_at: datetime, feed: datetime) -> dict:
    """The outcome of one kept train. Seconds are relative to the snapshot's feed time,
    like BART's currentEtaSeconds."""
    published = datetime.fromisoformat(train["currentEtaAt"])
    realized = int(round((final - published).total_seconds()))
    predicted = int(train["predictedRevisionSeconds"])
    return {
        "predictionId": train["predictionId"],
        "tripRunId": trip_run_of(train["predictionId"]),
        "stationId": train["stationId"],
        "finalPublishedEtaAt": iso(final),
        "finalPublishedEtaSeconds": int(round((final - feed).total_seconds())),
        "finalPublishedEtaKnownAt": iso(known_at),
        "realizedRevisionSeconds": realized,
        "modelErrorSeconds": predicted - realized,
        "predictedDirection": direction(predicted),
        "realizedDirection": direction(realized),
        "directionMatch": direction(predicted) == direction(realized),
    }


def curate(answers: list[Answer], keep: set[str]) -> list[Answer]:
    """The API answers reduced to the kept trains: boards list only them, stations and
    boarding groups only those with a kept train, and only their histories remain."""
    by_file = {a.file: a for a in answers}
    boards = {f: a for f, a in by_file.items() if f.startswith("boards/")}
    kept_boards = {}
    for f, a in boards.items():
        trains = [t for t in a.body["trains"] if t["predictionId"] in keep]
        if trains:
            kept_boards[f] = replace(a, body=a.body | {"trains": trains})
    groups = {(a.body["stationId"], a.body["boardingGroupId"]) for a in kept_boards.values()}
    stations_answer = by_file["stations.json"]
    stations = []
    for s in stations_answer.body:
        kept = [g for g in s["boardingGroups"] if (s["id"], g["id"]) in groups]
        if kept:
            stations.append(s | {"boardingGroups": kept})
    out = []
    for a in answers:
        if a.file == "stations.json":
            out.append(replace(a, body=stations))
        elif a.file.startswith("boards/"):
            if a.file in kept_boards:
                out.append(kept_boards[a.file])
        elif a.file.startswith("history/"):
            if a.request.split("/")[4] in keep:
                out.append(a)
        else:
            out.append(a)
    histories = {a.file for a in out if a.file.startswith("history/")}
    missing = sorted(p for p in keep if history_file(p) not in histories)
    if missing:
        raise ShowcaseError(f"kept trains without an ETA history: {missing[:5]}")
    return out


def full_trains(answers: list[Answer]) -> list[dict]:
    """Every board entry in the full API answers, tagged with its board."""
    out = []
    for a in answers:
        if a.file.startswith("boards/"):
            for t in a.body["trains"]:
                out.append(t | {"boardFile": a.file, "boardingGroupId": a.body["boardingGroupId"]})
    return out


# -- 3. derived public files ----------------------------------------------------------------


def change_row(train: dict, outcome: dict, model_version: str) -> dict:
    predicted = int(train["predictedRevisionSeconds"])
    return {
        "predictionId": train["predictionId"],
        "tripRunId": outcome["tripRunId"],
        "stationId": train["stationId"],
        "stationName": train["stationName"],
        "boardingGroupId": train["boardingGroupId"],
        "destination": train["headsign"],
        "lineName": train["lineName"],
        "routeShortName": train["routeShortName"],
        "horizonSeconds": train["publishedTimeHorizonSeconds"],
        "bartPublishedEtaSeconds": train["currentEtaSeconds"],
        "bartPublishedEtaAt": train["currentEtaAt"],
        "predictedRevisionSeconds": predicted,
        "modelAdjustedEtaSeconds": train["likelyFinalEtaSeconds"],
        "modelAdjustedEtaAt": train["likelyFinalEtaAt"],
        "finalPublishedEtaSeconds": outcome["finalPublishedEtaSeconds"],
        "finalPublishedEtaAt": outcome["finalPublishedEtaAt"],
        "realizedRevisionSeconds": outcome["realizedRevisionSeconds"],
        "modelErrorSeconds": outcome["modelErrorSeconds"],
        "directionMatch": outcome["directionMatch"],
        "modelVersion": model_version,
    }


def largest_changes(rows: list[dict], per_horizon: int = LARGEST_PER_HORIZON) -> dict[str, list]:
    """Per horizon: the largest absolute realized revisions, one row per trip run.

    Ranked by |final published ETA - BART published ETA|, never by time away. Ties go to
    the lower predictionId, so the order never depends on the model's forecast.
    """
    out = {}
    for horizon in sorted({r["horizonSeconds"] for r in rows}):
        ordered = sorted(
            (r for r in rows if r["horizonSeconds"] == horizon),
            key=lambda r: (-abs(r["realizedRevisionSeconds"]), r["predictionId"]),
        )
        kept, runs = [], set()
        for r in ordered:
            if r["tripRunId"] not in runs:
                runs.add(r["tripRunId"])
                kept.append(r)
        out[str(horizon)] = [{"rank": i, **r} for i, r in enumerate(kept[:per_horizon], 1)]
    return out


# The network schematic: an original octilinear grid, one cell per station along each
# line, in the station order of the GTFS route sequences (straight runs and 45-degree
# bends; north up). Columns run east, rows south. Every served station must have a cell.
SCHEMATIC_GRID: dict[str, tuple[float, float]] = {
    # Richmond line, north to MacArthur
    "RICH": (5, 0),
    "DELN": (6, 1),
    "PLZA": (7, 2),
    "NBRK": (8, 3),
    "DBRK": (9, 4),
    "ASHB": (10, 5),
    "MCAR": (11, 6),
    # Antioch line, east from MacArthur
    "ROCK": (12, 5),
    "ORIN": (13, 4),
    "LAFY": (15, 4),
    "WCRK": (17, 4),
    "PHIL": (18, 3),
    "CONC": (19, 2),
    "NCON": (20, 1),
    "PITT": (21, 0),
    "PCTR": (23, 0),
    "ANTC": (25, 0),
    # Oakland core
    "19TH": (11, 7),
    "12TH": (11, 8),
    "WOAK": (10, 9),
    "LAKE": (12, 9),
    # San Francisco and the Peninsula
    "EMBR": (7, 9),
    "MONT": (6, 10),
    "POWL": (5, 11),
    "CIVC": (4, 12),
    "16TH": (4, 13),
    "24TH": (4, 14),
    "GLEN": (4, 15),
    "BALB": (4, 16),
    "DALY": (4, 17),
    "COLM": (4, 18),
    "SSAN": (4, 19),
    "SBRN": (4, 20),
    "SFIA": (5, 21),
    "MLBR": (4, 22),
    # Fremont and Berryessa
    "FTVL": (13, 10),
    "COLS": (14, 11),
    "SANL": (15, 12),
    "BAYF": (16, 13),
    "HAYW": (16, 14),
    "SHAY": (16, 15),
    "UCTY": (16, 16),
    "FRMT": (16, 17),
    "WARM": (16, 18),
    "MLPT": (16, 19),
    "BERY": (16, 20),
    # Dublin/Pleasanton and Oakland Airport
    "CAST": (17, 12),
    "WDUB": (18, 11),
    "DUBL": (19, 10),
    "OAKL": (12, 11),
}
MAP_CELL = 44
MAP_MARGIN_LEFT, MAP_MARGIN_RIGHT, MAP_MARGIN_Y = 40, 110, 40


def schematic_xy(
    station_ids, grid: dict[str, tuple[float, float]] = SCHEMATIC_GRID
) -> tuple[dict[str, tuple[float, float]], tuple[int, int]]:
    """Each station's position on the schematic grid, scaled into a viewBox, and its size."""
    missing = sorted(set(station_ids) - grid.keys())
    if missing:
        raise ShowcaseError(f"stations without a schematic position: {missing}")
    cells = {s: grid[s] for s in station_ids}
    c0 = min(c for c, _ in cells.values())
    r0 = min(r for _, r in cells.values())
    xy = {
        s: (MAP_MARGIN_LEFT + (c - c0) * MAP_CELL, MAP_MARGIN_Y + (r - r0) * MAP_CELL)
        for s, (c, r) in cells.items()
    }
    width = int(max(x for x, _ in xy.values()) + MAP_MARGIN_RIGHT)
    height = int(max(y for _, y in xy.values()) + MAP_MARGIN_Y)
    return xy, (width, height)


def network_routes(con: duckdb.DuckDBPyConnection, service_date: date) -> list[dict]:
    """Each rail route's longest station sequence on the service date, from GTFS."""
    rows = con.execute(
        """
        WITH day_trips AS (
            SELECT t.trip_id, t.route_id
            FROM wh.static_trips t
            JOIN wh.static_service_days d ON d.service_id = t.service_id AND d.service_date = ?
            JOIN wh.static_routes r ON r.route_id = t.route_id AND r.route_type = 1
        ),
        seqs AS (
            SELECT dt.route_id, dt.trip_id,
                   list(s.parent_station ORDER BY st.stop_sequence) AS stations
            FROM day_trips dt
            JOIN wh.static_stop_times st ON st.trip_id = dt.trip_id
            JOIN wh.static_stops s ON s.stop_id = st.stop_id AND s.parent_station IS NOT NULL
            GROUP BY ALL
        ),
        longest AS (
            SELECT *, row_number() OVER (
                PARTITION BY route_id ORDER BY len(stations) DESC, trip_id) AS k
            FROM seqs
        )
        SELECT r.route_id, r.route_short_name, r.route_long_name, r.route_color, q.stations
        FROM longest q JOIN wh.static_routes r USING (route_id)
        WHERE q.k = 1
        ORDER BY r.route_short_name, r.route_id
        """,
        [service_date],
    ).fetchall()
    out = []
    for route_id, short, long_name, color, stations in rows:
        # A station listed twice in a row (SFO's arrive-and-reverse) is drawn once.
        ordered = [s for i, s in enumerate(stations) if i == 0 or s != stations[i - 1]]
        out.append(
            {
                "routeId": route_id,
                "routeShortName": short,
                "routeLongName": long_name,
                "color": f"#{color.upper()}" if color else None,
                "stationIds": ordered,
            }
        )
    return out


def _median(values: list[int]) -> float | None:
    return float(statistics.median(values)) if values else None


def _record_summary(r: dict) -> dict:
    return {
        "predictionId": r["predictionId"],
        "boardingGroupId": r["boardingGroupId"],
        "destination": r["destination"],
        "lineName": r["lineName"],
        "routeShortName": r["routeShortName"],
        "horizonSeconds": r["horizonSeconds"],
        "predictedRevisionSeconds": r["predictedRevisionSeconds"],
        "realizedRevisionSeconds": r["realizedRevisionSeconds"],
    }


def network_map(
    con: duckdb.DuckDBPyConnection,
    service_date: date,
    rows: list[dict],
    station_list: list[dict],
    grid: dict[str, tuple[float, float]] = SCHEMATIC_GRID,
) -> dict:
    """Every station served that day, with its forecasts at the replay moment (or none)."""
    routes = network_routes(con, service_date)
    served = {s["id"] for s in station_list} | {s for r in routes for s in r["stationIds"]}
    coords = {
        sid: (lat, lon)
        for sid, lat, lon in con.execute(
            "SELECT stop_id, stop_lat, stop_lon FROM wh.static_stops WHERE location_type = 1"
        ).fetchall()
        if sid in served
    }
    names = dict(
        con.execute(
            "SELECT stop_id, stop_name FROM wh.static_stops WHERE location_type = 1"
        ).fetchall()
    )
    xy, (map_width, map_height) = schematic_xy(sorted(coords), grid)
    by_station: dict[str, list[dict]] = {}
    for r in rows:
        by_station.setdefault(r["stationId"], []).append(r)
    stations = []
    for sid in sorted(coords):
        recs = by_station.get(sid, [])
        connecting = sorted({r["routeShortName"] for r in routes if sid in r["stationIds"]})
        entry = {
            "stationId": sid,
            "stationName": names.get(sid) or sid,
            "lat": coords[sid][0],
            "lon": coords[sid][1],
            "x": xy[sid][0],
            "y": xy[sid][1],
            "routes": connecting,
            "supportedForecastCount": len(recs),
            "largestAbsPredictedRevisionSeconds": None,
            "medianPredictedRevisionSeconds": None,
            "largestAbsRealizedRevisionSeconds": None,
            "medianRealizedRevisionSeconds": None,
            "largestPredictedRecord": None,
            "largestRealizedRecord": None,
        }
        if recs:
            by_pred = min(
                recs, key=lambda r: (-abs(r["predictedRevisionSeconds"]), r["predictionId"])
            )
            by_real = min(
                recs, key=lambda r: (-abs(r["realizedRevisionSeconds"]), r["predictionId"])
            )
            entry |= {
                "largestAbsPredictedRevisionSeconds": abs(by_pred["predictedRevisionSeconds"]),
                "medianPredictedRevisionSeconds": _median(
                    [r["predictedRevisionSeconds"] for r in recs]
                ),
                "largestAbsRealizedRevisionSeconds": abs(by_real["realizedRevisionSeconds"]),
                "medianRealizedRevisionSeconds": _median(
                    [r["realizedRevisionSeconds"] for r in recs]
                ),
                "largestPredictedRecord": _record_summary(by_pred),
                "largestRealizedRecord": _record_summary(by_real),
            }
        stations.append(entry)
    return {
        "viewBox": [0, 0, map_width, map_height],
        "projection": (
            "Original octilinear schematic: one grid cell per station, in the station order "
            "of the GTFS route sequences, north up. lat and lon are the GTFS coordinates. "
            "Not BART's map artwork."
        ),
        "routes": routes,
        "stations": stations,
        # One record per kept train, so the map can be read line by line.
        "trains": [
            {
                "predictionId": r["predictionId"],
                "stationId": r["stationId"],
                "boardingGroupId": r["boardingGroupId"],
                "lineName": r["lineName"],
                "routeShortName": r["routeShortName"],
                "destination": r["destination"],
                "horizonSeconds": r["horizonSeconds"],
                "predictedRevisionSeconds": r["predictedRevisionSeconds"],
                "realizedRevisionSeconds": r["realizedRevisionSeconds"],
            }
            for r in sorted(rows, key=lambda r: r["predictionId"])
        ],
    }


# -- the build ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Showcase:
    out_root: Path
    selected: Candidate
    summary: dict


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=1).encode() + b"\n"


def pinned_predictor(config: LocalApiConfig, spec: ExportSpec) -> Predictor:
    """The pinned bundle, on the pinned warehouse; anything else is refused."""
    digest = sha256_file(config.warehouse)
    if digest != spec.warehouse_sha256:
        raise ExportError(f"warehouse SHA-256 {digest} is not the pinned {spec.warehouse_sha256}")
    predictor = load_predictor(config.bundle, spec.bundle_id)
    version = predictor.metadata["model"]["version"]
    if version != spec.model_version:
        raise ExportError(f"model {version} is not {spec.model_version}")
    return predictor


def select_moment(
    config: LocalApiConfig,
    spec: ExportSpec,
    service_date: date = SHOWCASE_DATE,
    top: int = TOP_CANDIDATES,
    log=print,
) -> tuple[list[Candidate], dict]:
    """The `top` snapshots of the service day by coverage, best first, and the scan."""
    warehouse = config.warehouse
    predictor = pinned_predictor(config, spec)
    meta = predictor.metadata
    buckets = meta["domain"]["published_horizon_buckets_s"]
    tolerance = meta["domain"]["horizon_tolerance_s"]

    # Each snapshot is seen by the replay engine only as of that snapshot.
    con = duckdb.connect(str(warehouse), read_only=True)
    con.execute("SET TimeZone = 'UTC'")
    try:
        snaps = day_snapshots(con, service_date)
        bounds = upper_bounds(con, snaps, buckets, tolerance)
    finally:
        con.close()
    if not snaps:
        raise ShowcaseError(f"no snapshots on {service_date}")
    cutoff = datetime.fromisoformat(meta["training_data"]["calibration_data_cutoff_utc"])
    if snaps[0].collected_at < cutoff:
        raise ShowcaseError(f"{service_date} starts before the model's calibration cutoff")
    started = time.monotonic()

    def score(snap: Snapshot, bound: int) -> Candidate:
        c = evaluate(snapshot_trains(warehouse, snap, predictor, config), snap, bound)
        log(f"  {iso(snap.collected_at)}: bound {bound}, supported {c.supported}")
        return c

    ranked, scan = rank_snapshots(bounds, score, top)
    scan["secondsElapsed"] = round(time.monotonic() - started, 1)
    return ranked, scan


def candidate_at(config: LocalApiConfig, spec: ExportSpec, snapshot: Snapshot) -> Candidate:
    """One snapshot's coverage, evaluated exactly (for a pinned moment)."""
    predictor = pinned_predictor(config, spec)
    domain = predictor.metadata["domain"]
    con = duckdb.connect(str(config.warehouse), read_only=True)
    con.execute("SET TimeZone = 'UTC'")
    try:
        bound = upper_bounds(
            con, [snapshot], domain["published_horizon_buckets_s"], domain["horizon_tolerance_s"]
        )[snapshot]
    finally:
        con.close()
    return evaluate(snapshot_trains(config.warehouse, snapshot, predictor, config), snapshot, bound)


def build_showcase(
    config: LocalApiConfig,
    spec: ExportSpec,
    out_root: Path,
    service_date: date = SHOWCASE_DATE,
    top: int = TOP_CANDIDATES,
    log=print,
) -> Showcase:
    """Select the moment, then export the curated replay and every showcase file."""
    if out_root.exists():
        raise FileExistsError(f"{out_root} exists; choose another --out")
    ranked, scan = select_moment(config, spec, service_date, top, log)
    return export_moment(config, spec, ranked[0], out_root, ranked, scan)


def export_moment(
    config: LocalApiConfig,
    spec: ExportSpec,
    selected: Candidate,
    out_root: Path,
    ranked: list[Candidate] | None = None,
    scan: dict | None = None,
    grid: dict[str, tuple[float, float]] = SCHEMATIC_GRID,
) -> Showcase:
    """The curated replay at one snapshot, its showcase files and the review files."""
    if out_root.exists():
        raise FileExistsError(f"{out_root} exists; choose another --out")
    warehouse = config.warehouse
    pinned_predictor(config, spec)
    ranked = ranked or [selected]
    scan = scan or {
        "rule": "A pinned snapshot, not selected by the coverage ranking.",
        "snapshotsOnServiceDay": 1,
    }

    # The replay at the selected snapshot, through the pinned local API.
    as_of = selected.collected_at
    cfg = replace(config, as_of=as_of)
    spec = replace(spec, as_of=as_of, source_feed_timestamp=selected.feed_timestamp)
    state, app = load_replay(cfg, spec)
    answers = asyncio.run(_ask_everything(app))
    trains = full_trains(answers)
    ok = [t for t in trains if t["predictionStatus"] == "ok"]
    feed = selected.feed_timestamp

    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    con.execute(f"ATTACH '{str(warehouse.resolve())}' AS wh (READ_ONLY)")
    try:
        finals = final_published_etas(con, sorted({event_id_of(t) for t in ok}))
        outcomes, dropped = {}, Counter()
        for t in ok:
            f = finals.get(event_id_of(t))
            if f is None or f["final"] is None:
                dropped[(f or {}).get("reason") or "no_proxy_event"] += 1
                continue
            if f["stop_id"] != t["stopId"]:
                raise ShowcaseError(f"{t['predictionId']}: the warehouse event is another stop")
            if f["known_at"] <= as_of:
                raise ShowcaseError(f"{t['predictionId']}: final ETA known before the replay time")
            outcomes[t["predictionId"]] = retrospective_record(t, f["final"], f["known_at"], feed)
        keep = set(outcomes)
        if not keep:
            raise ShowcaseError(f"no supported train has a final published ETA: {dict(dropped)}")
        curated = curate(answers, keep)
        files = render(curated, spec)
        manifest = build_manifest(curated, files, state, cfg, spec)
        kept_trains = [t for t in ok if t["predictionId"] in keep]
        rows = [change_row(t, outcomes[t["predictionId"]], spec.model_version) for t in kept_trains]
        # The map shows every station served that day; those without a kept train are grey.
        all_stations = next(a.body for a in answers if a.file == "stations.json")
        map_data = network_map(con, state.engine.service_date, rows, all_stations, grid)
    finally:
        con.close()
    if any(
        t["predictionStatus"] != "ok"
        for a in curated
        if a.file.startswith("boards/")
        for t in a.body["trains"]
    ):
        raise ShowcaseError("a curated board lists an unsupported train")

    # 3. Write: the curated replay (publishable as web/public/replay), the showcase files
    # (web/public/showcase) and the review files (never published).
    tmp = out_root.with_name(f".{out_root.name}.building")
    shutil.rmtree(tmp, ignore_errors=True)
    replay_root = tmp / "replay"
    export_dir = replay_root / spec.name
    try:
        for rel, data in files.items():
            (export_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            (export_dir / rel).write_bytes(data)
        (export_dir / MANIFEST).write_bytes(encode_manifest(manifest))
        (replay_root / "index.json").write_bytes(encode(build_index(export_dir)) + b"\n")
        offline = check_public(replay_root)
        manifest_sha = offline["manifestSha256"]

        local = as_of.astimezone(PACIFIC)
        provenance = {
            "modelVersion": spec.model_version,
            "bundleId": spec.bundle_id,
            "warehouseSha256": spec.warehouse_sha256,
            "replayExport": spec.name,
            "replayManifestSha256": manifest_sha,
        }
        common = {
            "dataMode": "historical_replay",
            "asOf": iso(as_of),
            "feedTimestamp": iso(feed),
            "serviceDate": str(state.engine.service_date),
            "modelVersion": spec.model_version,
        }
        retrospective = {
            "schemaVersion": SCHEMA_VERSIONS["retrospective"],
            **common,
            "notice": RETROSPECTIVE_NOTICE,
            "records": [outcomes[t["predictionId"]] for t in kept_trains],
        }
        changes = {
            "schemaVersion": SCHEMA_VERSIONS["largest_changes"],
            **common,
            "title": "Largest ETA changes in this replay",
            "notice": (
                "Ranked by the realized ETA revision: the final published ETA minus BART's "
                "published ETA at the replay moment. These are revisions to BART's ETA, not "
                "train delays. " + RETROSPECTIVE_NOTICE
            ),
            "rankedBy": "absolute realized ETA revision; ties by predictionId",
            "perHorizonLimit": LARGEST_PER_HORIZON,
            "deduplicatedBy": "trip run, within each horizon",
            "byHorizon": largest_changes(rows),
        }
        network = {
            "schemaVersion": SCHEMA_VERSIONS["network_map"],
            **common,
            "notice": (
                "An original schematic built from GTFS. Stations are colored by how BART's "
                "published ETA was revised: 'ETA moved later' or 'ETA moved earlier'."
            ),
            **map_data,
        }
        public = {
            "retrospective.json": _json(retrospective),
            "largest-changes.json": _json(changes),
            "network-map.json": _json(network),
        }
        excluded = sum(dropped.values())
        showcase = {
            "schemaVersion": SCHEMA_VERSIONS["showcase"],
            **common,
            "title": "ETA Reliability: historical replay",
            "localTime": local.strftime("%A, %B %-d, %Y, %-I:%M %p %Z"),
            "notLive": "A fixed historical replay of recorded BART data. It is not live.",
            "disclosure": DISCLOSURE,
            "modelScope": NOT_PHYSICAL,
            "terms": TERMS,
            "selection": {
                "rule": scan["rule"],
                "serviceDate": str(state.engine.service_date),
                "candidatesConsidered": scan["snapshotsOnServiceDay"],
                "selected": selected.describe(),
            },
            "counts": {
                "boardEntries": len(trains),
                "supportedForecasts": len(ok),
                "includedRecords": len(keep),
                "excludedSupportedWithoutFinalEta": excluded,
                "excludedSupportedByReason": dict(sorted(dropped.items())),
                "notSupportedByStatus": dict(
                    sorted(
                        Counter(
                            t["predictionStatus"] for t in trains if t["predictionStatus"] != "ok"
                        ).items()
                    )
                ),
                "stationsRepresented": len({r["stationId"] for r in rows}),
                "stationsOnMap": len(network["stations"]),
                "tripRuns": len({r["tripRunId"] for r in rows}),
                "recordsByHorizon": {
                    str(h): n for h, n in sorted(Counter(r["horizonSeconds"] for r in rows).items())
                },
            },
            "provenance": provenance,
            "files": {name: {"bytes": len(b), "sha256": _sha(b)} for name, b in public.items()},
        }
        showcase_dir = tmp / "showcase"
        showcase_dir.mkdir(parents=True)
        for name, data in public.items():
            (showcase_dir / name).write_bytes(data)
        (showcase_dir / "showcase.json").write_bytes(_json(showcase))

        review = tmp / "review"
        review.mkdir()
        (review / "candidates.json").write_bytes(
            _json({"scan": scan, "top": [c.describe() for c in ranked]})
        )
        (review / "coverage.json").write_bytes(
            _json(
                {
                    "counts": showcase["counts"],
                    "offlineCheck": offline,
                    "statusOfEveryBoardEntry": dict(
                        sorted(Counter(t["predictionStatus"] for t in trains).items())
                    ),
                }
            )
        )
        with open(review / "included_records.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["predictionId"])
            w.writeheader()
            w.writerows(rows)
        tmp.rename(out_root)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return Showcase(out_root, selected, {"scan": scan, "counts": showcase["counts"]})


def publish_showcase(out_root: Path, public: Path = Path("web/public")) -> dict:
    """Copy a built showcase into the website: the curated replay to <public>/replay (through
    the existing publish and offline check) and the showcase files to <public>/showcase,
    which must then pass check_showcase."""
    index = json.loads((out_root / "replay" / "index.json").read_bytes())
    replay_summary = publish(out_root / "replay" / index["export"], public / "replay")
    target = public / "showcase"
    tmp = target.with_name(f".{target.name}.building")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(out_root / "showcase", tmp)
    try:
        check_showcase(tmp, public / "replay")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    old = target.with_name(f".{target.name}.old")
    shutil.rmtree(old, ignore_errors=True)
    if target.exists():
        target.rename(old)
    tmp.rename(target)
    shutil.rmtree(old, ignore_errors=True)
    return {"replay": replay_summary, "showcase": check_showcase(target, public / "replay")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="select the moment and write the showcase to --out")
    build.add_argument("--spec", type=Path, default=DEFAULT_SPEC_PATH)
    build.add_argument("--api-config", type=Path, default=DEFAULT_API_CONFIG_PATH)
    pub = sub.add_parser("publish", help="copy a built showcase into web/public")
    pub.add_argument("--public", type=Path, default=Path("web/public"))
    for p in (build, pub):
        p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    if args.command == "publish":
        print(json.dumps(publish_showcase(args.out, args.public), indent=1))
        return 0
    spec = load_export_spec(args.spec)
    config = load_api_config(args.api_config)
    result = build_showcase(config, spec, args.out, log=lambda m: print(m, file=sys.stderr))
    summary = {
        "out": str(result.out_root),
        "selected": result.selected.describe(),
        **result.summary,
    }
    print(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
