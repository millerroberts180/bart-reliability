# v1.0 release notes (draft)

Draft only: no tag or GitHub release has been created. The checklist at the end lists
what is left before publishing.

Proposed tag: `v1.0.0`, on the `main` commit that contains this file.

## What this release covers

This is the first complete version of the project:
- about ten days of BART GTFS-Realtime data, collected and checked;
- a Python and DuckDB pipeline that rebuilds how each published ETA changed;
- a chronological evaluation of models that predict the remaining change;
- a website for exploring a fixed historical replay.

Live demo: <https://millerroberts180.github.io/bart-reliability/>

The demo is a fixed replay of BART data as of Monday, October 19, 2026 at 8:10 AM
Pacific, not live data. It shows only trains the model supports at 5, 10 and 15 minutes
out. The model predicts revisions to BART's published ETA, not physical arrival times.

## Included

- A collector that polls BART's trip-update and alert feeds every 60 seconds, validates
  each response and stores it without overwriting anything.
- Conversion of the snapshots to hourly Parquet, and a DuckDB warehouse joined to the
  static schedule.
- SQL that finds each train's final stable estimate at each stop, and the revisions
  before it.
- Point-in-time features, two baselines, linear models and gradient-boosted trees,
  evaluated on a date-ordered split that was written down before fitting.
- The selected models, packaged as version `0.2.0+886fcd260732`, and a local FastAPI app
  that answers as of a past moment.
- A curated replay: the local app's answers at 8:10 AM on October 19 for the
  model-supported trains, with the final ETA BART published later for each, saved as
  JSON files. A React/Vite site on GitHub Pages shows them as highlights, an original
  network map and a train explorer ([showcase replay](showcase_replay.md)).

## Results

The test day was Monday, October 19, 2026, with 33,830 examples, and it was scored once
([evaluation](eta_model_evaluation_2026-10-20.md)):

| | Selected model | Historical baseline | No change | Model minus baseline (95% interval) |
|---|---|---|---|---|
| Mean absolute error (s) | 19.68 | 20.94 | 41.00 | −1.25 (−1.39 to −1.12) |
| Brier score, revision over 60 s | 0.1004 | 0.1110 | 0.1736 | −0.0106 (−0.0121 to −0.0091) |
| PR-AUC, revision over 60 s | 0.6027 | 0.5296 | 0.1736 | +0.0731 (+0.0599 to +0.0870) |

The intervals come from 2,000 bootstrap resamples of whole trips. The improvement is
consistent, but it is about 6% of the baseline's error, and it comes from one day.

The other results:
- On the same day, the model also beat the earlier version, which was trained on three
  days. Its mean absolute error was 0.36 s lower, with a 95% interval of 0.27 to 0.47 s.
- The model's 80% revision range covered 83.2% of test examples. That is inside the rule
  set before testing (within 5 points of 80%), so the range is included in the model
  bundle with provisional status.
- Collection completed 15,088 of 15,088 one-minute polls, and all 30,180 snapshots are
  valid. 27 fetches failed at first and succeeded on retry.

## Data, model and replay identifiers

| Item | Identifier |
|---|---|
| Final backup | Cutoff 2026-10-20 19:40:00 UTC; snapshots from 2026-10-10 08:11:07 to 2026-10-20 19:39:23 UTC; 30,180 files, 385,325,199 bytes; manifest SHA-256 `e74816ca44bbca95f767690553f852ff03aa62953fff58a2534a54f638b6f509` |
| Warehouse | `bart_checkpoint_2026-10-20.duckdb`, SHA-256 `19dd5cfc686bed4f223adbfe5c5d26ef8385e5d1a152da5aa2be7af9378e55cc` |
| Evaluation run | Commit `c2d504e` |
| Model bundle | `0.2.0+886fcd260732`, bundle ID `db2382848a9ff29a298aa6d320623daf532ac4d813475bf30a8e052e84ed6087` |
| Published replay | `web/public/replay/`, export `v1-20261019T151023Z`, replay time 2026-10-19T15:10:23Z, 150 files, 758,230 bytes |
| Replay hashes | `index.json` `563a705749166ecffe27cf992b5f55d3d3f0ce27bc3bcd53d7fb5e6e22c3f606`; manifest `cae7becfba2b69ec3556e4e9b0a5c4a5c0942683751827a81fd573e5c6e263e4`; tree `c9cbad518e865a9c0ca2397dedbc83026494fdd1a03974ef72b50c778fed043b` |
| Showcase files | `web/public/showcase/`, 4 files, 126,118 bytes; `showcase.json` `989cfe66b0e7a0d5fa2a5e46281757db780807c89e94b10b1e88a42077a14b9a`, which lists the other three files' SHA-256 values |

The raw data, warehouse and model files stay out of the repository, under the ignored
`data/`. The release attaches no files beyond GitHub's source archives.

## Status

Collection ended intentionally after the final backup above was verified, and the
DigitalOcean server used for collection was retired. The public site is static files on
GitHub Pages and does not depend on any server ([deployment notes](deployment.md#status-retired)).

## Limitations

- The labels measure revisions to BART's published ETAs, not physical arrivals. BART
  publishes no independent arrival data.
- The public site is a fixed replay of one moment. Its final published ETA is BART's own
  last stable estimate, not an observed arrival.
- The final evaluation covers one Monday. It can't show how the model does on other
  days, weekends or disrupted service.
- The data covers about ten days in one season, and there is no data after the backup
  cutoff.
- Only part of the service is modelled. At the replay moment, 89 of 1,067 trains have a
  supported forecast. The site shows the 83 whose final published ETA is known, and no
  other trains.
- The earlier model's classifier had lower calibration error than the new one.

## Not in this release

- Live data or a public prediction API.
- The rider-weighted analysis described in the project specification.
- More test days. These would need a new collection.

## Data credit

The data comes from BART's GTFS and GTFS-Realtime feeds (San Francisco Bay Area Rapid
Transit District), used under the
[BART Developer License Agreement](https://www.bart.gov/schedules/developers/developer-license-agreement).
This is an independent project. It is not an official BART product, and it is not
affiliated with or endorsed by BART.

## Before publishing

1. Merge the branch that adds this file into `main`, and confirm that CI and the Pages
   deployment pass.
2. Check the live site again on the deployed commit.
3. Decide whether to change the package versions. `pyproject.toml` and
   `web/package.json` are still `0.1.0`.
4. Tag the release commit `v1.0.0`, and publish the release from this file, without the
   draft note and this checklist.
