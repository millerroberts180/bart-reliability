# BART Reliability Lab

How accurate are BART's real-time arrival predictions, and when do they become
unreliable? See [PROJECT_SPEC.md](PROJECT_SPEC.md) for the full plan.

## Pipeline so far

```text
BART GTFS-RT feeds --bart-collect--> data/raw/gtfs_rt/<feed>/<date>/<HHMMSS>Z.pb
                   --bart-transform--> data/processed/trip_updates/date=…/hour=…/part.parquet
```

- **Collector** (`src/bart_reliability/collector/`): polls trip updates and alerts every
  60 s, validates each response with `gtfs-realtime-bindings`, and saves it atomically
  without overwriting. Settings live in `config/collector.toml`.
- **Transformer** (`src/bart_reliability/transform/`): flattens trip-update snapshots to
  one row per stop-time update and writes hourly, zstd-compressed Parquet. Reruns are
  idempotent. Schema, deduplication key, and assumptions:
  [docs/trip_updates_schema.md](docs/trip_updates_schema.md).

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
```

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
