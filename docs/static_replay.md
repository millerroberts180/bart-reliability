# Static historical replay

`bart-static-replay export` writes the local API's answers at one fixed past moment as
static JSON files. It covers **2026-10-20 at 17:00 UTC (10:00 AM PDT)**, the local
historical replay ([local_api.md](local_api.md)). `bart-static-replay publish` copies a
verified export into the website. The public GitHub Pages site reads it there, in
`VITE_DATA_MODE=static`.

**This is a fixed historical replay of recorded BART data, not live data.** Every file
answers as of that one moment, and nothing in it changes or ticks. The website labels it
as a replay through each answer's `dataMode: "historical_replay"` and `asOf`.

**Status:** published, and served by GitHub Pages.
- **Tracked public copy:** the reviewed export is in `web/public/replay/`. It is the only
  replay data tracked by Git (see "The published replay").
- **Ignored working export:** the exporter's output in `data/static_replay/` stays
  ignored.
- **Offline check:** CI and the Pages workflow check the published copy without the
  warehouse or the bundle.

## Zero-cost architecture

```text
collector (Droplet) --> raw GTFS-RT --> Parquet --> DuckDB warehouse    offline, on this machine
                                                         |
                       model bundle --> local FastAPI replay (bart-serve-local, 127.0.0.1)
                                                         |
                      bart-static-replay export + verify (byte parity with the API)
                                                         |
                      bart-static-replay publish --> web/public/replay/   tracked in Git
                                                         |
         GitHub Actions: bart-static-replay check (offline) --> vite build (static) --> GitHub Pages
                                                         |
                                     React site in the visitor's browser: same-origin JSON files
```

Everything that needs data, a model or a database runs offline, on the developer's
machine:
- **Machine:** the pipeline, the DuckDB warehouse, the model bundle and the FastAPI service.
- **Public:** only the reduced answers are published, as static files beside the site.
- **Cost:** GitHub Pages serves them with the site, so there is no API host, server or
  database to pay for. The Droplet only collects.

| | Local FastAPI service (`bart-serve-local`) | Public static replay (`web/public/replay/`) |
|---|---|---|
| Where | 127.0.0.1 only, never deployed | GitHub Pages, with the site |
| Data | Computed on request from the warehouse and the model bundle | Precomputed answers, reduced to the fields the site reads |
| Replay time | Any configured `as_of` after the model's data | 2026-10-20 at 10:00 AM Pacific only |
| Needs | Warehouse, bundle, Python with the model and serve extras | A browser |
| Use | Development, other replay times, producing and verifying exports | The public site |

## Why a static export

- **The answers are fixed and finite.** A replay at a fixed moment always gives the same
  answer, and the website can ask only a known set of questions. They are health, model
  metadata, the station list, 95 boards and the history of each of their 1,057 trains.
  Every answer can be computed once, in advance.
- **It costs nothing to host.** Static files can be served from GitHub Pages, which
  already hosts the site.
  - There is no server, port or process to run, scale or secure.
  - The Droplet is not resized and keeps running only the collector.
- **Nothing sensitive is published.** The warehouse, the model bundle (pickled models)
  and every database stay on this machine. Only the answers are published, reduced to
  the fields the website reads.
- **Same contract.** Each file is an API response the website's existing decoder accepts.
- **The FastAPI service stays.** It remains the source of truth for local use and for
  other replay times. It also produces and verifies every export.

The cost is flexibility. A static export cannot answer for another moment, show live
data, or answer a request outside the exported set.

## Command

```bash
.venv/bin/pip install -e '.[model,serve]'
.venv/bin/bart-static-replay export    # writes data/static_replay/v1-20261020T170000Z/
.venv/bin/bart-static-replay verify    # re-checks that export against a freshly loaded API
.venv/bin/bart-static-replay publish   # verifies it, then copies it to web/public/replay/
.venv/bin/bart-static-replay check     # checks web/public/replay offline (no warehouse or bundle)
```

