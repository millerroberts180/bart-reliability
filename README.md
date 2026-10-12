# BART Reliability Lab

How stable are BART's published arrival estimates (ETAs), and where and when are they
most likely to be revised as a train approaches? See [PROJECT_SPEC.md](PROJECT_SPEC.md)
for the full plan.

This project measures **ETA revision**, not arrival accuracy. BART publishes no
independent vehicle-location or actual-arrival feed, so revisions are measured against
BART's own final stable published estimate (`observed_arrival_proxy`). That reference is
circular, and it is never presented as an observed arrival. Evaluating physical accuracy
would need an independent AVL or actual-arrival source, which BART does not publish.

## Pipeline so far

```text
BART GTFS-RT feeds --bart-collect--> data/raw/gtfs_rt/<feed>/<date>/<HHMMSS>Z.pb
                   --bart-transform--> data/processed/trip_updates/date=…/hour=…/part.parquet
static GTFS ZIP + Parquet --bart-build-warehouse--> data/warehouse/bart.duckdb
```

- **Collector** (`src/bart_reliability/collector/`): polls trip updates and alerts every
  60 s, validates each response with `gtfs-realtime-bindings`, and saves it atomically
  without overwriting. Settings live in `config/collector.toml`.
- **Transformer** (`src/bart_reliability/transform/`): flattens trip-update snapshots to
  one row per stop-time update and writes hourly, zstd-compressed Parquet. Reruns are
  idempotent. Schema, deduplication key, and assumptions:
  [docs/trip_updates_schema.md](docs/trip_updates_schema.md).
- **Warehouse** (`src/bart_reliability/warehouse/`): loads static GTFS from
  `data/raw/gtfs_static/<date>/google_transit.zip` into typed DuckDB tables, creates
  views over the Parquet, and joins predictions to scheduled stop times with
  calendar-resolved service dates and join-quality metrics:
  [docs/warehouse.md](docs/warehouse.md).
- **ETA revision dataset** (`src/bart_reliability/warehouse/eta_revision.py`):
  reconstructs each trip-stop's ETA history, its final stable published estimate
  (`observed_arrival_proxy`), and 5/10/15-minute revision examples
  (`eta_revision_seconds`). Parameters live in `config/eta_revision.toml`;
  `bart-eta-sensitivity` tests how findings depend on them:
  [docs/observed_arrival_proxy.md](docs/observed_arrival_proxy.md).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## Usage

Run from the repository root.

```bash
.venv/bin/bart-collect            # poll forever (Ctrl+C to stop)
.venv/bin/bart-collect --once     # one cycle
.venv/bin/bart-transform          # raw snapshots -> Parquet (safe to rerun)
.venv/bin/bart-build-warehouse    # static GTFS + Parquet -> DuckDB (safe to rerun)
.venv/bin/bart-eta-sensitivity    # ETA revision parameter sensitivity (read-only)
```

Query the warehouse with DuckDB, e.g.
`SELECT * FROM rt_join_quality` or
`SELECT * FROM rt_predictions_enriched WHERE include_in_primary_metrics`.

To run the collector continuously on a server with systemd, see
[docs/deployment.md](docs/deployment.md).

Collector logs are JSON lines on stdout and in `logs/collector.log`. Malformed inputs
found by the transformer are listed in `data/processed/trip_updates/_quarantine.jsonl`.

## Checks

```bash
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

## Data

Nothing under `data/` should be committed. Raw snapshots are never modified by later
steps.
