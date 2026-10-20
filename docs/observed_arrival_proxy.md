# ETA revision dataset and the observed-arrival proxy

This project studies **ETA revision**: how BART's published arrival estimates change as a
train approaches a stop. Every revision is measured against one reference endpoint, the
**final stable published estimate**, stored in the field `observed_arrival_proxy`.

**The proxy is not an observed arrival, and revisions are not arrival-accuracy errors.**
BART publishes no independent vehicle-location (AVL) or actual-arrival feed. Evaluating
physical arrival accuracy would require such a source, which BART does not publish.

## The reference endpoint and its circularity

For each trip and stop, BART's estimate converges as the train approaches. Then the stop
disappears from the trip's list while later stops remain. The reference endpoint is the
**last stable published estimate before that confirmed downstream progression**
(`proxy_method = last_stable_estimate_before_downstream_progression`).

- **It is circular.** The reference comes from the same system that publishes the
  estimates. A revision of +42 s at 10 minutes means "BART's final stable estimate was
  42 s later than the estimate it published 10 minutes earlier". It does not mean the
  train arrived 42 s after the earlier estimate. If BART's final estimate is itself
  biased, the bias is invisible here.
- **The disappearance is BART's too.** When a stop drops off the list is a second signal
  from the same feed and system. It loosely bounds the endpoint but does not validate it
  independently.
- **Disappearance is not arrival.** BART keeps listing a stop for a variable time after
  its final estimate (median +5 s, up to 13 minutes; see below). The disappearance time is
  recorded but never used as the endpoint.

The technical name `observed_arrival_proxy` is kept for the table and field. Read
"observed" as "observed in the feed", not "observed at the platform".

## Sign convention

```text
eta_revision_seconds          = final stable estimate - estimate published at the horizon
absolute_eta_revision_seconds = |eta_revision_seconds|
```

Positive values mean the ETA later moved **later** (`revision_direction =
revised_later`). Negative values mean it later moved **earlier** (`revised_earlier`).
Zero is `unchanged`. Both directions describe movement relative to the final stable
published estimate.

## Configuration

All thresholds live in [`config/eta_revision.toml`](../config/eta_revision.toml).
`bart-build-warehouse --eta-revision-config PATH` selects another file. Every key is
required, so defaults never apply silently, and the values used are stored in the
warehouse table `eta_revision_config`.

| Parameter | Default | Meaning |
|---|---|---|
| `max_collection_gap_s` | 90 | Longest acceptable snapshot gap from first observation to confirmation (normal: 60) |
| `stability_window` | 3 | Final estimates checked for stability |
| `stable_spread_s` | 60 | Maximum spread of those estimates for the event to be eligible |
| `tier_a_spread_s` | 30 | Maximum spread for tier A |
| `tier_a_persistence_s` | -60 .. +120 | Tier A: last listing minus final estimate must fall in this window |
| `horizon_targets_s` | 300, 600, 900 | Target horizons, measured as time to the final stable estimate |
| `horizon_tolerance_s` | 60 | Maximum distance of a chosen estimate from its target |
| `exclude_origin_stops` | true | A trip's first stop is a layover/departure, not an approach |

The loader rejects values that would break the design: a gap below the polling interval,
tier A looser than "stable", or tolerances wide enough for one estimate to represent two
targets.

## Building the dataset

`bart-build-warehouse` builds the dataset from `rt_predictions_enriched` in the same
idempotent build as the rest of the warehouse ([warehouse.md](warehouse.md)). It exits
with code 1 if any check in `eta_revision_quality_checks` fails.

### Feed snapshots

The transformer writes a per-snapshot manifest, `trip_update_snapshots/`, with one row
per processed snapshot, **including valid feeds with no trips**. The warehouse orders
these into `proxy_snapshot_timeline`. An empty feed therefore counts as an observation in
which a trip was absent, not as missing data. Processed data written before the manifest
existed falls back to snapshots that produced rows
(`rt_feed_snapshots.snapshot_source = 'derived_from_rows'`).

### Events and eligibility

A candidate event is one `(service_date, trip_id, stop_id, stop_sequence)`. The service
date is calendar-resolved, so a trip running past midnight stays one event. Progression
is judged by **stop position** within the static trip, because BART's `stop_sequence`
numbering has gaps (`0, 2, 3, ...`).

