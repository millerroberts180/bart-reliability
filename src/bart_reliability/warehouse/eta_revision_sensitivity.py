"""Sensitivity of the ETA revision findings to the dataset's parameters.

Each scenario changes one parameter from the configured defaults and rebuilds the
dataset in memory from a read-only copy of the warehouse, so the warehouse itself is
never modified. The purpose is to check whether headline findings are robust, not to
pick parameters that make the numbers look better.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb

from bart_reliability.collector.logging_setup import configure_logging
from bart_reliability.warehouse.eta_revision import (
    build_eta_revision_dataset,
    drop_eta_revision_dataset,
)
from bart_reliability.warehouse.eta_revision_config import (
    DEFAULT_CONFIG_PATH,
    ETARevisionConfig,
    load_eta_revision_config,
)

logger = logging.getLogger(__name__)

# Inputs the dataset reads from the warehouse.
_INPUTS = ["rt_predictions_enriched", "rt_feed_snapshots", "static_stop_times"]


@dataclass(frozen=True)
class Scenario:
    name: str
    parameter: str
    overrides: dict


def default_scenarios(base: ETARevisionConfig) -> list[Scenario]:
    """One-at-a-time variations around `base`, including `base` itself."""
    lo, hi = base.tier_a_persistence_s
    variants = {
        "max_collection_gap_s": [75, 90, 120],
        "stable_spread_s": [30, 60, 90],
        "horizon_tolerance_s": [30, 60, 90],
        "tier_a_persistence_s": [(-30, 60), (lo, hi), (-120, 300)],
    }
    scenarios = [Scenario("default", "default", {})]
    for parameter, values in variants.items():
        for value in values:
            if value == getattr(base, parameter):
                continue
            overrides = {parameter: value}
            # Tier A can't be stricter than "stable"; tighten it alongside when needed.
            if parameter == "stable_spread_s" and value < base.tier_a_spread_s:
                overrides["tier_a_spread_s"] = value
            label = value if not isinstance(value, tuple) else f"{value[0]}..{value[1]}"
            scenarios.append(Scenario(f"{parameter}={label}", parameter, overrides))
    return scenarios


def _metrics(con: duckdb.DuckDBPyConnection) -> dict:
    def rows(sql):
        return con.execute(sql).fetchall()

    eligible, tier_a = rows(
        "SELECT count(*) FILTER (WHERE is_eligible), count(*) FILTER (WHERE quality_tier = 'A') "
        "FROM observed_arrival_proxy"
    )[0]
    out = {
        "eligible_events": eligible,
        "tier_a_events": tier_a,
        "exclusions": dict(
            rows(
                "SELECT exclusion_reason, count(*) FROM observed_arrival_proxy "
                "WHERE NOT is_eligible GROUP BY 1 ORDER BY 1"
            )
        ),
        "coverage_pct": {
            t: pct
            for t, pct in rows(
                "SELECT target_horizon_s, round(100 * count(*) / nullif((SELECT count(*) "
                "FROM observed_arrival_proxy_eligible), 0), 2) "
                "FROM eta_revision_examples GROUP BY 1 ORDER BY 1"
            )
        },
    }
    for name, where in (("tier_a", "p.quality_tier = 'A'"), ("all_eligible", "p.is_eligible")):
        out[f"revision_{name}"] = {
            t: {
                "mean_eta_revision_s": mean,
                "median_absolute_eta_revision_s": median,
                "pct_within_60s": within,
            }
            for t, mean, median, within in rows(
                f"""
                SELECT target_horizon_s, round(avg(eta_revision_seconds), 1),
                       quantile_cont(absolute_eta_revision_seconds, 0.5),
                       round(100 * avg((absolute_eta_revision_seconds <= 60)::INT), 1)
                FROM eta_revision_examples h JOIN observed_arrival_proxy p USING (event_id)
                WHERE {where} GROUP BY 1 ORDER BY 1
                """
            )
        }
    out["quality_check_failures"] = sum(
        n for _, n in rows("SELECT * FROM eta_revision_quality_checks")
    )
    return out


def run_sensitivity(
    db_path: Path, base: ETARevisionConfig | None = None, scenarios: list[Scenario] | None = None
) -> list[dict]:
    """Rebuild the dataset for each scenario from a read-only warehouse; return metrics."""
    base = base or ETARevisionConfig()
    scenarios = scenarios if scenarios is not None else default_scenarios(base)
    con = duckdb.connect()
    try:
        escaped = str(db_path).replace("'", "''")
        con.execute(f"ATTACH '{escaped}' AS warehouse (READ_ONLY)")
        for name in _INPUTS:
            # Materialize inputs once, so every scenario reads identical data.
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM warehouse.{name}")
        results = []
        for scenario in scenarios:
            config = base.with_overrides(**scenario.overrides)
            build_eta_revision_dataset(con, config)
            results.append(
                {
                    "scenario": scenario.name,
                    "parameter": scenario.parameter,
                    "config": config.as_dict(),
                    **_metrics(con),
                }
            )
            drop_eta_revision_dataset(con)
        return results
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sensitivity of ETA revision findings to dataset parameters."
    )
    parser.add_argument("--db", type=Path, default=Path("data/warehouse/bart.duckdb"))
    parser.add_argument("--eta-revision-config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output", type=Path, help="write results as JSON to this file")
    args = parser.parse_args(argv)

    configure_logging(None)
    results = run_sensitivity(args.db, load_eta_revision_config(args.eta_revision_config))
    for r in results:
        logger.info("eta_revision_sensitivity", extra={"fields": r})
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
