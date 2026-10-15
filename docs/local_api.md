# Local prediction API (historical replay)

A local-only HTTP API that serves the ETA revision models through the website's
`PredictionClient` contract. It runs in **historical-replay mode**: it answers as if it
were a configured past moment, using the ignored local warehouse and the exported model
bundle ([model_serving.md](model_serving.md)). It never contacts BART and is never live.
The frontend is not connected yet.

## Start

```bash
.venv/bin/pip install -e '.[model,serve]'
.venv/bin/bart-serve-local --warehouse data/warehouse/server_export_2026-10-15.duckdb
# serves http://127.0.0.1:8000/api/v1/health
```

Settings come from `config/local_api.toml`, and `--config` selects another file. Flags
override single values:

- `--as-of 2026-10-15T17:00:00Z`;
- `--warehouse`;
- `--bundle`;
- `--host`;
- `--port`.

The host must be a loopback address (`127.0.0.1` by default, `::1` or `localhost`).
Anything else is refused, so this command cannot bind publicly. There is no
authentication and there are no secrets.

The default `as_of` is 2026-10-15 17:00 UTC (10:00 PDT). That service date was not used
for training, validation or testing. Choose any time the warehouse covers. A time outside
the collected range gets `feed_stale` or `feed_unavailable`.

## Point-in-time replay

When the API starts, the replay engine opens an in-memory DuckDB and attaches the
warehouse read-only. It copies an **allowlist** of sources, each cut off at `as_of`, and
then detaches the warehouse:

| Copied | Cut-off |
|---|---|
| `rt_predictions_enriched` (trip-update rows with their static schedule match) | collected at or before `as_of`, within the last 6 h |
| Trip-update snapshot times; alert snapshots and observations | collected at or before `as_of` |
| Alert text and informed entities | only alert versions already seen by `as_of` |
| Manual alert categories (`config/alert_annotations.csv`) | only rows reviewed before the replay's Pacific date |
| Static GTFS schedule | no time dimension; a schedule retrieved after `as_of` is reported in `/health` |

Every query runs on these copies, so nothing else is reachable. Final labels, the
observed-arrival proxy, the modeling tables, alert visibility runs computed over the
whole collection, and anything collected after `as_of` are not in the database at all. A
query naming one fails. The tests check this, and they also check that holding a train
**after** `as_of` changes nothing the API returns at `as_of`.

The **replay snapshot** is the latest trip-update snapshot at or before `as_of`. For
every trip-stop it lists, the engine computes each model feature from that trip-stop's
listings up to the snapshot, using the training definitions (modeling_plan.md). On 25
real test-day examples, and on synthetic examples in the tests, every replayed feature
equals the training feature table exactly. Alert context uses the latest alert snapshot
at or before the replay snapshot, at most 120 s older. History ends at the replay
snapshot.

**Replay labelling.** Every response, error responses included, carries the headers
`X-Data-Mode: historical-replay` and `X-Replay-As-Of`. Object bodies also carry
`dataMode: "historical_replay"`. Prediction responses add a `replay` block:

- `asOf`;
- `sourceTimestamp`, the feed header time of the replay snapshot;
- `collectedAt`;
- `freshnessSeconds`, which is `asOf` minus the source time;
- `stale` and `staleAfterSeconds`.

In replay, `generatedAt` (the model timestamp) is `asOf`, the moment the model is run
"as of".

## Endpoints

