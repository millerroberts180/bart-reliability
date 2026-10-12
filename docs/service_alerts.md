# Service alerts

`bart-transform` normalizes BART's GTFS-Realtime **alert** snapshots. `bart-build-warehouse`
then records, for each ETA-revision example, which alerts riders could **see** in the feed
when the estimate was published.

**A visible alert is not evidence of an operational disruption, and nothing here
suggests that an alert caused an ETA revision.** These tables describe co-occurrence of
published estimates with alerts shown in the feed.

## Vocabulary

These concepts are kept separate in column names and in reporting:

| Term | Meaning | Column(s) |
|---|---|---|
| **alert state known** | A sufficiently recent alert snapshot exists at publication time T (see [the temporal join](#temporal-join-information-available-at-publication)) | `alert_state_known`, `alert_feed_status` |
| **visible** | The alert appeared in the most recent non-stale alert snapshot available at T | (bridge rows) |
| **applicable visible alert** | A visible alert whose **structured** informed entities apply to the prediction's agency, route, trip, and stop | `has_applicable_visible_alert`, `applicable_visible_alert_count`, `applicable_visible_alert_ids` |
| **structured active period** | Whether BART supplied an `active_period` | `has_structured_active_period` |
| **within structured period** | Whether T falls inside a supplied period: true, false, or **null when no period was supplied** | `within_structured_active_period` |
| **operational disruption active** | **Unknown (null) unless supported by a structured active period.** Visibility alone never sets it | `operational_disruption_active` |
| **alert category** | `planned_notice`, `incident_like`, or `unclassified`, from a **manual** annotation file | `alert_category`, `alert_context_group` |

## Processed schema

Written by `bart-transform` under the processed root, next to `trip_updates/`. Every run
rebuilds all outputs from raw snapshots.

| Dataset | Grain | Columns |
|---|---|---|
| `alert_snapshots/date=/hour=/` | one row per alert snapshot, **including valid empty feeds** | `feed_timestamp`, `collected_at`, `source_file`, `entity_count`, `alert_count` |
| `alert_observations/date=/hour=/` | one row per (snapshot, alert entity) | `feed_timestamp`, `collected_at`, `source_file`, `entity_id`, `alert_fingerprint` |
| `alert_versions/` | one row per distinct alert content | `alert_fingerprint`, `cause`, `effect`, `severity_level`, `header_text`, `description_text`, `url`, `*_translations`, `active_period_count`, `informed_entity_count`, `alert_json` |
| `alert_active_periods/` | one row per (content, period) | `alert_fingerprint`, `period_index`, `active_start`, `active_end` (null = open) |
| `alert_informed_entities/` | one row per (content, informed entity) | `alert_fingerprint`, `entity_index`, `agency_id`, `route_id`, `route_type`, `direction_id`, `trip_id`, `trip_route_id`, `stop_id` |
| `alert_snapshots/_quarantine.jsonl` | invalid snapshots | `source_file`, `reason` |

How the datasets fit together:

- **Fingerprint.** `alert_fingerprint` is the SHA-256 of the alert as canonical JSON. A
  version is `(entity_id, alert_fingerprint)`, so changed content under the same entity
  ID is a new version.
- **No cross product.** Periods and informed entities hang off the fingerprint, never off
  snapshots.
- **Absent stays absent.** Missing `cause`, `effect`, and `severity_level` are null.
- **Text.** English (`en`/`en-US`) is preferred, and all translations are kept.
- **Duplicates and malformed entities.**
  - Duplicate feed timestamps keep the earliest snapshot.
  - Non-alert and deleted entities are counted and skipped.
  - A repeated entity ID within one snapshot keeps its first occurrence.

## Warehouse tables and views

| Name | Kind | Purpose |
|---|---|---|
| `rt_alert_snapshots`, `rt_alert_observations`, `alert_versions`, `alert_active_periods`, `alert_informed_entities` | views | The Parquet above |
| `alert_snapshot_timeline` | table | Alert snapshots in order |
| `alert_visibility` | table | When each alert version was **visible in the feed**: `visible_from`, `last_seen`, `visible_until` (first later snapshot without it), `visible_at_end_of_data`, `interval_number` |
| `alert_entity_versions` | view | One row per `(entity_id, version)` |
| `alert_informed_entity_scope`, `alert_version_scope` | views | Structured scope: `stop` > `trip` > `route` > `route_type` > `system_wide`, plus `unspecified` (counted, never matched) |
| `alert_annotations` | table | The manual categories (below) |
| `eta_revision_example_alerts` | table | **Bridge, one-to-many:** one row per (revision example, applicable visible alert version), with `matched_scope`, `cause`, `effect`, `has_structured_active_period`, `within_structured_active_period`, `operational_disruption_active`, `alert_category` |
| `eta_revision_alert_context` | table | **Exactly one row per `eta_revision_examples` row**; join on `(event_id, target_horizon_s)` |
| `alert_quality_checks` | view | 10 invariants; any failure fails the build |

### Applicability

An informed entity applies to a prediction when **every** field it sets matches:
- the agency: BART's static `agency_id`, or the route's own agency;
- the static `route_id` and `route_type`;
- `direction_id`;
- `trip_id`;
- `stop_id`, which may be the platform or its parent station.

The bridge records the most specific matching scope. Scope comes **only from structured
fields**; alert text is never parsed.

### `eta_revision_alert_context` columns

| Group | Columns |
|---|---|
| Snapshot | `prediction_feed_timestamp`, `alert_snapshot_feed_timestamp`, `alert_snapshot_age_s`, `alert_feed_status`, `alert_state_known` |
| Visibility | `has_applicable_visible_alert`, `applicable_visible_alert_count`, `applicable_visible_alert_ids` |
| Category | `applicable_visible_planned_count`, `applicable_visible_incident_like_count`, `applicable_visible_unclassified_count`, `alert_context_group` |
| Structured periods | `with_structured_period_count`, `within_structured_period_count`, `outside_structured_period_count`, `operational_disruption_active` |
| Scope | `most_specific_visible_scope`, `visible_system_wide`, `visible_route`, `visible_trip`, `visible_stop` |
| Details | `visible_causes`, `visible_effects` |

- **Unknown state.** When alert state is unknown, the visibility, category, period, and
  scope fields are NULL, not false.
- **`operational_disruption_active`:**
  - TRUE if any applicable visible alert's structured period covers T;
  - FALSE only if every applicable visible alert has a structured period and none covers T;
  - NULL otherwise, including when no alert is visible. The absence of an alert is not
    evidence that nothing is disrupted.
- **`alert_context_group`** has exactly one value per example:
  - `unknown_alert_state`;
  - `no_applicable_visible_alert`;
  - `applicable_visible_incident_like`, if any applicable visible alert is incident-like;
  - otherwise `applicable_visible_unclassified`, if any is unclassified;
  - otherwise `applicable_visible_planned_notice`.

## Temporal join: information available at publication

**T** is `prediction_feed_timestamp`, the publication time of the trip-update snapshot.

1. **As-of snapshot.** Take the latest alert snapshot with feed timestamp **≤ T**
   (`ASOF` join). Snapshots published after T are never used.
2. **Staleness.** If it is more than **120 s** older than T, the state is
   `alert_snapshot_stale`. If none precedes T, it is `no_alert_snapshot`. Either way
   `alert_state_known` is false.
3. **Visible.** Alerts in that snapshot are visible. An alert is an applicable visible
   alert if its structured entities apply.
4. **Within period.** A structured period covers T when `start <= T <= end`. Missing
   bounds are open, and **both bounds are inclusive**, a documented choice because the
   specification does not define inclusivity.

The alert feed is sometimes stamped one second after the trip-update feed of the same
polling cycle. The strict rule then uses the previous cycle's snapshot, so alert state
can lag by up to about a minute.

## How "planned" and "incident-like" are determined

**By manual review of the alert text, not by an automated classifier.**
`config/alert_annotations.csv` lists one row per alert **version**:

- **Fields:** `entity_id`, `alert_fingerprint`, `category`, `basis` (the quoted text the
  decision rests on), and `reviewed_on`.
- **Rules applied by the reviewer:**
  - `planned_notice`: the text announces scheduled work or a recurring planned service
    change ("Expect … due to planned … construction work").
  - `incident_like`: the text reports a current or recent unplanned delay with a specific
    cause ("There is a 20-minute delay … due to a disabled train", "recovering from an
    earlier problem").
- **Unlisted versions are `unclassified`.** A version whose content changes, or a new
  alert, stays unclassified until someone reviews it.
- **Who reviewed.** The six current rows were **drafted by the AI coding assistant on
  2026-10-12** from the published text and are marked for confirmation by the project
  owner.
- **Validation.** The loader rejects unknown categories, malformed fingerprints, and
  duplicate fingerprints. The build checks that each annotation's `entity_id` matches
  the observations.

A category describes what an alert's text *says*. It does not establish that service was
operationally disrupted at T: `operational_disruption_active` stays NULL for these
alerts.

## Results on the real export (2026-10-12)

The verified server export: 2026-10-10 08:11 UTC to 2026-10-12 02:35 UTC.

| | Value |
|---|---|
| Alert snapshots | 2,546 (none quarantined, no duplicate feed timestamps) |
| Empty / non-empty | **1,990 empty** / 556 non-empty |
| Unique alerts / content versions / visibility intervals | 6 / 6 / 6 |
| `cause`, `effect` | never set |
| Structured active periods | **none** (0 of 6 versions) |
| Structured scope | 6 of 6 `system_wide` (`agency_id = BART`) |
| Manual categories | 5 `incident_like`, 1 `planned_notice` (`BSA_560`) |
| Malformed or unmatched records | 0 non-alert, 0 deleted, 0 duplicate IDs, 0 unspecified entities |

| Alert | Visible in feed (PDT) | Category | Text (abridged) |
|---|---|---|---|
| `BSA_1547` | 10-10 13:23 – 14:12 | incident-like | 20-minute delay, Antioch line, SFO direction, disabled train |
| `BSA_1549` | 10-10 13:39 – 14:10 | incident-like | 10-minute delay, SFO/Millbrae lines, unscheduled track inspections |
| `BSA_1550` | 10-10 14:12 – 15:10 | incident-like | Recovering; 20-minute delay, earlier disabled train |
| `BSA_560` | 10-11 12:08 – end of data | **planned notice** | "Expect 30-minute delays starting at 9pm each night on Sunday-Thursday … planned train control modernization construction work" |
| `BSA_1587` | 10-11 17:32 – 18:16 | incident-like | Recovering; 10-minute delay, earlier medical emergency |
| `BSA_1594` | 10-11 19:05 – end of data | incident-like | Recovering; 10-minute delay, earlier police activity |

### Revision examples (tier A, 44,334)

| `alert_context_group` | Examples | Share |
|---|---|---|
| `no_applicable_visible_alert` | 30,030 | 67.74% |
| `applicable_visible_planned_notice` (`BSA_560` only) | 9,702 | 21.88% |
| `applicable_visible_incident_like` | 4,602 | 10.38% |
| `applicable_visible_unclassified` | 0 | 0% |
| `unknown_alert_state` | 0 | **0.00%** |

- **Visible alerts.** **32.26%** of tier A examples (14,304) were published with an
  **applicable alert visible in the feed**: 32.56%, 32.27%, and 31.96% at 5, 10, and
  15 minutes. This is **not** the share published during an active disruption.
- **Disruption.** `operational_disruption_active` is **unknown for 100%** of examples,
  because BART supplied no structured active periods.
- **Planned-work concentration.** 80% of the visible-alert examples (11,450) include
  `BSA_560`; 9,702 have it as their only applicable visible alert. Its text describes
  delays from 9 pm on certain nights. Outside those hours its operational applicability
  is unknown, and it was visible for 31 hours. It is reported as its own group and should
  **not** define any primary "disruption" comparison.
- **Incident-like alerts.** They account for 10.38% of examples. 1,748 of those also had
  `BSA_560` visible, and they count as incident-like by the precedence rule.
- **Snapshot age at publication.** 0–1 s for 58.2% of all 47,574 examples, 58–61 s for
  the rest, at most 61 s.

### Staleness sensitivity

`bart-alert-sensitivity` rebuilds the alert context in memory from a read-only warehouse:

| Max snapshot age | Unknown alert state (tier A) | No visible alert | Planned notice | Incident-like |
|---|---|---|---|---|
| 60 s | 75 (0.17%) | 29,955 | 9,702 | 4,602 |
| **120 s** | **0 (0.00%)** | 30,030 | 9,702 | 4,602 |
| 180 s | 0 (0.00%) | 30,030 | 9,702 | 4,602 |

- **Keeping 120 s.** The 60 s limit misclassifies normal polling jitter as stale:
  alert-snapshot spacing is often 61–62 s, and the oldest snapshot any prediction used
  was 61 s old. 120 s, two polling intervals, has no such errors, and 180 s gives
  identical results.
- **Groups barely move.** The visible-alert groups change only at 60 s (75 examples
  move to unknown), so the threshold does not drive the findings.

## Limitations

- **Visibility, not disruption.** BART supplies no active periods, causes, or effects,
  so the real data can say only whether an alert was visible, never whether a disruption
  was operationally in effect.
- **Scope lives in the text.** Line, direction, and station information appears only in
  descriptions. Text is not parsed, so every real alert is system-wide and route- or
  stop-level applicability is understated. Those paths are tested synthetically only.
- **Manual categories.** Six versions were reviewed by hand, drafted by the AI assistant
  and pending owner confirmation. There is no automated classifier, and new or changed
  alerts are `unclassified` until reviewed.
- **A short sample.** About 42 hours, 6 alerts, one long-running planned notice.
- **Up to a minute of alert lag** under the strict no-future rule.
- **Rider visibility is approximated** by the feed at 60 s sampling.
- **Co-occurrence only.** Nothing here attributes ETA revisions to alerts.
