# Local model serving: the inference bundle

The bundle packages the selected ETA revision models
([modeling_plan.md](modeling_plan.md)) for local inference. It is **not** an API, and
nothing connects it to the website yet. Every prediction is **provisional**. The models
were trained on three service days and evaluated on one. They predict how BART's
published ETA will still be revised: `predicted_final_published_eta` is BART's own final
published estimate, not a physical arrival time.

## Rebuilding

```bash
bart-eta-bundle build --db data/warehouse/<snapshot>.duckdb
```

The build runs these steps:

1. Runs the modeling pipeline (`bart-eta-model`, the same code and
   `config/eta_model.toml`) into `data/models/eta_revision/`.
2. Copies the two selected fitted pipelines byte for byte. Each pipeline includes its
   encoders and scaler.
3. Calibrates the provisional interval on validation residuals ([below](#revision-interval)).
4. Writes `bundle.json`.
5. Loads the bundle through the same verification a consumer uses.
6. Checks parity with the pipeline's own `predictions.parquet`:
   - in batch for every validation and test row;
   - one record at a time for 500 evenly spaced rows.
7. Replaces `data/models/eta_revision_bundle/` atomically.

Any mismatch stops the build. Nothing in `bundle.json` depends on paths or wall-clock
time, and the fitted models are byte-identical for a given seed. Rebuilding from the same
warehouse and configs therefore reproduces the bundle exactly.

| Option | Default |
|---|---|
| `--config` | `config/eta_model.toml` (models, features, splits) |
| `--bundle-config` | `config/eta_model_bundle.toml` (name, version, interval rule) |
| `--run-dir` | the config's `output_dir` |
| `--out-dir` | `data/models/eta_revision_bundle` |

Both output directories are git-ignored. Only the code, the configs and the committed
schema are versioned.

## Bundle contents

| File | Contents |
|---|---|
| `regression.joblib` | Selected regression pipeline (`tree_hgb_leaves=31`), with preprocessing |
| `classification.joblib` | Selected large-revision classifier (`tree_hgb_leaves=15`), with preprocessing |
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

**Calibration data:**

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

## Limitations

- **Provisional.** Three training days, one validation day and one test day, and the test
  day has now been used (see [above](#the-test-day-is-no-longer-untouched)).
- **ETA revision only.** The target is BART's final published estimate, not physical
  arrival.
- **Narrow domain.** Only published-time horizons near 5, 10 and 15 minutes are served,
  and only for tier A–like conditions; eligibility is judged after the event.
- **Environment.** A bundle loads only under the Python, numpy and scikit-learn versions
  it was built with. Rebuild after upgrading.
