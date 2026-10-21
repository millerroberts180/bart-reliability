# ETA revision evaluation: 2026-10-20 checkpoint

**A one-time, preregistered evaluation. The sealed test day 2026-10-19 has now been used
and is spent.** It cannot serve as an untouched holdout for any later model version.

The models predict **ETA revision**: how much BART's published estimate will still change
before BART's own final stable estimate. The reference is circular, so nothing here
measures physical arrival accuracy ([observed_arrival_proxy.md](observed_arrival_proxy.md)).

## Result

Both retrained models were selected on validation and are gradient-boosted trees: the
regression model `tree_hgb_leaves=31` and the classifier `tree_hgb_leaves=31`. On
Monday 2026-10-19:

| Comparison | Regression (MAE) | Classification (Brier, PR-AUC) |
|---|---|---|
| Retrained vs historical baseline | **Better**: −1.25 s overall, and better at 5, 10 and 15 min | **Better**: Brier −0.0106, PR-AUC +0.073 |
| Retrained vs locked PR #7 models | **Better**: −0.36 s overall, and better at 5, 10 and 15 min | **Better**: Brier −0.0032, PR-AUC +0.034 |

Every one of these 12 primary differences has a trip-clustered 95% interval that excludes
zero in the retrained model's favour. The event-clustered sensitivity intervals agree.

**What this does and does not show:**
- **Small effects.** The improvement over the historical baseline is about 6% of its MAE,
  and the improvement over PR #7 is about 0.4 s.
- **One Monday.** The intervals are conditional on that single day. One test day cannot
  establish long-term generalization: it does not capture day-to-day variability,
  other service patterns, or conditions shared by many trips.
- **Not promoted.** This milestone only decides whether the retrained models deserve
  promotion. The serving bundle was not rebuilt or promoted.

## Procedure

Everything was fixed before the test day was scored:

