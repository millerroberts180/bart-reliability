# BART Reliability Lab

How stable are BART's published arrival estimates (ETAs), and where and when are they
most likely to be revised as a train approaches? See [PROJECT_SPEC.md](PROJECT_SPEC.md)
for the full plan.

This project measures **ETA revision**, not arrival accuracy. BART publishes no
independent vehicle-location or actual-arrival feed, so revisions are measured against
BART's own final stable published estimate (`observed_arrival_proxy`). That reference is
circular, and it is never presented as an observed arrival. Evaluating physical accuracy
would need an independent AVL or actual-arrival source, which BART does not publish.
The 511 regional stop observations are not one: see
[docs/511_arrival_feasibility.md](docs/511_arrival_feasibility.md).

## Pipeline so far

```text
BART GTFS-RT feeds --bart-collect--> data/raw/gtfs_rt/<feed>/<date>/<HHMMSS>Z.pb
                   --bart-transform--> data/processed/trip_updates/date=…/hour=…/part.parquet
                                       data/processed/alert_*/ (normalized alerts)
static GTFS ZIP + Parquet --bart-build-warehouse--> data/warehouse/bart.duckdb
warehouse (read-only) --bart-eta-model--> data/models/eta_revision/ (features, models, metrics)
warehouse (read-only) --bart-eta-bundle build--> data/models/eta_revision_bundle_<date>/ (inference bundle)
warehouse + bundle --bart-serve-local--> http://127.0.0.1:8000/api/v1 (historical replay, local only)
local API answers --bart-static-replay--> data/static_replay/v1-<as_of>/ (static replay files)
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
- **Service alerts** (`transform/alerts.py`, `warehouse/alerts.py`): normalized alert
  versions, active periods, and informed entities; when each alert was **visible in the
  feed**; and one alert-context row per ETA-revision example using only alerts published
  by the prediction's publication time. A visible alert is not evidence of an operational
  disruption (that needs a structured active period, which BART does not supply), and
  planned/incident categories come from a manual annotation file
  (`config/alert_annotations.csv`): [docs/service_alerts.md](docs/service_alerts.md).
- **ETA revision models** (`src/bart_reliability/modeling/`): point-in-time features in
  DuckDB SQL; examples at 5/10/15-minute published-time horizons (what BART's ETA said
  at the snapshot); a chronological service-date split; and no-revision and historical
  baselines. The models are a robust linear (Huber) comparator and gradient-boosted
  trees, selected on validation and never refitted on it. They predict the revision and
  revisions over 60 s, with structural leakage checks and a paired, trip-clustered
  bootstrap for test-day uncertainty. Settings live in `config/eta_model.toml`. Current results are
  provisional: [docs/modeling_plan.md](docs/modeling_plan.md). The preregistered
  evaluation on the sealed test day 2026-10-19 is in
  [docs/eta_model_evaluation_2026-10-20.md](docs/eta_model_evaluation_2026-10-20.md).
- **Inference bundle** (`src/bart_reliability/serving/`): the selected models exported with
  verified metadata, one strict single-record entry point, exact parity with the
  modeling pipeline, and a provisional horizon-aware revision interval. Inputs with a
  category unseen in training return `fallback_required` (use BART's published ETA). It is rebuilt
  with `bart-eta-bundle build`; settings live in `config/eta_model_bundle.toml` and the
  committed metadata schema `config/eta_model_bundle.schema.json`:
  [docs/model_serving.md](docs/model_serving.md).
- **Local prediction API** (`src/bart_reliability/api/`): FastAPI in historical-replay
  mode, answering as of a configured past moment with features, history and alerts cut
  off at that moment, through the website's `PredictionClient` contract. It binds to
  127.0.0.1 with localhost-only CORS. Boards are grouped by boarding group, the way a
  train leaves the station, built from the schedule's platforms rather than GTFS
  `direction_id`: [docs/boarding_groups.md](docs/boarding_groups.md). By default it
  replays 2026-10-20 10:00 AM Pacific with model `0.2.0+886fcd260732`. The website can
  read it locally (below): [docs/local_api.md](docs/local_api.md).
- **Static replay export** (`src/bart_reliability/static_replay/`): the local API's
  answers at that fixed moment, one compact JSON file per request the website can make,
  reduced to the fields the site reads. It has a manifest of hashes and provenance, is
  deterministic and atomic, and is verified file by file against a freshly loaded API.
  It is a fixed historical replay, never live data. The website does not read it yet,
  and the generated export is ignored by Git: [docs/static_replay.md](docs/static_replay.md).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pip install -e '.[dev,model]'   # also pandas and scikit-learn, for bart-eta-model
.venv/bin/pip install -e '.[dev,model,serve]'   # also FastAPI and uvicorn, for bart-serve-local
```