| Endpoint | Response |
|---|---|
| `GET /api/v1/health` | `HealthStatus` plus `asOf`, `freshnessSeconds`, `problems`, model and schema versions. Always 200; `status` is `degraded` when anything is missing or stale |
| `GET /api/v1/stations` | `Station[]`: parent stations with service on the replay date. Directions are labelled by destination (the last part of BART's headsign) |
| `GET /api/v1/stations/{station_id}/predictions?direction_id=0` | `PredictionResponse` for one direction (`direction_id` is required, `0` or `1`) |
| `GET /api/v1/predictions/{prediction_id}/history` | `PredictionHistoryPoint[]`, oldest first, ending at the replay snapshot |
| `GET /api/v1/model/metadata` | `ModelMetadata` (the client's `getModelMetadata`) |

`prediction_id` is `<service date>:<trip_id>:<stop_sequence>`, as in
`2026-10-15:1965830:8`. Interactive docs are at `/docs` while the server runs.

### Each train

Contract fields:

- `predictionId`, `tripId`, `lineName` ("Blue line"), `headsign` (the destination);
- `carCount`: always `null`, because BART's feed carries no consist length;
- `currentEtaSeconds` (seconds after the feed snapshot) and `currentEtaAt`;
- `predictedRevisionSeconds`, rounded to whole seconds;
- `revisionInterval`, rounded outward to whole seconds;
- `revisionProbability`, the probability of a revision of more than 60 s;
- `stability`, from the website's cutoffs (0.25 and 0.5, in `config/local_api.toml`).

Additions:

- `predictionStatus` and `statusReason`;
- `likelyFinalEtaSeconds` and `likelyFinalEtaAt`: current + predicted revision, the same
  arithmetic as `web/src/domain/eta.ts`;
- `fallbackEtaAt`;
- `publishedTimeHorizonSeconds`;
- `revisionIntervalStatus`;
- `unknownCategories`;
- route, station and stop identifiers;
- `scheduledHeadsign`, BART's full headsign.

| `predictionStatus` | Meaning | Model fields |
|---|---|---|
| `ok` | Inside the models' demonstrated support | Filled; the interval is filled only if the bundle's interval is available |
| `outside_model_horizon` | BART's ETA is not within 60 s of 5, 10 or 15 minutes, the only published-time horizons the models were trained on | `null` |
| `outside_model_population` | A trip origin, an excluded line (Antioch extension, Oakland Airport), an added or cancelled trip, a skipped stop, a repeated stop, or no schedule match: excluded from training | `null` |
| `fallback_required` | A category never seen in training (for example a stop or hour); the reason is "input outside demonstrated model support" | `null` |
| `features_unavailable` | A feature could not be computed at the snapshot (the reason lists it) | `null` |

For every status except `ok`, `fallbackEtaAt` is BART's unadjusted published ETA, and
that is what a client should show.

### Frontend contract for unsupported trains

The board lists **every** upcoming train, supported or not. Riders still need the trains
for which only BART's ETA is available, so the API never filters a board to supported
trains. The frontend should show each train as follows:

| Case | How it is signalled | Show |
|---|---|---|
| Model forecast with range | `predictionStatus: "ok"` and `revisionInterval` is an object | The model forecast: likely final published ETA, expected adjustment, 80% range, stability |
| Forecast, interval unavailable | `predictionStatus: "ok"`, `revisionInterval: null`, `revisionIntervalStatus.available: false` | The forecast without a range, saying the range is unavailable (`unavailableReasons`). Never draw a range |
| `outside_model_horizon` | model fields `null` | BART's published ETA only (`fallbackEtaAt`) |
| `outside_model_population`, `fallback_required`, `features_unavailable` | model fields `null`, `statusReason` set | BART's published ETA only (`fallbackEtaAt`), optionally with the reason |

"Interval unavailable" is not a `predictionStatus` value. It is an `ok` prediction whose
interval is `null`.

**Never substitute a simulated result.** In http mode the mock client's fixtures must
not fill a `null` model field. A train without a model forecast shows BART's ETA and
nothing else.

**Most trains being unsupported is expected.** On the 2026-10-15 10:00 PDT replay board
(Embarcadero, toward the East Bay), 2 of 20 trains have a model forecast. The models were
trained only at published-time horizons of 5, 10 and 15 minutes (within 60 s), so at any
moment only trains whose ETA falls in those windows are supported. Trains closer, farther
or between the windows are `outside_model_horizon`. This is the documented model domain,
not an API failure. As a train approaches, its ETA normally passes through each window,
so the same train gets a forecast at several points of its approach.

## Errors

Errors return `{"error": {"code", "clientCode", "message", "dataMode", "asOf"}}`.
`clientCode` maps to the website's `PredictionClientErrorCode`.

| HTTP | `code` | When |
|---|---|---|
| 503 | `model_bundle_unavailable` | Bundle missing, altered or built for another runtime. Stations and history still work |
| 503 | `warehouse_unavailable` | Warehouse file missing or lacking a required table |
| 503 | `feed_unavailable` | No trip-update snapshot at or before `as_of` |
| 503 | `feed_stale` | The latest snapshot at or before `as_of` is more than 120 s old: the warehouse does not cover `as_of` |
| 503 | `feature_schema_mismatch` | The bundle needs a feature schema other than the one this API computes (`eta-revision-features-1`) |
| 404 | `station_not_found`, `direction_not_found` | Unknown station, or a direction the station does not serve on the replay date |
| 404 | `prediction_history_unavailable` | Unknown or malformed `prediction_id`, or no listing at or before `as_of` |
| 422 | `invalid_request` | Missing or invalid query parameter, for example `direction_id` |

A missing feature for one train is not a request error. That train gets
`features_unavailable` and the others are unaffected.

## CORS

CORS is granted only to browser origins on this machine: `http://localhost[:port]`,
`http://127.0.0.1[:port]` and `http://[::1][:port]`. It covers GET requests, without
credentials.

A response to an allowed origin carries, on success and on error alike:

```text
Access-Control-Allow-Origin: <that origin>
Access-Control-Expose-Headers: X-Data-Mode, X-Replay-As-Of
Vary: Origin
```

That lets frontend code read the replay headers. Any other origin, including `https://`
variants of these hosts and LAN addresses, gets no `Access-Control-*` header, and its
preflight returns 400. Requests without an `Origin` header (curl, server-side clients)
work normally and carry no CORS headers.

## Contract differences

The responses follow `web/src/domain/types.ts`. The differences below must be handled
when the frontend is connected:

1. **Nullable model fields.** On `TrainPrediction`, `predictedRevisionSeconds`,
   `revisionInterval`, `revisionProbability` and `stability` are `null` whenever
   `predictionStatus` is not `ok`. `revisionInterval` is also `null` whenever the bundle
   cannot support an honest range. The TypeScript types declare them non-null, so they
   must become nullable, and the UI must show `fallbackEtaAt` for those trains.
2. **`HealthStatus.latestFeedTimestamp`** is `null` only when no warehouse is loaded.
3. **Predictions path.** The client's placeholder uses
   `GET /api/v1/predictions?station_id=…&direction_id=…`, while this API uses
   `GET /api/v1/stations/{station_id}/predictions?direction_id=…`.
   `HttpPredictionClient` must use the latter.
4. **Arrays stay arrays.** `stations` and `history` return bare arrays, as the contract
   says. For them, the replay identification is in the headers.
5. **Additions only otherwise.** Every other difference is an extra field, which a
   contract client ignores.

## Limitations

- **Few trains get predictions.** The models serve only BART ETAs near 5, 10 and 15
  minutes. At a typical moment most trains on a board are `outside_model_horizon`: 18 of
  20 at Embarcadero toward the East Bay at 10:00 PDT on 2026-10-15.
- **Edge horizons.** Within those horizons, training used each trip-stop's single
  closest snapshot, so ETAs 30 to 60 s from a target are rarer in training than in
  serving.
- **Post-hoc eligibility.** Only exclusions that can be checked at the snapshot are
  applied. Training also kept only events with a stable, confirmed final estimate, and
  that cannot be known in advance.
- **Unplaced trains.** Trains the feed lists without a schedule match have no direction.
  They are counted in `unplacedTrainCount`, not shown.
- **Provisional.** The models and interval carry everything in
  [model_serving.md](model_serving.md#limitations).

## Runtime profile (informational)

These measurements come from a local run on the development machine, which has more
memory and CPU than the 1 vCPU / 1 GB Droplet, so the Droplet would be slower. They used
the 2026-10-15 snapshot warehouse, with `as_of` 2026-10-15T17:00:00Z and a 6 h history
window. Nothing was optimized for them.

| Measure | Result |
|---|---|
| Cold start (process launch to first healthy `/health`) | 4.0 to 5.0 s with warm file caches; 12.0 s on the first launch |
| Replay engine build (copy the allowlisted, cut-off data) | 2.2 s |
| Bundle load (verify hashes, unpickle) | 0.3 s |
| In-memory replay data | about 214 MB of DuckDB tables (350,162 trip-update rows over 6 h, 57,188 schedule rows, 7,730 snapshots), plus 41 MB DuckDB file cache |
| Resident memory | about 195 MB after imports; 1.5 to 1.8 GB right after start-up (peak 2.0 GB while building the replay copy); 1.25 to 1.5 GB once loaded and after requests |
| `GET /health` | median 0.9 ms, p95 1.4 ms (320 bytes) |
| `GET /stations` | median 0.9 ms, p95 1.1 ms (17.7 KB; cached after the first call) |
| One full board (`EMBR`, direction 0, 20 trains) | median 84 ms, p95 90 ms (17.8 KB); other boards 30 to 108 ms on first request |
| One history (59 points) | median 3.4 ms, p95 3.8 ms (8.7 KB) |

Building the replay copy runs the enriched view over the whole warehouse. DuckDB keeps
much of that working memory afterwards, and its default limit is 80% of RAM. So resident
memory is several times the size of the replay data. **As built, the API would not fit
the 1 GB Droplet.** A public version would need a smaller footprint; nothing has been
changed for it yet. Possible approaches:

- precomputed replay or live tables;
- only the columns the board needs;
- a DuckDB `memory_limit`;
- an incremental live window instead of a historical copy.

## Example (2026-10-15, 10:00 PDT, abridged)

`GET /api/v1/stations/EMBR/predictions?direction_id=0`:

```json
{"stationId": "EMBR", "directionId": "0",
 "feedTimestamp": "2026-10-15T16:59:23Z", "generatedAt": "2026-10-15T17:00:00Z",
 "dataMode": "historical_replay",
 "replay": {"asOf": "2026-10-15T17:00:00Z", "sourceTimestamp": "2026-10-15T16:59:23Z",
            "freshnessSeconds": 37, "stale": false, "...": "..."},
 "trains": [
  {"predictionId": "2026-10-15:1965830:8", "lineName": "Blue line",
   "headsign": "Dublin/Pleasanton", "currentEtaSeconds": 552,
   "currentEtaAt": "2026-10-15T17:08:35Z", "predictedRevisionSeconds": 26,
   "revisionInterval": {"lowerSeconds": 2, "upperSeconds": 72, "level": 0.8},
   "revisionProbability": 0.0738, "stability": "likely_to_hold",
   "predictionStatus": "ok", "likelyFinalEtaAt": "2026-10-15T17:09:01Z", "...": "..."},
  {"predictionId": "2026-10-15:1965319:12", "lineName": "Yellow line",
   "headsign": "Pittsburg/Bay Point", "currentEtaSeconds": 60,
   "predictedRevisionSeconds": null, "revisionInterval": null,
   "revisionProbability": null, "stability": null,
   "predictionStatus": "outside_model_horizon",
   "fallbackEtaAt": "2026-10-15T17:00:23Z", "...": "..."}],
 "alerts": [{"alertId": "BSA_560", "scope": "system", "category": "planned_work",
             "headerText": "BART.gov Alert", "visibleSince": "2026-10-14T02:56:22Z"}],
 "model": {"modelVersion": "0.1.0+8d942e17429c", "trainedThrough": "2026-10-13T09:11:23Z",
           "revisionThresholdSeconds": 60, "simulated": false,
           "featureSchemaVersion": "eta-revision-features-1", "...": "..."}}
```
