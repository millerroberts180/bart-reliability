# Curated historical showcase replay

**Status:** the replay the public site shows. The website's static build reads it
([website_architecture.md](website_architecture.md)), and the Pages workflow deploys it
from `main`.

The showcase is one fixed moment of recorded BART data, replayed through the existing
model. It is a presentation layer for the Python, SQL and modeling work, not a new
model:
- **Model:** model `0.2.0+886fcd260732` and its serving bundle are unchanged. Nothing is
  fitted, retrained, compared or tuned.
- **Data:** it uses the existing warehouse (`bart_checkpoint_2026-10-20.duckdb`), the
  existing feature definitions, and the static-replay architecture
  ([static_replay.md](static_replay.md)).
- **Delivery:** the site stays static on GitHub Pages and needs no public API.

## Three ETAs

The project has no physical arrival times. Every value is one of three different
things, and the showcase never mixes them up:

| Term | Meaning | Known at the replay moment? |
|---|---|---|
| **BART published ETA** | What BART said at the replay snapshot | Yes |
| **Model-adjusted ETA** | BART's ETA plus the model's predicted revision | Yes, computed from the snapshot and earlier listings |
| **Final published ETA** | The final stable ETA BART published later: the warehouse's observed-arrival proxy, tier A ([observed_arrival_proxy.md](observed_arrival_proxy.md)) | No. It is a retrospective outcome and not a physical arrival |

They give three differences:
- **Predicted revision:** model-adjusted minus BART published.
- **Realized revision:** final published minus BART published.
- **Model error:** model-adjusted minus final published.

A direction is "later", "earlier" or "unchanged" by its sign. "Direction correct" means
the predicted and realized revisions have the same direction. The website says "ETA
moved later" or "ETA moved earlier". These are revisions to BART's published ETA, not
train delays.

## How the moment was chosen

**Coverage, not accuracy.**
- **Candidates:** every trip-update snapshot of 2026-10-19 (1,440). That is the complete
  held-out service day: after model 0.2.0's training, selection and interval
  calibration, and its spent sealed-test day.
- **Ranking:**
  1. the most model-supported forecasts;
  2. the most stations with a supported forecast;
  3. the most distinct trip runs;
  4. the greatest median absolute predicted revision;
  5. the earliest time.
- **Nothing retrospective is read:** no outcome, error or largest individual revision
  enters the ranking. Each snapshot's coverage is computed by the existing replay engine
  as of that snapshot, through the API's own `train_prediction`.
- **The search is exact but short:**
  - A SQL upper bound counts, per snapshot, the listings that pass the conditions every
    supported forecast must meet: upcoming, within 60 s of a served horizon, not an
    excluded line, a usable schedule match, and not a trip origin.
  - Snapshots are evaluated exactly in decreasing bound order. The search stops once
    the next bound is below the tenth-best supported count, because no remaining
    snapshot can then reach the top ten.
  - Every evaluated snapshot confirms its count did not exceed its bound.

## What the replay contains

- **Supported records only.** The exported boards list only trains for which the model
  returned `status: "ok"`. Stations and boarding groups without one are dropped, and
  every kept train keeps its ETA history.
- **Disclosure.** The export and the website carry this sentence: "This curated replay
  shows only trains eligible for the model’s 5-, 10- and 15-minute forecast windows."
  The model does not predict every BART train.
- **One retrospective condition.** A supported train is kept only if BART's final
  published ETA for it is known at tier A, the definition of the model's training and
  evaluation label.
  - It is needed so every train in the explorer can show what BART later published.
  - It reads no forecast, error or accuracy. Excluded supported trains are counted by
    reason.
  - Tests show that each kept train's forecast and history are the same bytes whatever
    happens after the snapshot. Only this condition and the final ETAs depend on later
    data.

## Files

The output directory is `data/static_replay/showcase/`, which Git ignores.

