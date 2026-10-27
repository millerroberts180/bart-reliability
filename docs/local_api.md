# Local prediction API (historical replay)

A local-only HTTP API that serves the ETA revision models through the website's
`PredictionClient` contract. It runs in **historical-replay mode**: it answers as if it
were a configured past moment, using the ignored local warehouse and the exported model
bundle ([model_serving.md](model_serving.md)). It never contacts BART and is never live.
The website reads it locally when started with `VITE_DATA_MODE=http`
([website_architecture.md](website_architecture.md#http-client-local-api)). Its answers
at the replay time are exported as static JSON files, and the public GitHub Pages site
reads those files, never this API ([static_replay.md](static_replay.md)).

## Start

```bash
.venv/bin/pip install -e '.[model,serve]'
.venv/bin/bart-serve-local
# serves http://127.0.0.1:8000/api/v1/health
```

Settings come from `config/local_api.toml`, and `--config` selects another file. Flags
override single values:

- `--as-of 2026-10-20T17:00:00Z`;
- `--warehouse`;
- `--bundle`;
- `--bundle-id` (the only bundle build to load; `bart-eta-bundle verify` prints it);
- `--host`;
- `--port`.

The host must be a loopback address (`127.0.0.1` by default, `::1` or `localhost`).
Anything else is refused, so this command cannot bind publicly. There is no
authentication and there are no secrets.

**The local historical replay is 2026-10-20 at 17:00 UTC (10:00 AM PDT).**
- **Data:** the 2026-10-20 checkpoint warehouse
  (`data/warehouse/bart_checkpoint_2026-10-20.duckdb`). Its SHA-256 is
  `19dd5cfc686bed4f223adbfe5c5d26ef8385e5d1a152da5aa2be7af9378e55cc`.
- **Model:** `0.2.0+886fcd260732`, pinned by `bundle_id`
  ([model_serving.md](model_serving.md#the-2026-10-20-bundle)).
- **Snapshot:** the replay snapshot is the one collected at 16:59:23 UTC, 37 s before the
  replay time.
- **Why that day:** October 20 comes after every outcome this model used. Its training
  data runs through 2026-10-16 08:55 UTC, and its selection and interval calibration
  through 2026-10-19 08:52 UTC. It is also a partial service day that no model was
  trained, selected or tested on.

**Why October 15 is no longer appropriate.** The earlier default, 2026-10-15 17:00 UTC,
suited the PR #7 models, which never used that day. Model 0.2.0 trained on it, so a replay
there would show in-sample predictions. `/api/v1/health` now reports a `model:` problem,
with status `degraded`, whenever `as_of` falls before the bundle's calibration cutoff.

Choose any time the warehouse covers after that cutoff. A time outside the collected
range gets `feed_stale` or `feed_unavailable`.

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

**Concurrent requests.** FastAPI runs the endpoints on a thread pool, and a browser sends
several requests at once, so queries overlap. One DuckDB connection must not be used by
two threads at once, so each query opens its own cursor on the in-memory copies, sets
UTC (a cursor does not inherit session settings) and closes it however the query ends.
The tests run eight threads of mixed requests against one engine and check every answer,
and check that every cursor is closed, including after a failed query.

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
| `GET /api/v1/stations` | `Station[]`: parent stations with service on the replay date, each with its `boardingGroups` and `endOfLine` |
| `GET /api/v1/stations/{station_id}/predictions?boarding_group=to-SHAY` | `PredictionResponse` for one boarding group (`boarding_group` is required) |
| `GET /api/v1/predictions/{prediction_id}/history` | `PredictionHistoryPoint[]`, oldest first, ending at the replay snapshot |
| `GET /api/v1/model/metadata` | `ModelMetadata` (the client's `getModelMetadata`) |

`prediction_id` is `<service date>:<trip_id>:<stop_sequence>`, as in
`2026-10-15:1965830:8`. Interactive docs are at `/docs` while the server runs.

### Boarding groups

A board is the trains leaving a station one way: a **boarding group**, built from the
schedule's platforms and neighbouring stations. GTFS `direction_id` is never used to
group or place trains, because each route defines it for itself: at Hayward, direction 1
holds Green line trains to Daly City and Orange line trains to Berryessa, which leave
from opposite platforms. The audit, the rule and why it works are in
[boarding_groups.md](boarding_groups.md) (`src/bart_reliability/api/boarding.py`).

Each station lists its groups in platform order, then by group ID:

```json
{"id": "HAYW", "name": "Hayward", "endOfLine": false,
 "boardingGroups": [
  {"id": "to-SHAY", "label": "Toward Berryessa/North San Jose",
   "destinations": ["Berryessa", "Berryessa/North San Jose"], "platform": "1",
   "gtfsDirectionIds": ["0", "1"]},
  {"id": "to-BAYF", "label": "Toward Daly City and Richmond",
   "destinations": ["Daly City", "Richmond"], "platform": "2",
   "gtfsDirectionIds": ["0", "1"]}]}
```

- `id` is `to-` and the group's next stations, stable for the feed and readable in a URL.
- `label` comes from that day's destinations.
- `platform` is set only when every train in the group leaves from that one platform on
  the replay date; otherwise it is `null`, and each train carries its own `platform`.
- `gtfsDirectionIds` is there only so the website can translate old `?direction=` links,
  where that is unambiguous.
- `endOfLine` is true when every train at the station starts or ends its trip there.
  Antioch, Berryessa, Dublin/Pleasanton, Millbrae, Oakland Airport and Richmond have one
  group each.

A train is placed by its scheduled stop:
- its matched stop gives the visit and the next station, and the next station gives the
  group;
- a train listed at a platform its schedule does not use there is placed by its one
  scheduled visit to the station, and gets no `platform`;
- a train whose trip ends at the station cannot be boarded, and is counted in
  `terminatingTrainCount`;
- a train with no scheduled trip, or with no single possible visit, is counted in
  `unplacedTrainCount`.

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
- `platform`, the scheduled platform code at this station (`null` when the listing and the
  schedule disagree, or the schedule has no platform codes);
- route, station and stop identifiers, and `gtfsDirectionId` (route-relative; never used to
  group trains);
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

**Most trains being unsupported is expected.** At the 2026-10-20 10:00 PDT replay, 79 of
the 1,057 trains on the 95 boards have a model forecast. At Embarcadero, toward the East
Bay, it is 1 of 18. The others break down as follows:
- 949 are `outside_model_horizon`;
- 27 are `outside_model_population` (23 trip origins and 4 repeated stops at SFO);
- 2 are `fallback_required`. Their platforms, `C80-1` at Pittsburg/Bay Point and `L20-1`
  at West Dublin/Pleasanton, never appeared in training, so they get BART's ETA only.

The models were
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
| 404 | `station_not_found`, `boarding_group_not_found` | Unknown station, or a boarding group the station does not have with trains on the replay date |
| 404 | `prediction_history_unavailable` | Unknown or malformed `prediction_id`, or no listing at or before `as_of` |
| 422 | `invalid_request` | Missing or invalid query parameter: no `boarding_group` (including a request that still sends only the old `direction_id`), or one with characters other than letters, digits and `-` |

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

The responses follow `web/src/domain/types.ts`. The website's types and
`HttpPredictionClient` were updated for the differences that remained when the API was
built:

1. **Nullable model fields.** On `TrainPrediction`, `predictedRevisionSeconds`,
   `revisionInterval`, `revisionProbability` and `stability` are `null` whenever
   `predictionStatus` is not `ok`. `revisionInterval` is also `null` whenever the bundle
   cannot support an honest range. The website types these trains separately and shows
   BART's published ETA for them (`currentEtaAt`, which equals `fallbackEtaAt`).
2. **`HealthStatus.latestFeedTimestamp`** is `null` only when no warehouse is loaded.
3. **Predictions path.** The API uses
   `GET /api/v1/stations/{station_id}/predictions?boarding_group=…`, and so does
   `HttpPredictionClient` (the earlier placeholder used `/api/v1/predictions?station_id=…`).
   Stations carry `boardingGroups` instead of `directions`, and a board carries
   `boardingGroupId` instead of `directionId` (see "Boarding groups").
4. **Arrays stay arrays.** `stations` and `history` return bare arrays, as the contract
   says. For them, the replay identification is in the headers.
5. **Additions only otherwise.** Every other difference is an extra field, which a
   contract client ignores.

## Limitations

- **Few trains get predictions.** The models serve only BART ETAs near 5, 10 and 15
  minutes. At a typical moment most trains on a board are `outside_model_horizon`: 17 of
  18 at Embarcadero toward the East Bay at 10:00 PDT on 2026-10-20.
- **Edge horizons.** Within those horizons, training used each trip-stop's single
  closest snapshot, so ETAs 30 to 60 s from a target are rarer in training than in
  serving.
- **Post-hoc eligibility.** Only exclusions that can be checked at the snapshot are
  applied. Training also kept only events with a stable, confirmed final estimate, and
  that cannot be known in advance.
- **Unplaced and terminating trains.** Trains the feed lists without a schedule match have
  no known way out; they are counted in `unplacedTrainCount`, not shown. Trains listed at
  the last stop of their trip cannot be boarded; they are counted in
  `terminatingTrainCount` (4 across all 50 stations at the default `as_of`).
- **Empty boards.** At the default `as_of`, 5 of the 95 boards are empty. Every train
  listed at those stations is on another board or counted as unplaced, so no query or
  mapping drops trains.
  - *The Oakland Airport connector*, at Coliseum and at Oakland Airport. The airport line
    (routes 19 and 20) never appears in the collected feed, and `realtime_routes.txt`
    marks it as having no real-time data, though the schedule has 370 trips a day.
  - *Antioch, and Pittsburg Center* both ways. The feed does list trains here (5 at Antioch
    and 9 upcoming at Pittsburg Center), but the Antioch extension's real-time trips use
    trip ids that are not in the static GTFS and carry no route or direction. None of
    them matches a scheduled trip (83,812 rows in the collection), so they are unplaced
    and given no direction. They would also be outside the model's population.

  Before boarding groups, 9 of 100 boards were empty. The four extra were the arrival
  "directions" of Antioch, Dublin/Pleasanton, Millbrae and Richmond, each toward itself.
  BART's feed almost never lists a train at the last stop of its trip (only 10 of 3,404
  trips in the collection), and a terminal now offers only its departures.

  The website's empty state names whichever of these reasons the response shows.
- **Provisional.** The models and interval carry everything in
  [model_serving.md](model_serving.md#limitations).

## Runtime profile (informational)

These measurements come from a local run on the development machine, which has more
memory and CPU than the 1 vCPU / 1 GB collector Droplet (since retired), so the Droplet
would have been slower. They used the 2026-10-15 snapshot warehouse, with `as_of`
2026-10-15T17:00:00Z and a 6 h history window. Nothing was optimized for them.

| Measure | Result |
|---|---|
| Cold start (process launch to first healthy `/health`) | 4.0 to 5.0 s with warm file caches; 12.0 s on the first launch |
| Replay engine build (copy the allowlisted, cut-off data) | 2.2 s |
| Bundle load (verify hashes, unpickle) | 0.3 s |
| In-memory replay data | about 214 MB of DuckDB tables (350,162 trip-update rows over 6 h, 57,188 schedule rows, 7,730 snapshots), plus 41 MB DuckDB file cache |
| Resident memory | about 195 MB after imports; 1.5 to 1.8 GB right after start-up (peak 2.0 GB while building the replay copy); 1.25 to 1.5 GB once loaded and after requests |
| `GET /health` | median 0.9 ms, p95 1.4 ms (320 bytes) |
| `GET /stations` | median 0.9 ms, p95 1.1 ms (17.7 KB; cached after the first call) |
| One full board (`EMBR`, toward the East Bay, 20 trains) | median 84 ms, p95 90 ms (17.8 KB); other boards 30 to 108 ms on first request. Measured before boarding groups; the engine now also builds its visit and group tables at start-up (start-up measured at 3.0 s in-process afterwards) |
| One history (59 points) | median 3.4 ms, p95 3.8 ms (8.7 KB) |

Building the replay copy runs the enriched view over the whole warehouse. DuckDB keeps
much of that working memory afterwards, and its default limit is 80% of RAM. So resident
memory is several times the size of the replay data. **As built, the API would not have
fit the 1 GB Droplet.** A public version would need a smaller footprint; nothing has been
changed for it yet. Possible approaches:

- precomputed replay or live tables;
- only the columns the board needs;
- a DuckDB `memory_limit`;
- an incremental live window instead of a historical copy.

## Example (2026-10-15, 10:00 PDT, abridged)

This was recorded under the earlier default, with the PR #7 bundle (`0.1.0+8d942e17429c`),
as was the website's recorded fixture. With model 0.2.0 at the 2026-10-20 replay, every
response has the same shape. The 50 recorded requests were replayed and compared field by
field ([model_serving.md](model_serving.md#the-2026-10-20-bundle)).

`GET /api/v1/stations/EMBR/predictions?boarding_group=to-WOAK`:

```json
{"stationId": "EMBR", "boardingGroupId": "to-WOAK",
 "feedTimestamp": "2026-10-15T16:59:23Z", "generatedAt": "2026-10-15T17:00:00Z",
 "dataMode": "historical_replay",
 "replay": {"asOf": "2026-10-15T17:00:00Z", "sourceTimestamp": "2026-10-15T16:59:23Z",
            "freshnessSeconds": 37, "stale": false, "...": "..."},
 "trains": [
  {"predictionId": "2026-10-15:1965830:8", "lineName": "Blue line",
   "headsign": "Dublin/Pleasanton", "currentEtaSeconds": 552, "platform": "2",
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
           "featureSchemaVersion": "eta-revision-features-1", "...": "..."},
 "unplacedTrainCount": 0, "terminatingTrainCount": 0}
```