`export`, `verify` and `publish` print a JSON summary: counts, the parity result and the
sizes.
- `--spec` selects another spec file and `--api-config` another API config.
- `export --out <dir>` writes to another root.
- `verify <dir>` and `publish <dir>` take another export.
- `publish --public <dir>` writes somewhere other than `web/public/replay`.

Exit codes:
- **0:** the export is complete and identical to the API;
- **1:** it was refused or differs;
- **2:** the spec or config is invalid.

Each run takes about 20 s. `check` prints its own summary and exits 1 on any problem
(see "Offline check").

## Inputs and pins

The replay settings come from `config/local_api.toml`, unchanged: the warehouse, bundle,
lookback, staleness limit and stability cutoffs. `config/static_replay.toml` pins what
the export must be made from:

| Key | Value |
|---|---|
| `as_of` | `2026-10-20T17:00:00Z` |
| `source_feed_timestamp` | `2026-10-20T16:59:23Z`, the latest snapshot collected at or before `as_of` |
| `model_version` | `0.2.0+886fcd260732` |
| `bundle_id` | `db2382848a9ff29a298aa6d320623daf532ac4d813475bf30a8e052e84ed6087` |
| `warehouse_sha256` | `19dd5cfc686bed4f223adbfe5c5d26ef8385e5d1a152da5aa2be7af9378e55cc` |
| `output_dir` | `data/static_replay` (ignored) |

Nothing is written unless every check passes:
- the API config's `as_of` and `bundle_id` equal the pins;
- the warehouse's SHA-256 equals its pin;
- the bundle loads under the pinned ID, with the pinned model version;
- the replay snapshot's feed time equals its pin;
- the API's health is `ok` with no problems. An in-sample replay, before the bundle's
  calibration cutoff, is therefore refused;
- every request answers HTTP 200;
- no observed time is after `as_of` (see "No future data").

## Layout

```text
data/static_replay/v1-20261020T170000Z/
  manifest.json                  provenance, counts, sizes and hashes (not needed by the page)
  health.json                    GET /api/v1/health
  model.json                     GET /api/v1/model/metadata
  stations.json                  GET /api/v1/stations
  boards/<station>/<group>.json  GET /api/v1/stations/<station>/predictions?boarding_group=<group>
  history/<id>.json              GET /api/v1/predictions/<prediction id>/history
```

**One file per request**, so the page fetches only what it shows.
- **Boards:** a board file is named by its station and boarding group, for example
  `boards/MONT/to-EMBR.json`.
- **History:** a history file is named by the prediction ID with its colons replaced.
  `2026-10-20:1965254:11` becomes `history/2026-10-20_1965254_11.json`, so a client
  finds the file from the ID alone.
- **Safe IDs:** station, group and trip IDs must be letters, digits and `-`. The export
  is refused otherwise, so no ID can escape its directory or collide with another.
- **Versions:** `v1` is the layout version, and the manifest states the format,
  `schemaVersion: "static-replay-1"`.

## What each file holds

Each file is the API's JSON body for its request, reduced to the fields the website
reads in `web/src/data/apiDecode.ts`. The kept fields stay in the API's order with the
API's values, and the result is compact UTF-8 JSON with no whitespace. A test keeps the
kept-field list equal to the fields the decoder reads, so a field the website starts
reading cannot be missing, and a field it never reads is not published.

Omitted fields stay in the local API. They are not needed by the page, and the manifest
carries the provenance instead:

| Response | Fields omitted |
|---|---|
| Health | `freshnessSeconds`, `problems`, `modelVersion`, `featureSchemaVersion`, `bundleId` |
| Board | `alertState`; from `replay`, everything except `asOf` |
| Train | `fallbackEtaAt`, `likelyFinalEtaSeconds`, `likelyFinalEtaAt`, `publishedTimeHorizonSeconds`, `revisionIntervalStatus`, `unknownCategories`, `routeId`, `routeShortName`, `gtfsDirectionId`, `stationId`, `stationName`, `stopId`, `scheduledHeadsign` |
| Alert | `descriptionText` |
| Model | `featureSchemaVersion`, `bundleId`, `provisional`, `intervalAvailable`, `servedHorizonsSeconds`, `horizonToleranceSeconds`, `dataMode` |