An event is eligible only if every rule holds. The first rule that fails is recorded as
`exclusion_reason`:

| Order | `exclusion_reason` | Rule |
|---|---|---|
| 1 | `excluded_line` | Antioch extension (`E20`, `E30`) or Oakland Airport Connector (`H10`, `H40`, routes 19/20) |
| 2 | `added_trip` | Trip ever marked `ADDED` |
| 3 | `cancelled_trip` | Trip ever marked `CANCELED` or `DELETED` |
| 4 | `skipped_or_no_data_stop` | Stop ever marked `SKIPPED` or `NO_DATA` |
| 5 | `unmatched_<status>` | No valid static trip and stop-time match |
| 6 | `ambiguous_repeated_stop` | Trip visits the stop more than once (SFO) |
| 7 | `not_primary_metrics` | Not in `include_in_primary_metrics` |
| 8 | `trip_origin` | First stop of the trip (when `exclude_origin_stops`) |
| 9 | `insufficient_observations` | Fewer observations than `stability_window` |
| 10 | `no_confirming_snapshot` | Stop still listed in the last snapshot of the data |
| 11 | `collection_gap` | A snapshot gap over `max_collection_gap_s` from first observation to confirmation |
| 12 | `trip_left_feed` | In the next snapshot the whole trip is gone, so the stop's disappearance can't be told apart from the trip leaving the feed |
| 13 | `no_downstream_progression` | The trip is visible but does not list only later stops |
| 14 | `unstable_final_estimate` | The final estimates span more than `stable_spread_s` |
| 15 | `no_horizon_history` | No estimate qualifies for any target horizon |

BART **never publishes a trip's final stop**, so terminal approaches are unobservable.
The last stop BART does list usually ends as `trip_left_feed`.

**Tier A** requires a final spread of at most `tier_a_spread_s`, the stop and trip
present in every snapshot of the span, and a last listing within
`tier_a_persistence_s` of the final estimate. Eligible events failing any of these are
**tier B**. Primary analyses should use tier A.

### Revision examples (`eta_revision_examples`)

For each eligible event and target, one published estimate is chosen deterministically:

1. Horizon is **time to the final stable estimate** (`time_to_proxy_s`), not BART's
   published horizon, so selection never depends on the estimate being measured.
2. The estimate must be within `horizon_tolerance_s` of the target.
3. The final `stability_window` observations, which define the endpoint, are never used.
4. The nearest estimate wins. Ties go to the earlier snapshot, then the lower feed
   timestamp.

### Tables and views

| Name | Kind | Contents |
|---|---|---|
| `observed_arrival_proxy` | table | Every candidate event: eligibility, exclusion reason, endpoint, tier, uncertainty |
| `observed_arrival_proxy_eligible` | view | Eligible events only |
| `eta_revision_examples` | table | One row per eligible event and target: `published_estimate`, `final_stable_estimate`, `time_to_proxy_s`, `published_horizon_s`, `eta_revision_seconds`, `absolute_eta_revision_seconds`, `revision_direction` |
| `eta_revision_history` | view | Every published estimate of each eligible event, with `time_to_proxy_s` and `eta_revision_seconds` (read from Parquet) |
| `eta_revision_quality_checks` | view | Invariant checks; every `failures` must be 0 |
| `eta_revision_config` | table | Parameters used for this build |
| `proxy_snapshot_timeline` | table | Snapshot order and the gap before each snapshot |
| `static_stop_positions` | table | Stop position within each static trip |
| `rt_feed_snapshots` | view | The transformer's snapshot manifest |

`observed_arrival_proxy` columns:

| Group | Columns |
|---|---|
| Identity | `event_id`, `service_date`, `trip_id`, `route_id`, `route_short_name`, `direction_id`, `stop_id`, `stop_sequence`, `stop_position`, `trip_stop_count` |
| Schedule | `scheduled_arrival` |
| Observation | `first_seen_at`, `last_seen_at`, `confirmed_absent_at` (first later snapshot without the stop), `confirmed_absent_feed_timestamp`, `next_snapshot_min_stop_position`, `observation_count`, `snapshots_in_span`, `stop_missing_snapshots`, `trip_missing_snapshots`, `max_collection_gap_s` |
| Estimates | `last_estimate_arrival`, `final_estimates` (newest first), `final_estimate_spread_s` |
| Endpoint | `is_eligible`, `exclusion_reason`, `proxy_arrival` (the final stable estimate; null unless eligible), `proxy_method`, `quality_tier`, `horizons_available` |
| Uncertainty | `listed_after_estimate_s`, `confirmed_absent_after_estimate_s`, `disappearance_window_s`, `uncertainty_s` |