| Path | Public? | Contents |
|---|---|---|
| `replay/index.json`, `replay/v1-…/` | yes | The curated static replay, in the existing `static-replay-1` format. It passes `bart-static-replay check` |
| `showcase/showcase.json` | yes | Moment, selection, disclosure, the three terms, counts, provenance, and the SHA-256 of the other three files |
| `showcase/retrospective.json` | yes | Final published ETA, realized revision, model error and direction, per kept train. Kept apart from the replay files |
| `showcase/largest-changes.json` | yes | "Largest ETA changes in this replay": per horizon, at most five trains by absolute realized revision, one per trip run |
| `showcase/network-map.json` | yes | Every station served that day, with original schematic coordinates, routes and its forecast summary, or none; and one record per kept train (line, station, predicted and realized revision) so the map can be read line by line |
| `review/candidates.json` | no | The ten best snapshots and the scan's proof of completeness |
| `review/coverage.json` | no | Every board entry's status, the counts and the offline check |
| `review/included_records.csv` | no | Every kept record with its three ETAs |

The schemas are in [contracts/showcase/](contracts/showcase/) (Draft 2020-12), and tests
validate every file against them.

`publish` copies the public files into `web/public/replay/` and `web/public/showcase/`,
which Git tracks, byte for byte:

| Published | Bytes | SHA-256 |
|---|---|---|
| `showcase/showcase.json` | 3,171 | `989cfe66b0e7a0d5fa2a5e46281757db780807c89e94b10b1e88a42077a14b9a` |
| `showcase/retrospective.json` | 34,509 | `2089654d304051744b70ffdca04ecaa44e3b3f5a323f2524764a5d2cf0ac780e` |
| `showcase/largest-changes.json` | 12,230 | `3c126bf9ead49d6ddf544519ea1d590017a17384e427bf4b74a8b005629c4b9e` |
| `showcase/network-map.json` | 76,208 | `6b340baf448e46850786d991d6daa72e05c6020768a3f7975e7bb35d400be312` |
| `replay/`, export `v1-20261019T151023Z` | 150 files, 758,230 | manifest `cae7becfba2b69ec3556e4e9b0a5c4a5c0942683751827a81fd573e5c6e263e4`; the rest in [static_replay.md](static_replay.md#the-published-replay) |

## The network schematic

The map is an original octilinear schematic. It is not BART's map artwork, traced or
imitated, and it uses no BART logo.
- **Positions:** each station has a cell on a grid (`SCHEMATIC_GRID` in
  `static_replay/showcase.py`), with straight runs and 45-degree bends, north up.
  - The cells follow the station order of the GTFS route sequences, so neighbouring
    stations on a line are neighbouring cells.
  - The cells are 44 units apart, scaled into the view box the file names.
  - The build refuses a served station with no cell.
  - The GTFS latitude and longitude are kept in the file as well.
- **Routes:** each route's polyline is the longest station sequence of its trips that day.
  The website draws every track in one neutral grey and keeps colour for the data.
- **Why a grid:** a geographic projection was tried first. It left downtown San Francisco
  and the Oakland core unreadably dense, even after the stations were pushed apart.
- **Stations without a forecast:** they stay on the map, grey, with a count of 0 and no
  values.

## Limitations

- **One moment.** It is one fixed snapshot of one Monday. It illustrates the model and
  measures nothing in general. Evaluation results are in
  [eta_model_evaluation_2026-10-20.md](eta_model_evaluation_2026-10-20.md).
- **A subset of trains.** Only model-eligible trains at 5, 10 or 15 minutes are shown.
  Most trains on a board at any moment are outside those windows.
- **Circular reference.** The final published ETA is BART's own last stable estimate,
  not an observed arrival.
- **Small displayed differences.** Model errors of seconds are below the minute
  resolution of the times the site shows.

## Rebuilding

```bash
.venv/bin/python -m bart_reliability.static_replay.showcase build     # about 8 min; refuses an existing --out
.venv/bin/python -m bart_reliability.static_replay.showcase publish   # web/public/replay and web/public/showcase
.venv/bin/bart-static-replay check web/public/replay                  # offline: the replay and the showcase
```

`publish` goes through the existing replay `publish`, which runs the offline check. It then
copies the four showcase files, which must pass `check_showcase`:
- the files are exactly the four, with the SHA-256 values `showcase.json` lists;
- they belong to the replay's export and manifest;
- every record is a supported train of that replay, with the same values;
- the rankings are by realized revision, with at most five rows per horizon and one per
  trip run;
- no file uses the phrases that would describe a physical arrival.

The build refuses anything other than the pinned warehouse, bundle and model version.
