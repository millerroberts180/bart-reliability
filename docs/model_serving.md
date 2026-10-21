# Local model serving: the inference bundle

The bundle packages the selected ETA revision models
([modeling_plan.md](modeling_plan.md)) for local inference. It is **not** an API; the
local replay API ([local_api.md](local_api.md)) loads one. Every prediction is
**provisional**. Two bundles exist:

- **PR #7 bundle** `0.1.0+8d942e17429c` (`data/models/eta_revision_bundle/`). Trained on
  three service days and evaluated on 2026-10-14. The local API still serves it.
- **2026-10-20 bundle** `0.2.0+886fcd260732` (`data/models/eta_revision_bundle_2026-10-20/`).
  The retrained models, packaged from the frozen evaluation run
  ([below](#the-2026-10-20-bundle)). It is not yet connected to the API.

The models predict how BART's published ETA will still be revised:
`predicted_final_published_eta` is BART's own final published estimate, not a physical
arrival time.

## Rebuilding

```bash
bart-eta-bundle build --db data/warehouse/<snapshot>.duckdb
```

The build runs these steps:

1. Runs the modeling pipeline (`bart-eta-model`, the same code and
   `config/eta_model.toml`) into the model config's `output_dir`.
2. Copies the two selected fitted pipelines byte for byte. Each pipeline includes its
   encoders and scaler.
3. Calibrates the provisional interval on validation residuals ([below](#revision-interval)).
4. Writes `bundle.json`.
5. Loads the bundle through the same verification a consumer uses.
6. Checks parity with the pipeline's own `predictions.parquet`:
   - in batch for every validation and test row;
   - one record at a time for 500 evenly spaced rows.
7. Replaces the output directory atomically.

Any mismatch stops the build. Nothing in `bundle.json` depends on paths or wall-clock
time, and the fitted models are byte-identical for a given seed. Rebuilding from the same
warehouse and configs therefore reproduces the bundle exactly.

| Option | Default |
|---|---|
| `--config` | `config/eta_model.toml` (models, features, splits) |
| `--bundle-config` | `config/eta_model_bundle.toml` (name, version, interval rule) |
| `--run-dir` | the config's `output_dir` |
| `--out-dir` | the bundle config's `output_dir` (`data/models/eta_revision_bundle_2026-10-20`) |
| `--from-run` | none: run the pipeline (below) |

Both output directories are git-ignored. Only the code, the configs and the committed
schema are versioned.

### Packaging a frozen run

```bash
bart-eta-bundle build --from-run data/models/eta_revision_2026-10-20
```

`--from-run` skips step 1. It packages a finished modeling run as it is: nothing is
refitted, reselected or re-evaluated, and nothing is written to the run directory, which
may be read-only. Steps 2 to 7 are the same, and parity is checked against that run's
`predictions.parquet`.

The run's recorded model configuration must equal `config/eta_model.toml`, except where
the run was written and which locked models it was compared with. Otherwise the build
stops, so the metadata always describes the run being packaged.

The interval's test coverage is computed in this step, from the run's stored test
predictions.

## Bundle contents

| File | Contents |
|---|---|
| `regression.joblib` | Selected regression pipeline, with preprocessing (`tree_hgb_leaves=31` in both bundles) |
| `classification.joblib` | Selected large-revision classifier, with preprocessing (`tree_hgb_leaves=15` in PR #7, `tree_hgb_leaves=31` in 2026-10-20) |
| `bundle.json` | Metadata, validated against `config/eta_model_bundle.schema.json` |

The committed schema is the contract. Its constants pin:

- the feature names, types and order (`feature_schema_version = eta-revision-features-1`);
- the record's context fields;
- the input domain;
- the fallback policy.

A build fails if `config/eta_model.toml` selects other features. Changing the features or
the input domain requires a new `feature_schema_version`. Changing the fallback policy
requires a new `bundle_format_version` (now 2).

`bundle.json` records:

- **artifacts:** filename, role, size and SHA-256 of each artifact;
- **environment:** Python and library versions;
- **features:** name, kind, input type and model dtype, in model order;
- **categorical handling:** the categories known from training, and the mechanism each
  model uses for unseen values;
- **fallback behavior:** what happens to each kind of invalid or unusual input;
- **training data:**
  - the warehouse range;
  - the frame fingerprint;
  - the train, validation and test service dates;
  - `training_data_cutoff_utc`: the last label confirmation used to fit the models;
  - `calibration_data_cutoff_utc`: the same for the interval;
- **model configuration:** the modeling and bundle settings, and the selected estimators'
  parameters;
- **interval:** the calibration and its test evaluation;
- **verification:** the parity results;
- **identity:** the model version (`0.1.0+<12 hex characters>`, hashed from the artifacts
  and the feature contract) and `bundle_id`, a SHA-256 of all other metadata.

### Verification on load

`load_predictor(bundle_dir)` refuses the bundle unless all of these hold:

1. **Files.** The directory contains exactly `bundle.json` and the listed artifacts.
2. **Schema.** `bundle.json` satisfies the committed schema, and `producer` is
   `bart-reliability`.
3. **Identity.** `bundle_id` equals the hash of the rest of the metadata, so no field
   was edited.
4. **Environment.** Python and numpy match by major.minor, and scikit-learn matches
   exactly.
5. **Hashes.** Every artifact's size and SHA-256 match, checked **before** it is
   unpickled.
6. **Models.** Each artifact is a scikit-learn Pipeline holding the recorded estimator
   class of the right kind (regressor or classifier), with exactly the schema's input
   columns in order.

Unpickling executes code. A hash recorded next to the artifacts detects corruption and
accidental mismatches, but not a deliberate replacement of both. Only load bundles that
`bart-eta-bundle build` wrote into a directory you control. Pin a known build with
`expected_bundle_id` (`bart-eta-bundle verify` prints it).

## Using it

The one supported entry point:

```python
from bart_reliability.serving import load_predictor

predictor = load_predictor("data/models/eta_revision_bundle", expected_bundle_id="cd2674…")
response = predictor.predict(record)
```

Or from the shell: `bart-eta-bundle predict --record record.json` (use `-` for stdin).

### Record

A record is a flat mapping with **exactly** these 18 fields. Each feature uses the
definition in [modeling_plan.md](modeling_plan.md#allowed-features), computed from the
snapshot and earlier snapshots only.

| Field | Type | Rule |
|---|---|---|
| `feature_schema_version` | string | `eta-revision-features-1` |
| `snapshot_collected_at` | ISO-8601 with offset | When the feed snapshot was collected |
| `published_eta` | ISO-8601 with offset | BART's published arrival time for this trip and stop in that snapshot |
| `published_horizon_s` | number | Must equal `published_eta − snapshot_collected_at` in whole seconds |
| `published_minus_scheduled_s`, `stop_position`, `stops_away`, `seconds_since_first_seen`, `eta_change_last_snapshot_s`, `eta_change_last_5min_s`, `eta_change_since_first_seen_s`, `prior_change_count`, `prior_abs_change_sum_s` | number | Finite |
| `published_horizon_bucket_s` | integer | 300, 600 or 900, and within 60 s of `published_horizon_s` |
| `route_short_name`, `stop_id`, `service_day_type` | string | Non-empty |
| `hour_local` | integer | Pacific hour of `snapshot_collected_at` |

No field is ever required that is known only after the snapshot. Labels, final
estimates, event identifiers and observations from later snapshots are not accepted.

**Fallback behavior** (pinned by the schema):

| Input | Result |
|---|---|
| Missing field, unexpected field (for example `final_stable_estimate`), null, NaN or infinity, wrong type, other feature-schema version | Rejected (`RecordError`); nothing is filled in |
| `published_horizon_s` or `hour_local` inconsistent with the timestamps | Rejected |
| Published time remaining outside 300/600/900 ± 60 s | Rejected: the models were trained only on these published-time horizons |
| Valid record with any categorical value unseen in training: a new route or stop, or an hour with no training service | `status: "fallback_required"` (see below). No prediction, probability or interval |
| Interval unavailable | Bounds are `null` with the reason; supported point predictions are still returned |

### Unknown categories: fallback required

The models have shown nothing about inputs they never saw in training. A record that
passes every check above, but has any categorical value outside `known_categories`, is
therefore **outside demonstrated model support**. The response then has:

- `status`: `"fallback_required"`;
- `reason`: `"input outside demonstrated model support"`;
- `unknown_categories`: every unseen value, as `{"feature": ..., "value": ...}`;
- `model` (name, version, `bundle_id`) and `feature_schema_version`;
- `predicted_eta_revision_seconds`, `probability_absolute_revision_over_60_seconds` and
  `predicted_final_published_eta` all `null`, and `revision_intervals` empty;
- `fallback`: `{"action": "use_published_eta", "eta": <published_eta>}`.

The future API should then show **BART's unadjusted published ETA**. It must not
substitute the trees' missing-value path. The models can technically score such a
record, but nothing has shown that score to be meaningful. Records with only known
categories are unaffected and return `status: "ok"` with exactly the same predictions as
before. This rule changed the bundle format to `bundle_format_version` 2; bundles in the
old format are refused.

### Response

Both statuses return the same set of keys.

| Field | Meaning |
|---|---|
| `status`, `reason` | `"ok"` with `reason` `null`, or `"fallback_required"` with its reason |
| `predicted_eta_revision_seconds` | Predicted final stable estimate − `published_eta` (positive: the ETA will move later) |
| `probability_absolute_revision_over_60_seconds` | Predicted probability that the revision exceeds 60 s either way |
| `predicted_final_published_eta` | `published_eta` + predicted revision, UTC, rounded to the second |
| `model` | Name, version, `bundle_id`, and the selected regression and classification candidates |
| `training_data_cutoff`, `calibration_data_cutoff` | Last label confirmation used to fit the models, and to calibrate the interval |
| `feature_schema_version` | The schema the record was checked against |
| `revision_intervals` | List of interval estimates, one per method (one today) |
| `unknown_categories` | Unseen `{"feature", "value"}` pairs; empty when `status` is `"ok"` |
| `fallback` | `null`, or the published ETA to use instead |
| `provisional` | Always `true` for now |

Each `revision_intervals` entry carries:

- `method` and `status`;
- `nominal_coverage` and `available`, with `unavailable_reasons`;
- `lower_revision_seconds` and `upper_revision_seconds`;
- `lower_final_published_eta` and `upper_final_published_eta`;
- `empirical_test_coverage`: overall and for this horizon, with a trip-clustered 95%
  interval;
- `calibration`: its provenance, including whether it was reused for model selection;
- `calibration_examples_this_horizon` and `residual_quantiles_this_horizon_s`;
- `independently_calibrated`.

An independently calibrated interval is planned for when more days exist. It would be
calibrated on days used neither for selection nor for testing, and would be added as a
second entry with `independently_calibrated: true`. Consumers should pick an entry by
`method` and `available`, not by position.

Example, from a test-day snapshot. These are real values, shown only to illustrate the
format:

```json
{"published_eta": "2026-10-14T20:04:29Z",
 "predicted_eta_revision_seconds": 41.24,
 "probability_absolute_revision_over_60_seconds": 0.114,
 "predicted_final_published_eta": "2026-10-14T20:05:10Z",
 "revision_intervals": [{"available": true, "nominal_coverage": 0.8,
   "lower_revision_seconds": 18.44, "upper_revision_seconds": 87.49,
   "lower_final_published_eta": "2026-10-14T20:04:47Z",
   "upper_final_published_eta": "2026-10-14T20:05:56Z", "...": "..."}]}
```

## Revision interval

This is a provisional, horizon-aware residual interval. For each published-time horizon,
the bounds are the predicted revision plus the 10th and 90th percentiles of the selected
regression model's residuals (actual minus predicted revision). The lower tail takes the
observed residual at or below that percentile, and the upper tail the one at or above it.

**Calibration data** (PR #7 bundle; for the 2026-10-20 bundle see
[below](#the-2026-10-20-bundle)):

- The **validation** split (service date 2026-10-13): 30,623 examples, about 10,200 per
  horizon.
- The model was fitted on training rows only, so these residuals are out of sample.
- **The same day also selected the model** (validation MAE among five regression
  candidates), so the calibration is not independent of model selection.
- Test outcomes are never used to fit the interval.

**Availability rule.** Declared in `config/eta_model_bundle.toml` before any test coverage
was computed. The interval is served only if:

- every horizon has at least 1,000 calibration examples; and
- test coverage is within 0.05 of the nominal 0.80, overall and for every horizon.

Otherwise the bounds are `null`. Test outcomes enter only this check and the coverage
report.

**Results for the 2026-10-15 snapshot** (test day 2026-10-14; 625 trips, 33,412
examples):

| Published-time horizon | Residual quantiles (s) | Mean width (s) | Validation coverage | Test coverage | Trip-clustered 95% interval |
|---|---|---|---|---|---|
| 5 min | −17.1 to +23.3 | 40.4 | 0.800 | 0.796 | 0.786 to 0.805 |
| 10 min | −22.8 to +46.3 | 69.1 | 0.800 | 0.800 | 0.788 to 0.811 |
| 15 min | −25.6 to +69.3 | 94.9 | 0.800 | 0.809 | 0.796 to 0.822 |
| Overall | | | | 0.802 | 0.791 to 0.812 |

The rule is met, so the interval is **available, with provisional status**. Its limits:

- It rests on one calibration day and one test day.
- It is conditional on those days' conditions.
- It is not independent of model selection.
- It does not show coverage on other days. Validation (Tuesday) had much heavier tails
  than test.

### The test day is no longer untouched

October 14 (2026-10-14) has now been used for two things: evaluating the selected
models, and deciding whether this interval may be served. It must not be described as an
untouched holdout for any later model version. A new model, feature set, interval method
or availability rule needs evaluation on **later service days** that played no part in
those decisions. The interval stays provisional for two reasons: its calibration reused
the model-selection day (2026-10-13), and its evaluation covers only October 14. Each
bundle records this in `training_data.test_day_status`. The next version's sealed test
day, 2026-10-19, and the rule for this interval there were
[preregistered](modeling_plan.md#preregistered-evaluation-2026-10-20-checkpoint). The
retrained models have been evaluated on it once
([eta_model_evaluation_2026-10-20.md](eta_model_evaluation_2026-10-20.md)). The bundle
has not been rebuilt, so the served models are still the PR #7 ones.

## Parity and determinism

On the 2026-10-15 snapshot (bundle format 2, model version `0.1.0+8d942e17429c`,
`bundle_id` `cd267407788558dd…`):

- **Batch.** Bundle predictions equal the pipeline's for all 64,035 validation and test
  rows, with a maximum absolute difference of 0 for both models. All 64,035 rows have
  only known categories.
- **Single record.** One-record predictions equal batch predictions for all 500 sampled
  rows; none needed fallback. The tests check every row of the synthetic sample.
- **Determinism.** Two builds into different run and bundle directories produced
  byte-identical `bundle.json`, `regression.joblib` and `classification.joblib`.
- **Unchanged by the fallback rule.** The model files and interval are byte-identical to
  the format-1 bundle. Supported records get exactly the same predictions as before.

The model version hashes only the artifacts and the feature contract. Descriptive
metadata, calibration or policy changes alter `bundle_id` but not the model version.

## The 2026-10-20 bundle

These are the retrained models, approved for promotion after the preregistered evaluation
([eta_model_evaluation_2026-10-20.md](eta_model_evaluation_2026-10-20.md)).
- **How it was built.** It was packaged from the frozen run
  `data/models/eta_revision_2026-10-20/` with `bart-eta-bundle build --from-run`. Nothing
  was refitted, reselected or re-evaluated, and the run directory was not written. Its
  model files are byte-identical to the run's selected models.
- **Not yet in use.** The local API still loads the PR #7 bundle.

| | |
|---|---|
| Directory | `data/models/eta_revision_bundle_2026-10-20/` (ignored, read-only) |
| Model version | `0.2.0+886fcd260732` |
| Bundle ID | `db2382848a9ff29a298aa6d320623daf532ac4d813475bf30a8e052e84ed6087` |
| Bundle format / feature schema | 2 / `eta-revision-features-1`, both unchanged |
| Regression | `tree_hgb_leaves=31` (`HistGradientBoostingRegressor`), `regression.joblib`: 1,427,289 bytes, SHA-256 `cdfaa60609eeb15745133a77e62f74a73f3825e60250d4edf861b2e2f24ee917` |
| Classification | `tree_hgb_leaves=31` (`HistGradientBoostingClassifier`), `classification.joblib`: 1,489,289 bytes, SHA-256 `a89547ce41224f997280ec72b4ba32bd9a51f7ae9a1a3199d14fb31856de950d` |
| `bundle.json` | 14,547 bytes, SHA-256 `60f14143548fb4f1911ca051807e8ee4c8f165f3ee52f41f4736c803ee2aab30` |
| Training | 2026-10-10 to 10-15. Last label 2026-10-16 08:55:23 UTC (`trainedThrough`) |
| Validation (selection and interval calibration) | 2026-10-16 to 10-18. Last label 2026-10-19 08:52:23 UTC |
| Test | 2026-10-19, used once by the evaluation and by this interval check, and now spent |
| Environment | Python 3.13.3, scikit-learn 1.9.1, numpy 2.5.4, pandas 3.0.6, joblib 1.6.0, DuckDB 1.5.6 |

**Interval decision.** The method and availability rule are unchanged from
[above](#revision-interval):
- **Method:** 10th and 90th percentile residuals on validation (83,012 examples).
- **Rule:** served only with at least 1,000 calibration examples per horizon, and test
  coverage within 0.05 of 0.80 overall and per horizon.
- **The check:** the permitted 2026-10-19 coverage check was computed once, in this
  build.

| Published-time horizon | Calibration examples | Residual quantiles (s) | Mean width (s) | Validation coverage | 2026-10-19 coverage | Trip-clustered 95% interval |
|---|---|---|---|---|---|---|
| 5 min | 27,686 | −19.2 to +21.9 | 41.1 | 0.8000 | 0.8299 | 0.8200 to 0.8392 |
| 10 min | 27,669 | −26.5 to +40.4 | 66.8 | 0.8001 | 0.8307 | 0.8183 to 0.8429 |
| 15 min | 27,657 | −30.3 to +61.9 | 92.2 | 0.8001 | 0.8345 | 0.8209 to 0.8473 |
| Overall | 83,012 | | | | 0.8317 | 0.8207 to 0.8421 |

Every coverage is within 0.05 of 0.80, so the interval is **available, with provisional
status**. On the test day it over-covered: at about 0.83, the trip-clustered intervals
exclude 0.80. The bounds were somewhat wider than needed on a day with smaller revisions.
The rule was applied as written, and nothing was adjusted after the coverage was seen.

**Verification:**

- **Batch parity.** Bundle predictions equal the frozen run's `predictions.parquet` for
  all 116,842 validation and test rows. The maximum absolute difference is 0 for both
  models, and every row has only known categories.
- **Single record.** All 500 evenly spaced rows give identical predictions, and none
  needed fallback.
- **Known categories return `ok`.**
  - All 116,842 validation and test records validate with no unseen category.
  - An evenly spaced sample of 3,000 returns `status: "ok"`, with the frozen predictions
    and an interval.
  - The bundle knows 84 stops, 10 routes, 23 Pacific hours (all but 03), 3 service-day
    types and 3 horizons.
- **Unseen categories fall back.** Each of these was checked on a real test record:
  - an unseen route (`Purple-N`);
  - an unseen stop (`Z99-1`);
  - hour 3, the only in-domain Pacific hour absent from training;
  - service-day type `holiday`;
  - all four at once.

  Each returns `fallback_required`, with null revision, probability and final ETA, no
  interval, the unseen features listed, and BART's published ETA as the fallback. A
  horizon outside 300 / 600 / 900 is rejected as invalid instead.
- **Backward compatible with the website.**
  - The committed bundle schema is unchanged.
  - The local API ran in-process against the checkpoint warehouse and this bundle, at the
    website fixture's replay time (2026-10-15 17:00 UTC).
  - It answered all 50 requests recorded in `web/src/data/fixtures/apiReplay.json` with
    200. The response shapes equal the fixture's, and every response passes the
    TypeScript contract check the API tests use.
- **The packaging path.** Packaging the PR #7 run the same way reproduced the PR #7
  bundle's model version, artifacts, interval and parity. Only `bundle_id` differed,
  because of the configuration's new `locked_comparison` key and the parity reference
  label.

**Before the API uses this bundle.** The API's default replay time, 2026-10-15 17:00 UTC,
falls inside this bundle's training period (`trainedThrough` 2026-10-16 08:55 UTC). A
replay there would show a model trained on that day. When switching bundles, move `as_of`
after 2026-10-16 08:55 UTC, for example to 2026-10-20, which no model used.

**Limitations of this bundle:**
- **One test day.** The evaluation and the interval coverage both come from Monday
  2026-10-19 alone. They do not establish long-term generalization.
- **Classifier calibration.** The retrained classifier was less well calibrated than PR
  #7's on the test day (expected calibration error 0.0263 against 0.0137). It predicted
  somewhat too high below 0.5.
- **Calibration not independent.** The interval was calibrated on the model-selection
  days.

## Limitations

- **Provisional.**
  - PR #7: three training days, one validation day and one test day, and the test day
    has been used (see [above](#the-test-day-is-no-longer-untouched)).
  - 2026-10-20: six training days, three validation days and one spent test day
    (see [above](#the-2026-10-20-bundle)).
- **ETA revision only.** The target is BART's final published estimate, not physical
  arrival.
- **Narrow domain.** Only published-time horizons near 5, 10 and 15 minutes are served,
  and only for tier A–like conditions; eligibility is judged after the event.
- **Environment.** A bundle loads only under the Python, numpy and scikit-learn versions
  it was built with. Rebuild after upgrading.
