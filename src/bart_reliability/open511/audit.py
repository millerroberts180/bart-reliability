"""Reproducible feasibility audit of 511 BART stop observations.

Inputs are the BART subset written by `extract_bart_subset` (all-string Parquet) and the
project warehouse (BART's direct static GTFS). Every number in
docs/511_arrival_feasibility.md comes from `audit()`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from bart_reliability.open511.extract import extract_subset

MEMBERS = {
    # member: (column, kind, value)
    "stop_observations.txt": ("agency_id", "equals", "BA"),
    "routes.txt": ("agency_id", "equals", "BA"),
    "trips.txt": ("route_id", "prefix", "BA:"),
    "stop_times.txt": ("trip_id", "prefix", "BA:"),
    "calendar_dates.txt": ("service_id", "prefix", "BA:"),
}


def extract_bart_subset(zip_path: Path, out_dir: Path) -> dict[str, int]:
    """Write BART's rows of each regional file to out_dir/<name>.parquet."""
    counts = {}
    for member, (column, kind, value) in MEMBERS.items():
        name = member.removesuffix(".txt")
        counts[name] = extract_subset(
            zip_path, member, out_dir / f"{name}.parquet", column, **{kind: value}
        )
    return counts


def _secs(col: str) -> str:
    return (
        f"(CAST(split_part({col}, ':', 1) AS INT) * 3600 "
        f"+ CAST(split_part({col}, ':', 2) AS INT) * 60 "
        f"+ CAST(split_part({col}, ':', 3) AS INT))"
    )