1. **Preregistration.** The split, method and reading rules are in
   [modeling_plan.md](modeling_plan.md#preregistered-evaluation-2026-10-20-checkpoint),
   merged in PR #9 (`54b6f1c`). The project owner confirmed the selection rule beforehand:
   validation decides the primary model, and a winning linear model would have stayed
   primary.
2. **Warehouse checked.** `data/warehouse/bart_checkpoint_2026-10-20.duckdb` matched
   SHA-256 `19dd5cfc686bed4f223adbfe5c5d26ef8385e5d1a152da5aa2be7af9378e55cc` before the
   run and again after it.
3. **Locked models preserved.** The PR #7 bundle and run were copied to the ignored,
   read-only `data/models/locked/`. The bundle loader verified bundle
   `cd267407788558dd4776a6b7c86b6448c1a075f9f56c2ff7aa35300137d2fee9` and both model-file
   hashes.
4. **Configuration committed before fitting.** Commit `c2d504e` contains the
   preregistered split, the versioned output directory, the pinned locked comparison, and
   the code that scores it and reports category support.
5. **Rehearsal on spent days only.** This used the 2026-10-15 warehouse, which contains
   nothing after 10-15.
   - With the PR #7 split, the code reproduced PR #7 exactly: frame fingerprint,
     selection, every prediction, every metric, and every bootstrap replicate. The locked
     predictions equalled the retrained ones, so every difference was 0.
   - A weekend-only training split exercised the fallback reporting: every test row was
     outside the retrained model's support, and the shared-support subset was empty.
6. **One run.** `bart-eta-model --db data/warehouse/bart_checkpoint_2026-10-20.duckdb` ran
   from 2026-10-21 00:00:17 to 00:01:33 UTC (2026-10-20 17:00 PDT), on a clean tree at
   `c2d504e`. It exited 0 with no warnings. Its outputs were then made read-only.

Nothing was changed after the result. The features, models, hyperparameters,
thresholds, exclusions, metrics and selection rules are as preregistered.

## Data and population

The population is tier-A eligible events, at published-time horizons of 5, 10 and 15
minutes (±60 s). All 12 point-in-time feature checks passed with 0 failures. No event
crossed a split boundary, so none was purged.

| Split | Service dates | Days | Events | Trips | Examples | 5 / 10 / 15 min | Share > 60 s |
|---|---|---|---|---|---|---|---|
| Training | 2026-10-10 to 10-15 | Sat to Thu | 60,350 | 3,411 | 180,686 | 60,248 / 60,229 / 60,209 | 21.2% |
| Validation | 2026-10-16 to 10-18 | Fri, Sat, Sun | 27,732 | 1,567 | 83,012 | 27,686 / 27,669 / 27,657 | 20.5% |
| **Sealed test** | **2026-10-19** | Mon | 11,291 | 624 | 33,830 | 11,277 / 11,280 / 11,273 | 17.4% |

Prediction times run from 2026-10-10 12:17 to 10-16 08:49 UTC for training, from 10-16
11:18 to 10-19 08:46 for validation, and from 10-19 11:18 to 10-20 08:46 for test. The
last training label was confirmed at 10-16 08:55 UTC, before the first validation
prediction. The last validation label was confirmed at 10-19 08:52, before the first
test prediction.

**Not modelled:**
- **Tier B:** 21,700 examples.
- **Outside the split dates:** 49 examples from 2026-10-09 and 15,475 from the partial
  day 2026-10-20.
- **No example:** 774 eligible event-horizons. 767 had no estimate within ±60 s, and 7
  had one only in the final window.

## Validation results (model selection only)

Every candidate was fitted on training rows only and scored on validation. The selected
models were not refitted on validation data. Only they and the baselines were scored on
the test day.

| Model | MAE (s) | MAE 5 / 10 / 15 min (s) | Median AE (s) | RMSE (s) |
|---|---|---|---|---|
| no_revision (baseline) | 45.18 | 29.19 / 46.85 / 59.53 | 31.00 | 70.27 |
| historical (baseline) | 24.36 | 15.98 / 24.77 / 32.34 | 12.00 | 51.95 |
| linear_huber_alpha=0.01 | 26.12 | 18.61 / 25.88 / 33.89 | 14.28 | 52.23 |
| linear_huber_alpha=1 | 26.11 | 18.57 / 25.88 / 33.89 | 14.26 | 52.23 |
| linear_huber_alpha=100 | 26.72 | 18.70 / 26.72 / 34.75 | 15.02 | 52.91 |
| tree_hgb_leaves=15 | 24.07 | 15.42 / 24.70 / 32.11 | 11.36 | 51.64 |
| **tree_hgb_leaves=31 (selected)** | 23.98 | 15.26 / 24.69 / 32.01 | 11.08 | 51.54 |

| Model | Brier | PR-AUC | PR-AUC 5 / 10 / 15 min | ROC-AUC |
|---|---|---|---|---|
| no_revision (baseline) | 0.2049 | 0.2049 | 0.0834 / 0.2153 / 0.3163 | 0.5000 |
| historical (baseline) | 0.1281 | 0.5255 | 0.3355 / 0.4795 / 0.5837 | 0.8075 |
| linear_logistic_C=0.01 | 0.1314 | 0.4970 | 0.2501 / 0.4531 / 0.5652 | 0.7933 |
| linear_logistic_C=0.1 | 0.1309 | 0.5025 | 0.2790 / 0.4636 / 0.5667 | 0.7982 |
| linear_logistic_C=1 | 0.1310 | 0.5036 | 0.2840 / 0.4656 / 0.5672 | 0.7981 |
| tree_hgb_leaves=15 | 0.1229 | 0.5516 | 0.3811 / 0.5075 / 0.6108 | 0.8305 |
| **tree_hgb_leaves=31 (selected)** | 0.1227 | 0.5542 | 0.3954 / 0.5080 / 0.6139 | 0.8322 |

- **Selection.** Regression is selected by validation MAE: `tree_hgb_leaves=31`, 23.98 s.
  Classification is selected by validation Brier score: `tree_hgb_leaves=31`, 0.1227.
- **Linear comparators.** The best was `linear_huber_alpha=1` (26.11 s). It was not
  selected and did not beat the historical baseline (24.36 s).
- **Leakage alarm.** No single feature reached the 0.95 alarm on training rows. The
  highest was `stop_id` at 0.738, and there were no fit warnings.

## Sealed-test results (2026-10-19, evaluated once)

Every model in these tables was scored on the same 33,830 examples.

**Revision magnitude:**

| Model | MAE (s) | MAE 5 min | MAE 10 min | MAE 15 min | Median AE (s) | RMSE (s) |
|---|---|---|---|---|---|---|
| no_revision (baseline) | 41.00 | 27.57 | 42.70 | 52.72 | 29.00 | 60.94 |
| historical (baseline) | 20.94 | 14.48 | 21.35 | 26.98 | 11.00 | 41.94 |
| **tree_hgb_leaves=31 (selected)** | 19.68 | 12.91 | 20.37 | 25.77 | 9.57 | 40.97 |
| locked_pr7 (locked PR #7, never refitted) | 20.04 | 13.33 | 20.72 | 26.09 | 9.70 | 41.46 |

**Large revisions (absolute revision > 60 s):**

| Model | Brier | PR-AUC | Brier 5 / 10 / 15 min | PR-AUC 5 / 10 / 15 min |
|---|---|---|---|---|
| no_revision (baseline) | 0.1736 | 0.1736 | 0.0709 / 0.1803 / 0.2696 | 0.0709 / 0.1803 / 0.2696 |
| historical (baseline) | 0.1110 | 0.5296 | 0.0555 / 0.1208 / 0.1566 | 0.3507 / 0.4913 / 0.5818 |
| **tree_hgb_leaves=31 (selected)** | 0.1004 | 0.6027 | 0.0500 / 0.1098 / 0.1415 | 0.4611 / 0.5662 / 0.6554 |
| locked_pr7 (locked PR #7, never refitted) | 0.1036 | 0.5689 | 0.0523 / 0.1138 / 0.1449 | 0.4042 / 0.5259 / 0.6267 |

Secondary metrics. These were not used for any decision:

| Model | ROC-AUC | Expected calibration error | Precision at 0.5 | Recall at 0.5 |
|---|---|---|---|---|
| no_revision (baseline) | 0.5000 | 0.1736 | n/a | 0.0000 |
| historical (baseline) | 0.8280 | 0.0385 | 0.5931 | 0.4167 |
| **tree_hgb_leaves=31 (selected)** | 0.8597 | 0.0263 | 0.6432 | 0.4620 |
| locked_pr7 (locked PR #7, never refitted) | 0.8463 | 0.0137 | 0.6478 | 0.4395 |

### Retrained minus historical baseline

**Primary: trip-clustered bootstrap.** This pairs every model on the same resamples:
2,000 replicates, seed 20261015, 95% percentile intervals, over 624 trip runs. Negative
MAE and Brier differences, and positive PR-AUC differences, favour the retrained model.

| Difference | Observed | 95% interval | Replicates where the retrained model is better |
|---|---|---|---|
| MAE (s), overall | -1.2534 | -1.3933 to -1.1188 | 100.0% |
| MAE (s), 5 min | -1.5714 | -1.7173 to -1.4346 | 100.0% |
| MAE (s), 10 min | -0.9774 | -1.1221 to -0.8410 | 100.0% |
| MAE (s), 15 min | -1.2115 | -1.4465 to -0.9928 | 100.0% |
| Brier score | -0.0106 | -0.0121 to -0.0091 | 100.0% |
| PR-AUC | +0.0731 | +0.0599 to +0.0870 | 100.0% |

**Sensitivity: event-clustered** (11,291 events). These intervals are narrower because
events of the same trip are correlated.

| Difference | Observed | 95% interval | Replicates where the retrained model is better |
|---|---|---|---|
| MAE (s), overall | -1.2534 | -1.3400 to -1.1703 | 100.0% |
| MAE (s), 5 min | -1.5714 | -1.6954 to -1.4531 | 100.0% |
| MAE (s), 10 min | -0.9774 | -1.0847 to -0.8696 | 100.0% |
| MAE (s), 15 min | -1.2115 | -1.3427 to -1.0845 | 100.0% |
| Brier score | -0.0106 | -0.0116 to -0.0096 | 100.0% |
| PR-AUC | +0.0731 | +0.0642 to +0.0820 | 100.0% |

### Retrained minus locked PR #7 models

The locked models are PR #7's regression `tree_hgb_leaves=31` and classification
`tree_hgb_leaves=15`, trained on 2026-10-10 to 10-12 and selected on 10-13. They were
only used to predict, on the same rows and the same resamples.

**Primary: trip-clustered**

| Difference | Observed | 95% interval | Replicates where the retrained model is better |
|---|---|---|---|
| MAE (s), overall | -0.3616 | -0.4675 to -0.2671 | 100.0% |
| MAE (s), 5 min | -0.4158 | -0.4937 to -0.3423 | 100.0% |
| MAE (s), 10 min | -0.3499 | -0.4709 to -0.2335 | 100.0% |
| MAE (s), 15 min | -0.3191 | -0.4772 to -0.1750 | 100.0% |
| Brier score | -0.0032 | -0.0045 to -0.0021 | 100.0% |
| PR-AUC | +0.0339 | +0.0237 to +0.0446 | 100.0% |

**Sensitivity: event-clustered**

| Difference | Observed | 95% interval | Replicates where the retrained model is better |
|---|---|---|---|
| MAE (s), overall | -0.3616 | -0.4280 to -0.2962 | 100.0% |
| MAE (s), 5 min | -0.4158 | -0.4863 to -0.3463 | 100.0% |
| MAE (s), 10 min | -0.3499 | -0.4317 to -0.2696 | 100.0% |
| MAE (s), 15 min | -0.3191 | -0.4127 to -0.2293 | 100.0% |
| Brier score | -0.0032 | -0.0040 to -0.0025 | 100.0% |
| PR-AUC | +0.0339 | +0.0264 to +0.0411 | 100.0% |

### Category support and fallback

The serving rule applies: a row with any categorical value its model never saw is
outside that model's support, and the bundle would return `fallback_required` for it.
- **No fallback.** No 2026-10-19 example has an unseen category for either the retrained
  models or the locked PR #7 models. Support is 33,830 of 33,830 examples (100%) for
  each, and validation support for the retrained models is also 100%.
- **No subset.** The shared-support subset is therefore the full test population. By the
  predeclared rule it was not computed separately.
- **Historical-baseline fallback levels.** On the test day, 33,818 examples used the
  horizon × route × stop level. The other 12 fell back to horizon × route, because their
  stop group had fewer than 30 training rows or none.

### Historical-baseline sensitivity

These sizes were predeclared, and the primary size stays 30. Every setting gives the
same reading on every primary difference.

| Min group size | Validation MAE diff (s) | Test historical MAE (s) | Test MAE diff, trip-clustered | Test Brier diff | Test PR-AUC diff |
|---|---|---|---|---|---|
| 15 | -0.38 | 20.93 | -1.253 (-1.393 to -1.119) | -0.0106 (-0.0122 to -0.0091) | +0.0731 (+0.0599 to +0.0871) |
| **30 (primary)** | -0.38 | 20.94 | -1.253 (-1.393 to -1.119) | -0.0106 (-0.0121 to -0.0091) | +0.0731 (+0.0599 to +0.0870) |
| 60 | -0.39 | 20.94 | -1.254 (-1.393 to -1.118) | -0.0106 (-0.0122 to -0.0091) | +0.0734 (+0.0598 to +0.0872) |
| 100 | -0.39 | 20.94 | -1.254 (-1.393 to -1.118) | -0.0106 (-0.0122 to -0.0091) | +0.0734 (+0.0598 to +0.0872) |

### Other observations

- **Easier test day.** The test day had fewer large revisions than training and
  validation (17.4% against 21.2% and 20.5%). Both baselines and the retrained model had a
  lower MAE on it than on validation. The locked models were not scored on validation.
- **Calibration.** On calibration error, the locked PR #7 classifier was better than the
  retrained one (0.0137 against 0.0263). The retrained classifier predicted somewhat too
  high below 0.5: for example, a mean of 0.248 against an observed 0.197 in the 0.2–0.3
  bin. That is consistent with the test day's lower prevalence.
- **Operating point.** Precision at the descriptive 0.5 operating point was 0.643
  (retrained) against 0.648 (PR #7), and recall 0.462 against 0.440. Neither is a
  deployment threshold.

## Limitations

- **One Monday.** The test covers a single weekday. It does not establish long-term
  generalization, performance on weekends, holidays or disrupted days, or behaviour
  after schedule changes. The bootstrap is conditional on that day.
- **The test day was not perfectly untouched.** The checkpoint build's log printed
  pooled ETA-revision summaries over all 12 service dates, and 2026-10-19 is 10.8% of
  their tier-A events. Per-day data counts had also been computed. No daily 2026-10-19
  outcome was examined before this run
  ([data_checkpoint_2026-10-20.md](data_checkpoint_2026-10-20.md#what-has-been-seen-of-the-later-days)).
- **Validation differs from test.** Validation is mostly weekend service (Friday,
  Saturday, Sunday), while the test day is a weekday. The planned notice `BSA_560` was
  visible all day on 2026-10-19, and the alert feed was empty on 2026-10-16. Alert
  features are not used.
- **Circular labels.** Revisions are measured against BART's own final estimate.
- **Limited population.** Only tier-A eligible events are modelled, and eligibility is
  judged after the event. Origins, the last listed stop, added and cancelled trips, SFO
  repeats and excluded lines are absent.
- **The PR #7 comparison has two confounds.** The retrained models have six training days
  against three, and the classifiers differ in size (31 against 15 leaves). The
  comparison says the retrained pair predicted better on this day, not why.
- **No multiplicity adjustment.** Each primary difference is read separately.

## Artifacts

All of these are ignored by Git and read-only.

| Artifact | Path | SHA-256 |
|---|---|---|
| Warehouse (input) | `data/warehouse/bart_checkpoint_2026-10-20.duckdb` | `19dd5cfc686bed4f223adbfe5c5d26ef8385e5d1a152da5aa2be7af9378e55cc` |
| Selected regression model | `data/models/eta_revision_2026-10-20/models/regression__tree_hgb_leaves=31.joblib` | `cdfaa60609eeb15745133a77e62f74a73f3825e60250d4edf861b2e2f24ee917` |
| Selected classification model | `data/models/eta_revision_2026-10-20/models/classification__tree_hgb_leaves=31.joblib` | `a89547ce41224f997280ec72b4ba32bd9a51f7ae9a1a3199d14fb31856de950d` |
| Metrics | `data/models/eta_revision_2026-10-20/metrics.json` | `e6b2fab34870d2c93d99665061c69431642d447ae4df6fc9e9e4b17ddc9ede57` |
| Predictions | `data/models/eta_revision_2026-10-20/predictions.parquet` | `441ae75e69fbba3adb343f038fb96b0117a5e0857a1915af9ed5bf3441774749` |
| Run manifest | `data/models/eta_revision_2026-10-20/run_manifest.json` | `c4f1f8c6ea3f4085101c1467909dea998c7d17bc6f1c825c0738ac78e4fd118a` |
| Bootstrap replicates | `data/models/eta_revision_2026-10-20/bootstrap_replicates.parquet` | `836826949ebfdc55d8973f98018325cf0e9c5a581be1b703e3e885aaa718cea9` |
| Historical baseline | `data/models/eta_revision_2026-10-20/historical_baseline.parquet` | `61bba6a83a9c9fed99ff67cc3cb21e8e606f0c8b8c6edc1085acc04380542e54` |
| Baseline sensitivity | `data/models/eta_revision_2026-10-20/historical_baseline_sensitivity.parquet` | `afbc332759b4394961a3dcff44a6d5fc57fa1dec841e7155d223a7db527f0659` |
| Features | `data/models/eta_revision_2026-10-20/features.duckdb` | `f3f57b314d06daa86b95b62d16a8f62bd8964285936e8236ec8462dd109fbbf9` |
| Run report | `data/models/eta_revision_2026-10-20/report.md` | `abb5f1d3af175d369e1fe01dfac83d793e6ed1bbaf7b2801b7dd8bbee6ae52b1` |
| Run log | `data/models/eta_revision_2026-10-20_run.log` | `d15fae27a4c0462556a7f1cae0fefb8e511d1f12b3a7321701cf0c6a7abf439d` |
| Locked PR #7 regression | `data/models/locked/pr7_bundle_cd267407/regression.joblib` | `98d54d3e5954363d2d184e1cebb14e955bab4113f4dc55d01a15e5f117bf3d09` |
| Locked PR #7 classification | `data/models/locked/pr7_bundle_cd267407/classification.joblib` | `f62e5a37333b0b2cefccf9d778c3ecd78b73ac6088ea7ee792aa2a9fba3cb4e0` |
| Locked PR #7 metadata | `data/models/locked/pr7_bundle_cd267407/bundle.json` | `38c2699128d49b194e7f6eedc41269b36ac5c8b2e83be4d969afb69a3a3d88a0` |

The run's frame fingerprint is
`8487dd40a249bb73c2f9b25f2d80f1d46c425f879f2460bd34b342891e292100`. It records Python
3.13.3, DuckDB 1.5.6, scikit-learn 1.9.1, numpy 2.5.4 and pandas 3.0.6. The output
directory holds 18 files, and the other candidates' model files are there too. The
original PR #7 run and bundle under `data/models/` are unchanged.

## Reproduction

```bash
git checkout c2d504ef63b7efa5990debac7090aecf3c2fcc52
shasum -a 256 data/warehouse/bart_checkpoint_2026-10-20.duckdb   # must be 19dd5cfc…55cc
.venv/bin/bart-eta-model --db data/warehouse/bart_checkpoint_2026-10-20.duckdb \
    --out-dir data/models/<new directory>
```

- **Inputs.** The run needs the read-only locked bundle under `data/models/locked/`.
- **Output location.** The evaluation's own output directory is read-only, so a
  reproduction must write somewhere else with `--out-dir`.
- **Determinism.** The pipeline is deterministic: the same warehouse and configuration
  give the same selection, predictions, metrics and bootstrap replicates. Model files
  can differ byte-for-byte between processes because of serialization order. The
  rehearsal confirmed that the fitted trees and every prediction stay identical.
- **No new evidence.** A reproduction repeats this evaluation. It is not a new test.

## Next steps

Promotion is the project owner's decision, and nothing has been promoted.
- **Bundle rebuild.** Rebuilding the bundle with `bart-eta-bundle build` would rerun this
  configuration, so pass `--run-dir` to a new directory.
- **Its interval check.** That rebuild would also compute the serving interval's
  2026-10-19 coverage, under the availability rule predeclared in
  [model_serving.md](model_serving.md).
- **Later models.** Any later model needs service days after 2026-10-20.
