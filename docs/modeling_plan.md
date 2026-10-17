# ETA revision modeling plan

This milestone builds a leakage-safe pipeline that predicts how much BART's published ETA
will still be revised. It is **not** an arrival-accuracy model. The reference endpoint is
BART's own final stable published estimate ([observed_arrival_proxy.md](observed_arrival_proxy.md)),
so every target here is an *ETA revision*. Results from the current snapshot are
**provisional development results** and do not describe BART performance in general.

## Development snapshot

A read-only copy of the production collector's raw files, taken without stopping or
modifying the collector.

| | |
|---|---|
| Server file listing (cutoff) | 2026-10-15 20:18:32 UTC (13:18 PDT) |
| Files | 15,858: 7,929 trip-update and 7,929 alert snapshots, SHA-256 verified against the server |
| Collected | 2026-10-10 08:11:07 UTC to 2026-10-15 20:18:23 UTC (132.1 h) |
| Invalid files | 0 (every file parsed and validated with the collector's `validate_feed`) |
| Polling gaps | none over 90 s. Spacing was 57 to 63 s, except 32 s and 44 s at the two restarts (reboot on 10-10, `needrestart` on 10-11) |
| Coverage | 100% of 60 s intervals per feed; 1,991 alert snapshots were valid empty feeds |
| Complete service dates | 2026-10-10 (Sat) to 2026-10-14 (Wed). 10-09 is a 40-minute late-night tail; 10-15 ends at the cutoff |

The snapshot lives under the ignored `data/raw/server_exports/2026-10-15/`, with a
`snapshot_manifest.json` and the server-side SHA-256 list. Rerunning on a newer snapshot
uses the same commands (see [Rerunning](#rerunning)).

## Prediction targets

Each modeling example is one eligible stop-arrival event at one published-time horizon:

1. **`eta_revision_seconds`** (regression) = final stable estimate − estimate published at
   the prediction snapshot. Positive means the ETA later moved later.
2. **`large_revision`** (classification) = `absolute_eta_revision_seconds > 60`. The
   threshold is `large_revision_threshold_s` in `config/eta_model.toml`.

### Published-time horizons

The 5, 10 and 15 minute horizons are **published-time horizons**. At the prediction
snapshot, BART's own ETA said the train was about 300, 600 or 900 s away
(`published_horizon_s`, within ±60 s, using `horizon_targets_s` and `horizon_tolerance_s`
from `config/eta_revision.toml`). They describe what BART was publishing, not
independently observed time before physical arrival. For each event and horizon, the
snapshot closest to the target is chosen, and ties go to the earlier snapshot.

The descriptive dataset `eta_revision_examples` instead chooses horizons by time to the
*final* estimate. That selection uses the outcome. On that table,
`eta_revision_seconds = time_to_proxy_s − published_horizon_s` holds exactly, so the
bucket plus the published time remaining nearly determines the label. On the 2-day
export, examples whose published time remaining was more than 120 s from their bucket were
100% large revisions, and those within 60 s were 4.7%. Choosing by published-time horizon uses
only information available at the snapshot. On the current snapshot, the share of large
revisions is flat across distance from the target: 8.8% vs 8.3% at 5 minutes, and 22.2%
vs 23.1% at 10 minutes. `eta_revision_examples` is unchanged and remains the descriptive
dataset.

Two rules carry over from the descriptive dataset, and both depend on the event's end:

- **Final-window rule.** The final `stability_window` estimates that define the endpoint
  are never used as prediction snapshots. On the development snapshot this affects 18 of
  about 175,000 event-horizons: 14 use the next-closest estimate, and 4 have no example.
- **Eligibility and tier.** Only eligible events are modeled, and by default only tier
  A. Both are label-quality filters judged after the event. At inference time eligibility
  is unknown, so the results describe events that end with a stable, confirmed final
  estimate.

## Allowed features

Features are built in SQL (`src/bart_reliability/modeling/features.py`) into the DuckDB
table `eta_model_features`. Every value comes from the prediction snapshot or earlier
snapshots, or from the static schedule. The code keeps a catalog of allowed features, and
the configuration can only select from it.

**Selected by default:**

| Feature | Type | Definition | Why it is known at inference time |
|---|---|---|---|
| `published_horizon_bucket_s` | cat | 300 / 600 / 900 published-time horizon bucket | Derived from the current published ETA |
| `published_horizon_s` | num | Published ETA − snapshot collection time | Both are in the current snapshot |
| `published_minus_scheduled_s` | num | Published ETA − static scheduled arrival | Current ETA and the published schedule |
| `route_short_name` | cat | Route (encodes direction for BART, e.g. Yellow-S) | Static trip attribute |
| `stop_id` | cat | Platform stop | Static |
| `stop_position` | num | Position of the stop in the trip | Static schedule |
| `stops_away` | num | Stop position − first stop position the trip lists in this snapshot | Current snapshot |
| `hour_local` | cat | Pacific hour of the snapshot | Clock time |
| `service_day_type` | cat | weekday / saturday / sunday, from the trip's static service calendar | Static schedule |
| `seconds_since_first_seen` | num | Snapshot time − first time this trip-stop was listed | Earlier snapshots |
| `eta_change_last_snapshot_s` | num | Current ETA − ETA in the previous listing | Previous snapshot |
| `eta_change_last_5min_s` | num | Current ETA − earliest ETA listed in the trailing 300 s | Trailing window ending at the snapshot |
| `eta_change_since_first_seen_s` | num | Current ETA − first listed ETA | Earlier snapshots |
| `prior_change_count` | num | Listings so far whose ETA differed from the previous listing | Earlier snapshots |
| `prior_abs_change_sum_s` | num | Sum of absolute ETA changes so far | Earlier snapshots |

**Computed but not selected** (still checked for leakage, and can be enabled in config):

| Feature | Why it is not selected now |
|---|---|
| `missing_snapshots_so_far` | Snapshots since first seen in which this stop was not listed. Always 0 under tier A, which requires no missing snapshots over the whole event. It becomes informative only if tier B is modeled |
| `snapshot_gap_before_s`, `max_snapshot_gap_last_15min_s` | Eligibility already removes events with gaps over 90 s, and the snapshot has no gap over 90 s, so these barely vary |
| `has_applicable_visible_alert`, `alert_context_group` | Point-in-time alert state, using the same rule as [service_alerts.md](service_alerts.md). In this sample it mostly identifies the date (no alert on Oct 10–11; one planned notice on 97% of Oct 14). New alert versions stay `unclassified` until manually reviewed, so the categories also depend on review timing. |

**Considered and not built:**

| Feature | Why not |
|---|---|
| Day of week | Each day appears once; the test day never appears in training. `service_day_type` keeps the schedule regime |
| Feed `arrival_uncertainty_s` | Constant (30 s) in every row |
| Feed age (collection − header time) | 0 to 2 s throughout |
| Trip ID, event ID | Identifiers (see prohibited fields) |
| Recent realized revisions on the route | Requires other events' outcomes, which are known only after confirmation; deferred |

## Prohibited leakage fields

The model frame rejects these columns, and the config loader refuses them by name:

- **The endpoint:** `final_stable_estimate`, `proxy_arrival`, `last_estimate_arrival`,
  `final_estimates`, `final_estimate_spread_s`, `uncertainty_s`.
- **The target and its derivatives:** `eta_revision_seconds`,
  `absolute_eta_revision_seconds`, `revision_direction`, `large_revision`,
  `time_to_proxy_s`.
- **The outcome-anchored horizon:** `target_horizon_s`. It is chosen using the final
  estimate.
- **Observations after the snapshot:** `last_seen_at`, `confirmed_absent_at`,
  `confirmed_absent_feed_timestamp`, `next_snapshot_min_stop_position`,
  `observation_count`, `snapshots_in_span`, `stop_missing_snapshots`,
  `trip_missing_snapshots`, `max_collection_gap_s`, `listed_after_estimate_s`,
  `confirmed_absent_after_estimate_s`, `disappearance_window_s`,
  `observation_rank_from_end`, `horizons_available`.
- **Label-quality flags:** `quality_tier`, `is_eligible`, `exclusion_reason`.
- **Future alert state:** any alert snapshot newer than the prediction snapshot. The
  point-in-time join cannot produce one, and a check verifies it.
- **Aggregates using validation or test outcomes:** the historical baseline is fitted on
  training rows only. The models' encoders and scalers are fitted inside each model on
  training rows.
- **Identifiers that encode the event:** `event_id`, `trip_id`, `snapshot_index`, and raw
  timestamps.

## Leakage controls

**Primary controls.** These are structural, and a failure stops the run:

1. **Prohibited-field catalog and allowlist.** The configured features must come from
   the point-in-time catalog, no prohibited name may be selected, and the columns passed
   to every model must equal the configured features.
2. **Point-in-time SQL checks** (`eta_model_feature_checks`):
   - the last history row used is the prediction snapshot itself;
   - the trailing-window source is not before `t − 300 s`;
   - the alert snapshot is not newer than the prediction;
   - the reconstructed history matches each event's observation count;
   - no prediction snapshot falls in the final window;
   - each published-time horizon is within tolerance of its bucket;
   - there is exactly one row per event and bucket.
3. **Split isolation.** No event appears in two splits. Every training label is confirmed
   before the first validation prediction, and every validation label before the first
   test prediction.
4. **Train-only aggregation.** The historical baseline refuses rows that are not training
   rows. That includes every sensitivity setting.
5. **Perturbation tests** (test suite):
   - Changing estimates published after a prediction snapshot must leave that example's
     features unchanged.
   - Changing validation or test labels must leave the fitted baselines (every
     sensitivity setting) and the models unchanged.

**Diagnostic alarm.** Each feature alone is scored for large revisions on training rows
(ROC-AUC). The run stops at 0.95 or above, because one input that strong would be
suspicious. This is an alarm, not proof that leakage is absent: it cannot see leaks that
act through combinations of features.

The outcome-anchored horizons show the gap. On `eta_revision_examples` (tier A, 2026-10-15
snapshot), the bucket alone scores 0.673 and the published time remaining alone 0.53, so
the alarm passes both. Their combination, the distance from bucket to published time,
scores 0.963. On the development run the highest single feature is 0.75: `stop_id`,
scored optimistically by its training-row rate.

## Split strategy

The split is chronological by service date. Each event belongs to one service date, so
all of its horizons stay in one split, and rows are never split randomly. BART's overnight
break falls between service dates, so boundaries cross no running service. An event whose label
is confirmed after the next split's first prediction is purged (`crosses_split_boundary`)
and counted.

| Split | Service dates (config) | Days |
|---|---|---|
| train | 2026-10-10 to 2026-10-12 | Sat, Sun, Mon (Mon ran weekday service) |
| validation | 2026-10-13 | Tue |
| test | 2026-10-14 | Wed |
| not used | 2026-10-09 (late-night tail), 2026-10-15 (incomplete) | |

One test day cannot support a credible final test, so **all metrics are provisional**.
Only complete service dates are used, to keep each split's time-of-day mix whole. When
more data exists, the boundaries are edited in `config/eta_model.toml`, and the run
records them.

**The test day is spent.** 2026-10-14 has been used to evaluate the selected models,
and later to decide whether the serving interval is available
([model_serving.md](model_serving.md#the-test-day-is-no-longer-untouched)). It is no
longer an untouched holdout. Later model versions must be evaluated on later service
days, not on any date up to 2026-10-14.

## Baselines

1. **No revision:** predicts 0 s, and a probability of 0 for a large revision.
2. **Historical:** the median `eta_revision_seconds` and the frequency of large revisions
   in training rows, grouped with fallback levels. A group with fewer than
   `min_group_size` (30) training rows defers to the next level:
   1. horizon bucket × route × stop
   2. horizon bucket × route
   3. horizon bucket
   4. all training rows

   Each prediction records the level it used.

**Sensitivity of the historical baseline.** The pipeline also fits the baseline with
predeclared minimum group sizes of 15, 30, 60 and 100 (`sensitivity_min_group_sizes`).
Every setting uses the same fallback hierarchy and training rows only. Each is reported
beside the selected models on validation and test, including the paired bootstrap below.
The primary setting stays 30. It was fixed before any test result was seen, and the
sensitivity settings were declared after test results were visible, so they are not used
to choose a setting.

## Models

The models are interpretable, maintainable scikit-learn estimators. The seeds are fixed,
there is no early stopping, and no random row splits are used:

| Family | Regression | Classification | Validation grid |
|---|---|---|---|
| Linear (comparator) | `HuberRegressor`: a robust linear comparator. Huber loss is quadratic for small residuals and linear for large ones, so heavy tails pull on it less than on least squares. It does not directly optimize MAE | L2 `LogisticRegression` | regression α ∈ {0.01, 1, 100}; classification C ∈ {0.01, 0.1, 1} |
| Tree | `HistGradientBoostingRegressor` (absolute-error loss) | `HistGradientBoostingClassifier` | max leaf nodes ∈ {15, 31} |

For linear models, numeric features are median-imputed and standardized, and categories
are one-hot encoded with unknown categories ignored. For trees, categories are
ordinal-encoded and handled natively. The hyperparameters, learning rate, iteration count
and minimum leaf size live in `config/eta_model.toml`.

**Selection.** Every candidate is fitted on training rows and scored on validation:

- Regression candidates are compared by validation MAE, and classifiers by validation
  Brier score. A tie goes to the earlier (simpler) candidate.
- In the development run, both selected models are trees: the regression tree
  `tree_hgb_leaves=31` was selected using validation MAE, and the classification tree
  `tree_hgb_leaves=15` using validation Brier score. The Huber models remain linear
  comparators and were not selected.
- The selected regression model and classifier are scored **once** on test, beside both
  baselines. Candidates that were not selected are never scored on test.
- Models were not refitted on validation data, so no fitted quantity uses validation
  outcomes.

## Evaluation metrics

Every block reports its examples, events, service dates and prediction-time range.

- **Revision magnitude:** MAE, median absolute error and RMSE, overall and per 5/10/15
  minute published-time horizon. Each is reported with its change relative to each
  baseline, in seconds and percent.
- **Large revisions (> 60 s):**
  - prevalence;
  - precision and recall at probability ≥ `decision_threshold` (0.5). This is a
    descriptive operating point, not an optimized deployment threshold. A production
    threshold would be selected on validation data using an explicit rider or product
    cost;
  - PR-AUC (average precision) and ROC-AUC;
  - Brier score;
  - expected calibration error;
  - a 10-bin calibration table;
  - all of the above by horizon.

  A metric that is undefined (for example precision with no positive predictions, or
  ROC-AUC with one class) is reported as `null`.
- **Paired uncertainty on test:** a deterministic cluster bootstrap with 2,000
  replicates (`[uncertainty]`), seeded by `seed`. It reports 95% percentile intervals for
  the selected model minus the historical baseline:
  - MAE overall and at each published-time horizon;
  - Brier score;
  - PR-AUC;
  - the share of replicates in which the selected model wins.

  The **primary** unit is the trip run (service date + trip_id). BART reuses trip_ids
  every day, so the date is part of the key. A drawn trip brings every stop-arrival
  event of that trip and all of their 5/10/15-minute examples. Resampling stop-arrival
  events instead is kept as a labelled **sensitivity** analysis. Its intervals are
  narrower because events of the same trip are correlated. Rows are never resampled on
  their own.

  Even the trip bootstrap is conditional on the single test day. It does not capture
  day-to-day variability, and it may not capture system-wide conditions shared by many
  trips. It therefore cannot establish generalization to future service days. If an
  interval includes zero, the test day does not establish an improvement.

## Sample limitations

- About five complete service days: three for training, one for validation, one for test.
  Each split has one weather, incident and alert history.
- Training has one weekday (Monday, Indigenous Peoples' Day, which ran weekday service).
  Validation and test are midweek days.
- The labels are circular. BART's final estimate is the reference, so a model that
  predicts revisions well says nothing about physical arrival accuracy.
- Only eligible events with a stable final estimate (tier A by default) are modeled.
  Cancelled, added, skipped, ambiguous, origin and excluded-line events are not.
- Examples from the same day share conditions, so metrics are not independent samples.

## Development run (provisional)

This run used the 2026-10-15 snapshot, tier A, the 0.5 operating point and the default
config. There is one test day, so these numbers describe Wednesday 2026-10-14 only. All
results are provisional.

| Split | Service dates | Events | Examples | Share > 60 s |
|---|---|---|---|---|
| train | 2026-10-10 to 10-12 | 27,873 | 83,471 | 20.9% |
| validation | 2026-10-13 | 10,232 | 30,623 | 21.3% |
| test | 2026-10-14 | 11,157 | 33,412 | 21.1% |

**Excluded examples:**

- 16,672 on 2026-10-15, which was incomplete;
- 49 on 2026-10-09;
- 10,715 tier B;
- none that crossed a split boundary.

In addition, 414 eligible event-horizons had no example: 410 had no estimate within ±60 s
of the bucket, and 4 had one only in the final window.

**Validation selection:**

| Task | Selected model | Selected using | Validation score | Historical baseline | Best linear comparator (not selected) |
|---|---|---|---|---|---|
| Regression | tree `tree_hgb_leaves=31` | validation MAE | 29.0 s | 30.0 s | 31.7 s (Huber) |
| Classification | tree `tree_hgb_leaves=15` | validation Brier score | 0.120 | 0.129 | 0.128 (logistic) |

The linear comparators did not beat the historical baseline. Neither selected model was
refitted on validation data.

**Test** (11,157 events, 33,412 examples, 2026-10-14):

| Metric | No revision | Historical | Selected tree | Tree − historical (point) |
|---|---|---|---|---|
| MAE (s) | 46.1 | 25.1 | 24.1 | −0.96 (−3.8%) |
| MAE at 5 / 10 / 15 min published-time horizon (s) | 29.9 / 48.0 / 60.5 | 16.9 / 25.5 / 32.8 | 15.5 / 24.9 / 31.9 | −1.4 / −0.6 / −0.9 |
| Median absolute error (s) | 32.0 | 12.0 | 11.0 | −1.0 |
| RMSE (s) | 78.5 | 61.3 | 60.9 | −0.4 |
| Brier | 0.211 | 0.129 | 0.125 | −0.004 (−3.3%) |
| PR-AUC | 0.211 | 0.535 | 0.568 | +0.033 |
| ROC-AUC | 0.500 | 0.814 | 0.828 | +0.014 |
| Precision / recall at the 0.5 operating point | n/a / 0.000 | 0.615 / 0.400 | 0.647 / 0.385 | |
| Expected calibration error | 0.211 | 0.018 | 0.024 | +0.006 |

**Primary uncertainty: trip-clustered bootstrap** (selected tree minus historical; 2,000
replicates, seed 20261015; 625 trip runs, 11,157 events and 33,412 examples, 2026-10-14):

| Difference | Observed | 95% interval | Replicates where the tree wins |
|---|---|---|---|
| MAE (s), overall | −0.96 | −1.14 to −0.78 | 100% |
| MAE (s), 5-min published-time horizon | −1.38 | −1.54 to −1.20 | 100% |
| MAE (s), 10-min published-time horizon | −0.63 | −0.83 to −0.45 | 100% |
| MAE (s), 15-min published-time horizon | −0.86 | −1.15 to −0.60 | 100% |
| Brier score | −0.0042 | −0.0061 to −0.0024 | 100% |
| PR-AUC | +0.0327 | +0.0199 to +0.0458 | 100% |

**Sensitivity: event-clustered bootstrap** (same seed and replicate count; 11,157
events). These intervals are narrower because events from the same trip are correlated,
so resampling them independently understates the uncertainty. The trip-clustered
intervals are 1.3 to 1.9 times as wide.

| Difference | Observed | 95% interval | Replicates where the tree wins |
|---|---|---|---|
| MAE (s), overall | −0.96 | −1.05 to −0.86 | 100% |
| MAE (s), 5-min published-time horizon | −1.38 | −1.51 to −1.25 | 100% |
| MAE (s), 10-min published-time horizon | −0.63 | −0.76 to −0.50 | 100% |
| MAE (s), 15-min published-time horizon | −0.86 | −1.02 to −0.71 | 100% |
| Brier score | −0.0042 | −0.0053 to −0.0032 | 100% |
| PR-AUC | +0.0327 | +0.0255 to +0.0399 | 100% |

**Reading:**

- **Every trip-clustered interval excludes zero.** Within 2026-10-14, the tree's
  improvement over the historical baseline is distinguishable from zero.
- **The effect is small:** about 1 s of MAE, 0.004 of Brier score and 0.03 of PR-AUC.
- **One day only.** Even this bootstrap is conditional on the single October 14 test day.
  It does not capture day-to-day variability, and it may not capture system-wide
  conditions shared by many trips. It cannot establish that the improvement holds on
  future service days.

**Historical-baseline sensitivity** (predeclared minimum group sizes; test differences
with trip-clustered intervals):

| Min group size | Validation historical MAE (s) | Test historical MAE (s) | Test MAE diff (s) | Test Brier diff | Test PR-AUC diff |
|---|---|---|---|---|---|
| 15 | 30.04 | 25.05 | −0.96 (−1.14 to −0.78) | −0.0042 (−0.0061 to −0.0024) | +0.0326 (+0.0197 to +0.0457) |
| **30 (primary)** | 30.04 | 25.05 | −0.96 (−1.14 to −0.78) | −0.0042 (−0.0061 to −0.0024) | +0.0327 (+0.0199 to +0.0458) |
| 60 | 30.04 | 25.05 | identical to 30 | identical to 30 | identical to 30 |
| 100 | 30.21 | 25.17 | −1.08 (−1.27 to −0.90) | −0.0048 (−0.0066 to −0.0030) | +0.0348 (+0.0224 to +0.0469) |

- **The comparison does not change materially.** Every setting gives the same reading
  for every audited difference.
- **Why 60 equals 30.** No horizon × route × stop group has 30 to 59 training rows: 3
  have fewer than 30, 34 have 60 to 99, and the median is 149. The two settings therefore
  fit identical tables.
- **The primary stays 30.** Validation does not favor another size (MAE 30.04 s for 15,
  30 and 60; 30.21 s for 100), and test results are not used to choose one.

**Other observations:**

- Most of the improvement over "no revision" comes from the historical medians by
  published-time horizon, route and stop.
- Both probability models are overconfident above about 0.7: for predictions of 0.8 to
  0.9, 0.69 (historical) and 0.74 (tree) actually exceeded 60 s.
- Validation (Tuesday) had much heavier tails than test (RMSE 103 to 117 s, against 61 to
  79 s).

Full tables, including the calibration bins, are in `report.md` in the run directory.

## Artifact locations

Everything generated goes under the ignored `data/models/` (default
`data/models/eta_revision/`, replaced atomically on each run):

| File | Contents |
|---|---|
| `features.duckdb` | `eta_model_examples`, `eta_model_features`, alert context, `eta_model_feature_checks`, and `eta_model_frame` (split and exclusion per example) |
| `predictions.parquet` | Validation and test predictions from every scored model and baseline |
| `historical_baseline.parquet` | Fitted groups, by level (primary setting) |
| `historical_baseline_sensitivity.parquet` | Fitted groups for every predeclared minimum group size |
| `bootstrap_replicates.parquet` | Per-replicate metric values, trip-clustered (primary) and event-clustered (sensitivity) |
| `models/*.joblib` | Fitted candidates |
| `metrics.json`, `report.md` | All metrics, sample sizes and date ranges |
| `run_manifest.json` | Config, data range, split boundaries, versions and seed |

Only source code, tests, configuration and this documentation are committed.

## Rerunning

```bash
bart-transform --raw-dir data/raw/server_exports/<date>/gtfs_rt --out-dir data/processed/<name>
bart-build-warehouse --processed-dir data/processed/<name> --db data/warehouse/<name>.duckdb
bart-eta-model --db data/warehouse/<name>.duckdb
```

`bart-eta-model` attaches the warehouse read-only and never modifies it. It is
deterministic for a given warehouse and config.