`uncertainty_s` is a heuristic, not a confidence interval. It is the largest of three
quantities:
- the final-estimate spread;
- the disappearance window (normally 60 s);
- how far the last listing is from the final estimate. This matters when an estimate
  freezes while the stop stays listed.

## Results on the real export (2026-10-12)

These results describe only the 42-hour 2026-10-12 export. Counts for the 10.5-day
export are in [data_checkpoint_2026-10-20.md](data_checkpoint_2026-10-20.md). Revision
statistics for that later export are deliberately not summarized: they would include
the sealed test day of the
[preregistered evaluation](modeling_plan.md#preregistered-evaluation-2026-10-20-checkpoint).

**Data:**
- **Snapshots:** 2,546 trip-update snapshots from the verified server export, 2026-10-10
  08:11:07 UTC to 2026-10-12 02:35:23 UTC (about 42.4 hours, Saturday morning to Sunday
  evening Pacific).
- **Input rows:** **1,521,621** real-time predictions.
- **Snapshot gaps:** 60 s, except 44 s and 32 s at two service restarts. No empty feeds.
- **Static archive:** `2026-10-08`. **Parameters:** the defaults above.

### Events

| | Count |
|---|---|
| Candidate events | 19,744 |
| **Eligible** | **15,869** (80.4%) |
| Tier A | 14,781 (93.1% of eligible) |
| Tier B | 1,088 |

| Exclusion | Events | Notes |
|---|---|---|
| `trip_origin` | 816 | |
| `trip_left_feed` | 797 | 669 at the last stop BART lists; 128 trips vanishing mid-route |
| `added_trip` | 674 | |
| `no_confirming_snapshot` | 657 | Still listed in the final snapshot of the export |
| `excluded_line` | 367 | Antioch extension |
| `ambiguous_repeated_stop` | 289 | SFO |
| `unstable_final_estimate` | 137 | Final spread median 112 s, max 537 s |
| `unmatched_stop_time_not_found` | 112 | Real-time platform differs from the scheduled one |
| `no_downstream_progression` | 16 | One trip (`1973469`) whose list restarted at position 1 |
| `insufficient_observations` | 4 | |
| `unmatched_trip_not_found` | 4 | |
| `no_horizon_history` | 2 | |

`collection_gap`, `cancelled_trip`, and `skipped_or_no_data_stop` excluded no events in
this export, which has no gap over 60 s and no cancelled trip.

**BART does cancel trips.** The 10.5-day export through 2026-10-20 has trip-level
`CANCELED` trips on 9 of 12 service dates, 29 of them on 2026-10-13, and
`cancelled_trip` excludes 726 events there. Through that export, stop-level
`schedule_relationship` was still never populated (no `SKIPPED` or `NO_DATA`), and no
gap exceeded 90 s. `skipped_or_no_data_stop` and `collection_gap` therefore remain
covered by synthetic tests only.

### Horizon coverage

| Target | Examples | Share of eligible |
|---|---|---|
| 5 min | 15,856 | 99.92% |
| 10 min | 15,860 | 99.94% |
| 15 min | 15,858 | 99.93% |

Eligible events have a median of 82 observations (p5 50, p95 117).

### ETA revision by horizon (tier A)

| Target | n | Mean revision | Mean abs | Median abs | p90 abs | Within ±60 s | Revised later |
|---|---|---|---|---|---|---|---|
| 5 min | 14,781 | +25.4 s | 27.3 s | 22 s | 54 s | 92.7% | 82.0% |
| 10 min | 14,778 | +42.2 s | 47.4 s | 35 s | 87 s | 78.5% | 94.1% |
| 15 min | 14,775 | +55.8 s | 61.3 s | 43 s | 119 s | 66.8% | 95.7% |

Across all eligible events (tiers A and B) the mean revision is +26.2, +43.7, and
+57.8 s. **Headline finding:** BART's published ETAs are usually revised **later** as a
train approaches, and the revision grows with horizon. At 15 minutes, a third of ETAs
move by more than a minute before the final stable estimate.

### Stability of the final estimates

Spread of the last 3 estimates (eligible plus `unstable_final_estimate` events): 67.0%
exactly 0 s, median 0 s, p90 24 s, p99 57 s, max 537 s.

Tier B causes:
- final spread of 31–60 s: 759 events;
- persistence outside -60 to +120 s: 309;
- the stop or trip missing from one or more snapshots: 32.

Some events have several causes.

### Persistence after the final estimate

How long BART keeps listing a stop after its final estimate (eligible events):

| | p5 | p25 | p50 | p75 | p95 | p99 | min | max |
|---|---|---|---|---|---|---|---|---|
| Last listed minus final estimate | -31 s | -12 s | +5 s | +22 s | +55 s | +158 s | -481 s | +771 s |

The stop was confirmed absent a median of 65 s after the final estimate (p95 115 s).
With 60 s snapshots, this means BART typically removes a stop within about a minute of
its final estimate. 27 eligible events stayed listed more than 5 minutes after it;
6 vanished more than 5 minutes before it.

`uncertainty_s`: median 60 s, p99 162 s, max 771 s (tier B p95 253 s).

### Questionable events

| Event | Line, station | Behavior |
|---|---|---|
| `2026-10-10:1968547:11` | Orange-N, Fruitvale | Estimate frozen at 00:25:32 PDT while the stop stayed listed until 00:38:23 (771 s) |
| `2026-10-10:1968419:16` | Yellow-N, MacArthur | Listed 713 s after a frozen estimate |
| `2026-10-10:1968342:10` | Yellow-S, MacArthur | Listed 641 s after its final estimate |
| `2026-10-10:1968385:23` | Yellow-N, Concord | Dropped 481 s **before** its final estimate (13:38:51 PDT) |
| `2026-10-10:1968311:6` | Yellow-S, Walnut Creek | Dropped 457 s before its final estimate, in the **same snapshot** as the previous row |

Long persistence clusters at MacArthur (`K30`, 9 of the 27 events listed more than 300 s
after the estimate), a transfer station where trains hold. When an estimate freezes
during a hold, the "final stable estimate" reflects when BART expected the train, not a
settled view after the hold. Two trips losing stops early in the same snapshot points to
a feed-side event. All of these are tier B.

## Sensitivity analysis

`bart-eta-sensitivity` rebuilds the dataset in memory from a **read-only** attachment of
the warehouse, changing one parameter at a time from the defaults. The warehouse file's
SHA-256 was identical before and after the run.

**Robustness criteria, fixed before the results were seen.** The headline findings are
robust if, in every scenario:
1. the mean revision is positive at all three horizons and grows with horizon;
2. the median absolute revision moves by no more than 10 s from the default;
3. the share within ±60 s moves by no more than 5 percentage points;
4. eligible events change by less than 10% and coverage stays above 95%.

Coverage depends mechanically on tolerance, so criterion 4 is reported but expected to
move with it.

| Scenario | Eligible | Tier A | Coverage 5/10/15 min (%) | Tier A mean revision (s) | Tier A median abs (s) | Tier A within ±60 s (%) | All-eligible mean (s) |
|---|---|---|---|---|---|---|---|
| **Defaults** | 15,869 | 14,781 | 99.92 / 99.94 / 99.93 | +25.4 / +42.2 / +55.8 | 22 / 35 / 43 | 92.7 / 78.5 / 66.8 | +26.2 / +43.7 / +57.8 |
| Max gap 75 s | 15,869 | 14,781 | 99.92 / 99.94 / 99.93 | +25.4 / +42.2 / +55.8 | 22 / 35 / 43 | 92.7 / 78.5 / 66.8 | +26.2 / +43.7 / +57.8 |
| Max gap 120 s | 15,869 | 14,781 | 99.92 / 99.94 / 99.93 | +25.4 / +42.2 / +55.8 | 22 / 35 / 43 | 92.7 / 78.5 / 66.8 | +26.2 / +43.7 / +57.8 |
| Stable spread 30 s | 15,110 | 14,781 | 99.91 / 99.95 / 99.93 | +25.4 / +42.2 / +55.8 | 22 / 35 / 43 | 92.7 / 78.5 / 66.8 | +25.4 / +42.6 / +56.2 |
| Stable spread 90 s | 15,920 | 14,781 | 99.92 / 99.94 / 99.92 | +25.4 / +42.2 / +55.8 | 22 / 35 / 43 | 92.7 / 78.5 / 66.8 | +26.4 / +44.0 / +58.1 |
| Tolerance ±30 s | 15,867 | 14,779 | 99.92 / 99.94 / 99.94 | +25.4 / +42.2 / +55.8 | 22 / 35 / 43 | 92.7 / 78.5 / 66.8 | +26.3 / +43.7 / +57.8 |
| Tolerance ±90 s | 15,870 | 14,782 | 99.94 / 99.96 / 99.94 | +25.4 / +42.2 / +55.8 | 22 / 35 / 43 | 92.7 / 78.5 / 66.8 | +26.2 / +43.7 / +57.8 |
| Persistence -30 .. +60 s | 15,869 | 13,603 | 99.92 / 99.94 / 99.93 | +24.9 / +41.5 / +55.1 | 22 / 35 / 43 | 93.2 / 78.9 / 67.2 | +26.2 / +43.7 / +57.8 |
| Persistence -120 .. +300 s | 15,869 | 15,045 | 99.92 / 99.94 / 99.93 | +25.4 / +42.3 / +55.9 | 22 / 36 / 43 | 92.6 / 78.4 / 66.7 | +26.2 / +43.7 / +57.8 |

Exclusion counts that changed (all others identical across scenarios):

| Scenario | `unstable_final_estimate` | `no_horizon_history` |
|---|---|---|
| Defaults | 137 | 2 |
| Stable spread 30 s | 896 | 2 |
| Stable spread 90 s | 86 | 2 |
| Tolerance ±30 s | 137 | 4 |
| Tolerance ±90 s | 137 | 1 |

**Result: no scenario violates any criterion, so the defaults are kept.**
- Tier A: every variant moves the mean revision by at most 0.7 s, the median absolute
  revision by at most 1 s, and the share within ±60 s by at most 0.5 points.
- All eligible events: at most 1.6 s, 1 s, and 1.4 points respectively.
- Eligible events stay within -4.8% to +0.3% of the default, and coverage never falls
  below 99.9%.
- Tier A ranges from 13,603 to 15,045 events (-8.0% to +1.8%).

What the sensitivity analysis can and cannot show:

- **The gap threshold is untested by this data.** The export has no gap over 60 s, so
  75, 90, and 120 s give identical results. A collection with real outages is needed to
  exercise it. The 10.5-day export has none either: its largest gap between polling
  cycles is 64.7 s.
- **The stability threshold cannot move tier A by construction**, because tier A already
  requires a spread of at most 30 s. Its effect shows in the eligible count and the
  all-eligible statistics.
- **Tolerance barely matters at 60 s sampling.** Snapshots fall within 30 s of nearly
  every target, so ±30 s and ±90 s choose almost the same estimates.
- **Only the parameters were varied, not the endpoint definition.** The analysis shows
  the findings don't hinge on thresholds. It cannot address the circularity of using
  BART's own final estimate as the reference.

## Limitations

- **Circular reference** (above). Revisions describe BART's internal consistency, not
  physical arrival accuracy.
- **Terminal approaches are unobservable,** and the last listed stop of each trip is
  mostly excluded, so line ends are under-represented.
- **One weekend.** The results above cover no weekday peaks, holidays, or DST
  changeovers. Later data adds weekdays, disruptions and `CANCELED` trips (see above),
  but still no `SKIPPED` stop or DST changeover.
- **60 s sampling** limits how precisely disappearance can be placed and makes the
  tolerance and gap parameters nearly inert.
- **Frozen estimates during holds** (e.g. MacArthur) can make the endpoint too early.
  They are flagged as tier B but not corrected.
- **The sensitivity grid is one-at-a-time.** Interactions between parameters, and
  alternative endpoint definitions, were not explored.