def audit(bart_dir: Path, warehouse_db: Path, month: tuple[str, str]) -> dict:
    """Compute coverage, identifier match rates, integrity, and the usable subset."""
    first, last = month
    c = duckdb.connect()
    c.execute(f"ATTACH '{warehouse_db}' AS wh (READ_ONLY)")
    for name in ("stop_observations", "trips", "stop_times", "routes", "calendar_dates"):
        c.execute(f"CREATE VIEW rg_{name} AS SELECT * FROM '{bart_dir / name}.parquet'")
    c.execute(f"""
        CREATE TEMP TABLE obs AS
        SELECT o.*, CAST(stop_sequence AS INT) AS seq,
               regexp_extract(trip_id, '^BA:([^:]+)', 1) AS bart_trip_id,
               {_secs("observed_arrival_time")} AS obs_s,
               {_secs("scheduled_arrival_time")} AS sch_s
        FROM rg_stop_observations o
    """)
    c.execute("""
        CREATE TEMP TABLE pos AS
        SELECT trip_id, stop_sequence, stop_id,
               row_number() OVER (PARTITION BY trip_id ORDER BY stop_sequence) AS p
        FROM wh.static_stop_times
    """)
    c.execute("""
        CREATE TEMP TABLE per_trip AS
        SELECT service_date, trip_id, count(*) AS n FROM obs
        WHERE schedule_relationship = '0' AND obs_s IS NOT NULL GROUP BY ALL
    """)
    c.execute("""
        CREATE TEMP TABLE usable AS
        SELECT o.* FROM obs o
        JOIN per_trip t USING (service_date, trip_id)
        JOIN pos ON pos.trip_id = o.bart_trip_id AND pos.stop_sequence = o.seq
        WHERE o.schedule_relationship = '0' AND o.obs_s IS NOT NULL AND t.n > 1 AND pos.p > 1
    """)

    def one(sql):
        cur = c.execute(sql)
        return dict(zip([d[0] for d in cur.description], cur.fetchone(), strict=True))

    def pairs(sql):
        return {str(k): v for k, v in c.execute(sql).fetchall()}

    sched_window = f"cd.exception_type = '1' AND cd.date BETWEEN '{first}' AND '{last}'"
    result = {
        "rows": one("""
            SELECT count(*) AS rows, count(observed_arrival_time) AS with_arrival,
                   count(observed_departure_time) AS with_departure,
                   count(*) FILTER (WHERE observed_arrival_time = observed_departure_time)
                       AS arrival_equals_departure,
                   min(service_date) AS first_date, max(service_date) AS last_date,
                   count(DISTINCT service_date) AS dates,
                   count(DISTINCT to_stop_id) AS stops, count(DISTINCT trip_id) AS trip_ids
            FROM obs
        """),
        "schedule_relationship": pairs(
            "SELECT schedule_relationship, count(*) FROM obs GROUP BY 1 ORDER BY 1"
        ),
        "vehicle_id": pairs("SELECT vehicle_id, count(*) FROM obs GROUP BY 1 ORDER BY 2 DESC"),
        "uncertainty": pairs("SELECT uncertainty, count(*) FROM obs GROUP BY 1 ORDER BY 2 DESC"),
        "matching": one("""
            SELECT count(*) AS rows,
                   count(*) FILTER (WHERE t.trip_id = o.trip_id) AS trip_exact,
                   count(*) FILTER (WHERE b.trip_id IS NOT NULL) AS trip_normalized,
                   count(*) FILTER (WHERE s.stop_code = o.to_stop_id) AS stop_via_stop_code,
                   count(*) FILTER (WHERE st.trip_id IS NOT NULL) AS scheduled_stop_time,
                   count(*) FILTER (WHERE st.trip_id IS NOT NULL
                                    AND s2.stop_code = o.to_stop_id) AS stop_time_and_stop_agree
            FROM obs o
            LEFT JOIN wh.static_trips t ON t.trip_id = o.trip_id
            LEFT JOIN wh.static_trips b ON b.trip_id = o.bart_trip_id
            LEFT JOIN wh.static_stops s ON s.stop_code = o.to_stop_id
            LEFT JOIN wh.static_stop_times st
              ON st.trip_id = o.bart_trip_id AND st.stop_sequence = o.seq
            LEFT JOIN wh.static_stops s2 ON s2.stop_id = st.stop_id
        """),
        "regional_schedule_vs_bart": one("""
            SELECT count(*) AS regional_stop_times,
                   count(*) FILTER (WHERE b.arrival_time = r.arrival_time
                                    AND b.departure_time = r.departure_time
                                    AND s.stop_code = r.stop_id) AS identical
            FROM rg_stop_times r
            LEFT JOIN wh.static_stop_times b
              ON b.trip_id = regexp_extract(r.trip_id, '^BA:([^:]+)', 1)
             AND b.stop_sequence = CAST(r.stop_sequence AS INT)
            LEFT JOIN wh.static_stops s ON s.stop_id = b.stop_id
        """),
        "coverage": one(f"""
            SELECT (SELECT count(*) FROM rg_calendar_dates cd WHERE {sched_window})
                       AS scheduled_trip_days,
                   (SELECT count(*) FROM per_trip) AS observed_trip_days,
                   (SELECT count(*) FROM per_trip WHERE n = 1) AS single_observation_trip_days,
                   (SELECT count(*) FROM rg_calendar_dates cd
                      JOIN rg_stop_times st ON st.trip_id = cd.service_id WHERE {sched_window})
                       AS scheduled_stop_events,
                   (SELECT count(*) FROM obs WHERE schedule_relationship = '0'
                       AND obs_s IS NOT NULL) AS observed_scheduled_stop_events
        """),
        "origin_artifact": one("""
            SELECT count(*) AS origin_rows,
                   quantile_cont(obs_s - sch_s, 0.5) AS median_observed_minus_scheduled_s
            FROM obs o JOIN pos ON pos.trip_id = o.bart_trip_id AND pos.stop_sequence = o.seq
            WHERE o.schedule_relationship = '0' AND o.obs_s IS NOT NULL AND pos.p = 1
        """),
        "usable": one("""
            SELECT count(*) AS rows, count(DISTINCT (service_date, trip_id)) AS trip_days,
                   count(DISTINCT to_stop_id) AS stops,
                   quantile_cont(obs_s - sch_s, [0.05, 0.25, 0.5, 0.75, 0.95])
                       AS observed_minus_scheduled_s,
                   avg((obs_s < sch_s)::INT) AS share_early,
                   avg((abs(obs_s - sch_s) <= 300)::INT) AS share_within_5_min
            FROM usable
        """),
        "usable_by_route": pairs("SELECT route_id, count(*) FROM usable GROUP BY 1 ORDER BY 1"),
        "usable_ordering": one("""
            SELECT count(*) AS consecutive_pairs,
                   count(*) FILTER (WHERE obs_s < prev) AS decreasing,
                   count(*) FILTER (WHERE obs_s = prev) AS equal
            FROM (SELECT obs_s, lag(obs_s) OVER (PARTITION BY service_date, trip_id
                                                 ORDER BY seq, obs_s) AS prev FROM usable)
            WHERE prev IS NOT NULL
        """),
        "duplicates": one("""
            SELECT count(*) AS duplicate_keys,
                   count(*) FILTER (WHERE times > 1) AS conflicting_times,
                   max(spread) AS max_spread_s
            FROM (SELECT count(DISTINCT obs_s) AS times, max(obs_s) - min(obs_s) AS spread
                  FROM obs WHERE schedule_relationship = '0'
                  GROUP BY service_date, trip_id, seq HAVING count(*) > 1)
        """),
    }
    c.close()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit 511 BART stop observations.")
    parser.add_argument("--zip", type=Path, help="extract the BART subset from this archive first")
    parser.add_argument("--bart-dir", type=Path, required=True)
    parser.add_argument("--warehouse", type=Path, default=Path("data/warehouse/bart.duckdb"))
    parser.add_argument("--first-date", required=True, help="YYYYMMDD")
    parser.add_argument("--last-date", required=True, help="YYYYMMDD")
    args = parser.parse_args(argv)
    if args.zip:
        print(json.dumps({"extracted": extract_bart_subset(args.zip, args.bart_dir)}))
    print(
        json.dumps(
            audit(args.bart_dir, args.warehouse, (args.first_date, args.last_date)),
            indent=1,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