## Usage

Run from the repository root.

```bash
.venv/bin/bart-collect            # poll forever (Ctrl+C to stop)
.venv/bin/bart-collect --once     # one cycle
.venv/bin/bart-transform          # raw trip-update and alert snapshots -> Parquet (safe to rerun)
.venv/bin/bart-build-warehouse    # static GTFS + Parquet -> DuckDB (safe to rerun)
.venv/bin/bart-eta-sensitivity    # ETA revision parameter sensitivity (read-only)
.venv/bin/bart-alert-sensitivity  # alert-state staleness sensitivity (read-only)
.venv/bin/bart-eta-model          # features, baselines, models, metrics (warehouse read-only)
.venv/bin/bart-eta-bundle build   # rebuild the inference bundle (runs bart-eta-model first)
.venv/bin/bart-eta-bundle build --from-run data/models/<run>   # package a frozen run, no refit
.venv/bin/bart-eta-bundle predict --record record.json   # one prediction from the bundle
.venv/bin/bart-serve-local --warehouse data/warehouse/<snapshot>.duckdb   # local replay API
.venv/bin/bart-static-replay export   # static replay files (config/static_replay.toml)
.venv/bin/bart-static-replay verify   # re-check them against a freshly loaded API
```

Query the warehouse with DuckDB, e.g.
`SELECT * FROM rt_join_quality` or
`SELECT * FROM rt_predictions_enriched WHERE include_in_primary_metrics`.

To run the collector continuously on a server with systemd, see
[docs/deployment.md](docs/deployment.md). The 24-hour production test is in
[docs/collection_validation.md](docs/collection_validation.md), and the 10.5-day data
checkpoint (to 2026-10-20) in [docs/data_checkpoint_2026-10-20.md](docs/data_checkpoint_2026-10-20.md).

Collector logs are JSON lines on stdout and in `logs/collector.log`. Malformed inputs
found by the transformer are listed in `data/processed/trip_updates/_quarantine.jsonl`.

## Website prototype

**Live demo (simulated data): <https://millerroberts180.github.io/bart-reliability/>**

The demo is the simulated build. `.github/workflows/deploy-pages.yml` builds it with
`VITE_DATA_MODE=mock` on every push to `main` and publishes it to GitHub Pages. Every
value it shows is simulated and nothing is live. The historical-replay API is not deployed.

`web/` holds a React + TypeScript prototype of the public site, "ETA Reliability". By
default it runs on simulated data. Stack, data contracts, the mock client and the HTTP
client are described in [docs/website_architecture.md](docs/website_architecture.md).

```bash
cd web
npm install
npm run dev      # http://localhost:5173/ (simulated data)
npm run test && npm run lint && npm run build
```

To run it against the local historical-replay API, set the API address once in the
ignored `web/.env.local`:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

then start two processes from the repository root, each in its own terminal:

```bash
.venv/bin/bart-serve-local                     # API: http://127.0.0.1:8000 (config/local_api.toml)
cd web && VITE_DATA_MODE=http npm run dev       # site: http://localhost:5173/
```

Every value the site then shows is labelled as a historical replay of recorded BART data
as of the API's replay time. Nothing is live.

## Checks

```bash
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

## Data

Nothing under `data/` should be committed. Raw snapshots are never modified by later
steps.