Stations and history keep every field. They are bare arrays, as in the API, so their
replay label comes from the health and board answers and from the manifest.

Everything the existing website shows is kept:
- **Forecasts:** model forecasts with their 80% interval.
- **Fallbacks:** trains without a forecast keep `predictionStatus`, `statusReason` and
  BART's ETA. This covers the out-of-horizon and out-of-population trains and the two
  `fallback_required` trains at unseen platforms.
- **Empty-board explanations:** the website words them from `unplacedTrainCount`,
  `terminatingTrainCount` and the station's `endOfLine`.
- **History:** each train's published-ETA history.
- **Replay and model metadata:** `dataMode`, `replay.asOf`, the model version, the training
  cutoff and the revision threshold.

## Manifest

The manifest is indented for review. It holds no export time, host name or path, and
the page does not need it.

| Field | Content |
|---|---|
| `schemaVersion`, `dataMode`, `notice` | `static-replay-1`, `historical_replay`, and a not-live notice |
| `replay` | `asOf`, the source snapshot's feed and collection times, and the service date |
| `provenance.model` | Model version, bundle ID, feature schema, training and calibration cutoffs |
| `provenance.warehouse` | Warehouse file name (no directory) and SHA-256 |
| `provenance.staticSchedule` | GTFS archive label, SHA-256 and feed version |
| `provenance.replaySettings` | History lookback, staleness limit and stability cutoffs |
| `counts` | Files, bytes, stations, boards, empty boards, trains by status, trains with an interval, alerts, history files and points |
| `files` | For every file, sorted by path: bytes, SHA-256 and record count (trains on a board, points in a history, stations in the list) |

## Determinism and atomic writes

**Deterministic.** Two exports from identical inputs are byte-identical, manifest
included:
- requests run in a fixed order;
- boards, alerts and histories keep the API's ordering;
- JSON is written with fixed separators;
- manifest entries are sorted by path;
- no wall-clock time is recorded.

Two exports of the October 20 replay produced the same 1,156 files. Their combined
SHA-256 (of the sorted `shasum` list) is `251f6920462eb12ad902f2bd653a656458c158c5d2095855891779379ce06c7d`.

**Atomic.** The export is written to a hidden `.v1-….building` directory beside the
target. It is verified there and only then renamed into place.
- **A failed export** leaves no partial directory, and any earlier export is untouched.
- **A successful export** replaces the earlier one whole, so no stale file survives.

## No future data

The replay engine already holds only data collected at or before `as_of`
([local_api.md](local_api.md#point-in-time-replay)). The exporter checks every full
answer again, omitted fields included:
- **Observed times:** every feed snapshot, generation, replay, collection, alert
  visibility, alert snapshot and training-cutoff time is at or before `as_of`.
- **Snapshot:** each board and the health answer come from the pinned 16:59:23 UTC
  snapshot, and no history point is after it.
- **Estimates:** BART's published ETAs and the model's likely final ETA may be later
  clock times. They are estimates, published or computed by the snapshot.
- **Unclassified times:** any other time field is refused until it is classified.

A test holds a train after `as_of` in the warehouse. The warehouse changes, but not one
exported byte does.

## Validation against the API

`verify` and every `export` do the following:
1. **Manifest.** Read it strictly: keys, types, schema version, data mode and allowed
   paths. Every listed file must exist with its size and SHA-256, and no unlisted file
   may be present.
2. **Second API.** Load a second, independent API from the warehouse and bundle, and ask
   every request again. That API also enumerates the requests, so a missing or extra file
   is found.
3. **Files.** Compare every file byte for byte with its reduced answer. A difference is
   reported with its file and first differing field.
4. **Manifest again.** Compare the manifest with one rebuilt from the fresh answers.

Both sides run the same API code. Parity proves that the files are exactly what the API
answers, not that the API is right. The API's own checks are in `tests/test_local_api.py`
and [local_api.md](local_api.md).

**Results for the October 20 export:**
- **In-process API:** all 1,155 requests answered identically. There were no
  differences and no missing or extra files, and the manifest was identical.
- **Running server:** a separate check queried `bart-serve-local` on 127.0.0.1 over HTTP.
  All 1,155 responses were HTTP 200 with `X-Data-Mode: historical-replay`, and every
  file equalled its reduced answer.

## Results: 2026-10-20 at 10:00 AM PDT

| | Count |
|---|---|
| Stations | 50 |
| Boards | 95 (5 empty: the Oakland Airport connector both ways, Antioch, and Pittsburg Center both ways) |
| Trains | 1,057 |
| `ok`, all with an interval | 79 |
| `outside_model_horizon` | 949 |
| `outside_model_population` | 27 |
| `fallback_required` | 2 |
| Alerts visible | 1 |
| History files / points | 1,057 / 47,939 |

These match the full sweep of the API in [local_api.md](local_api.md).

### Sizes

gzip sizes use compression level 6. They estimate transfer size for a host that
compresses JSON.

| Files | Count | Bytes | gzip bytes | Median file | Largest file |
|---|---|---|---|---|---|
| `health.json` | 1 | 121 | 121 | | |
| `model.json` | 1 | 125 | 130 | | |
| `stations.json` | 1 | 22,255 | 1,773 | | |
| `boards/` | 95 | 551,286 | 85,394 | 5,738 | 13,572 |
| `history/` | 1,057 | 5,176,305 | 391,399 | 4,429 | 13,810 |
| Data files | 1,155 | 5,750,092 | 478,817 | | |
| `manifest.json` | 1 | 188,535 | 56,240 | | |
| **Total** | **1,156** | **5,938,627** | **535,057** | | |

**First view.** With no station in the address, the page fetches four data files:
- `health.json` and `stations.json`;
- the first station's first board, `boards/12TH/to-19TH.json`;
- its earliest train's history.

Those total **40,875 bytes, or 3,573 bytes gzipped**. For comparison, the current Pages
build's HTML, JavaScript and CSS are 334,834 bytes, or 99,354 gzipped. Its Latin web
fonts add up to about 138 KB, already compressed, because browsers fetch only the font
subsets a page uses. The data is therefore about 1.5% of a first visit, or 3.5% when
the fonts are already cached.

**Each later choice** fetches one board (median 903 bytes gzipped, largest 1,346) and one
history (median 334 bytes gzipped, largest 873). The manifest is not fetched.

**History is 90% of the export's bytes.** Each point repeats its field names and full
timestamps. A columnar encoding would be smaller, but it would change the response
contract, which this export keeps.

## The published replay

`bart-static-replay publish` verifies the export against a freshly loaded API, as
`verify` does, and then replaces `web/public/replay/` with:
- a copy of the export, unchanged;
- `index.json`, which names the export, its schema version, its replay time and the
  manifest's SHA-256.

The copy passes the offline check before it replaces the earlier one, through the same
build, check and rename steps as an export.

The website reads `index.json` first and refuses any schema version other than
`static-replay-1` ([website_architecture.md](website_architecture.md#static-replay-client-github-pages)).

| | Published replay |
|---|---|
| Export | `v1-20261020T170000Z` (layout v1, `schemaVersion` `static-replay-1`) |
| Replay time / source snapshot | 2026-10-20T17:00:00Z / 2026-10-20T16:59:23Z |
| Model / bundle | `0.2.0+886fcd260732` / `db2382848a9ff29a298aa6d320623daf532ac4d813475bf30a8e052e84ed6087` |
| Warehouse | `bart_checkpoint_2026-10-20.duckdb`, SHA-256 `19dd5cfc686bed4f223adbfe5c5d26ef8385e5d1a152da5aa2be7af9378e55cc` |
| Manifest SHA-256 | `737f7bf404cd180ff798ec6e5d2cd8b46b9f40ffb398d9223e7b523bbf8fbe90` (188,535 bytes) |
| `index.json` SHA-256 | `07eb740f64c68e95a46a255028659c4a21f1053702fffc63ebd7274fa46252fe` (212 bytes) |
| Tracked files | 1,157: 1,155 answers, the manifest and the index |
| Tracked bytes | 5,938,839 (535,238 gzipped) |
| Tree hash | `5202c3fb6b093930642571bd1999e03e36084bb81e248115d1692abca5afb0ba`, the SHA-256 of the sorted `<sha256>  <path>` lines of every file |

The published export is byte-identical to the reviewed export in `data/static_replay/`.

The published files hold values from BART's GTFS and GTFS-Realtime data. They are
redistributed under the
[BART Developer License Agreement](https://www.bart.gov/schedules/developers/developer-license-agreement),
and the site's footer credits BART as the source
([README](../README.md#data-source-and-license)).

### Offline check

```bash
.venv/bin/bart-static-replay check   # web/public/replay by default; about half a second
```

It needs neither the warehouse nor the bundle, and imports only pydantic. CI runs it, and
so does the Pages workflow before it builds. A replay that fails is never deployed. It
checks:
- **Index and manifest:**
  - exact keys and values in `index.json`, including a supported schema version and a
    safe export name;
  - only `index.json` and that export in `web/public/replay/`;
  - the manifest's SHA-256 against the index;
  - the manifest itself, as `verify` does: shape, safe relative paths, every file's size
    and SHA-256, and no unlisted or symlinked file.
- **Schemas:**
  - every file holds exactly the kept fields, strictly typed as in `api/schemas.py`, in
    the API's order, in the exporter's compact form.
- **Consistency:**
  - the website decoder's rules: forecast numbers only on `ok` trains, probabilities from
    0 to 1, valid ranges, non-negative ETAs, and no duplicate stations, groups,
    predictions or snapshots;
  - health is `ok`;
  - each board's model block equals `model.json`;
  - every history point's `publishedEtaSeconds` equals its two timestamps' difference.
- **Cross-references:**
  - every boarding group in `stations.json` has its board, and every board is a listed
    group;
  - every train has its history file, and no history belongs to no train.
- **Counts:** every manifest count and per-file record count, recomputed from the files.
- **No future data:**
  - no observed time is after the replay time;
  - every board and the health answer are from the source snapshot, and no history point
    is after it.

### Updating the public replay

1. **Collect.** Collect, transform and build a new checkpoint warehouse, offline. If a new
   model is wanted, train and package it under its own milestone.
2. **Configure.** Point `config/local_api.toml` at it, with an `as_of` after every outcome
   the model used. Health must report no problems there.
3. **Pin.** Set the new pins in `config/static_replay.toml`: replay time, source snapshot,
   model version, bundle ID and warehouse SHA-256.
4. **Export.** Run `bart-static-replay export` and review the export and its size.
5. **Publish.** Run `bart-static-replay publish`. It verifies the export against the API,
   replaces `web/public/replay/` and runs the offline check.
6. **Re-run checks.** Run all checks, including `bart-static-replay check` and the web
   tests. The web tests pin the October 20 counts, so a new replay updates them on
   purpose.
7. **Merge.** Commit `web/public/replay/` with the code and docs, and merge to `main`. The
   Pages workflow checks the replay again, builds and deploys.

## Limitations

- **One fixed moment.** It is not live, and nothing ticks or updates.
- **Only exported requests.** Any other station, boarding group or prediction is not in
  the export.
- **Local inputs.** Regenerating or verifying against the API needs the ignored local
  warehouse and bundle, so CI cannot rebuild the export. CI checks the published copy
  offline instead.
- **Repository size.** The published replay adds about 6 MB and 1,157 files to the
  repository. Each update replaces them, and Git keeps the old copies in its history.
- **API-only fields.** The omitted fields exist only in the local API.
- **Inherited limits.** Everything in [local_api.md](local_api.md#limitations) still
  applies: horizons, the static schedule, unplaced trains, unsupported lines and the
  provisional model.
