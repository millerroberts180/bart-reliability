# DuckDB warehouse

`bart-build-warehouse` loads one static GTFS archive and creates views over the
processed trip-update Parquet in `data/warehouse/bart.duckdb` (git-ignored).

```bash
.venv/bin/bart-build-warehouse                       # newest data/raw/gtfs_static/<date>/google_transit.zip
.venv/bin/bart-build-warehouse --gtfs-zip PATH --processed-dir data/processed --db data/warehouse/bart.duckdb
```

The build is **idempotent**: it creates a fresh database under a temporary name and
renames it over the old one only if every step succeeds. Reruns never duplicate rows,
and a failed build (missing or malformed archive) leaves the previous warehouse intact.
Exit code 2 means the static archive was rejected; the log says why.

## Static tables

Every GTFS identifier (`route_id`, `trip_id`, `stop_id`, `service_id`, ...) is stored as
`VARCHAR` exactly as written, so values like `07` or `0042` keep their leading zeros.
Blank fields become `NULL`. `raw_<file>` tables keep the untouched all-string input
for auditing.

| Table | Key | Notes |
|---|---|---|
| `static_agency` | - | |
| `static_routes` | `route_id` | `route_type` as integer |
| `static_trips` | `trip_id` | `service_id`, `direction_id`, `trip_headsign`, `shape_id` |
| `static_stops` | `stop_id` | Platform-level stops (`A10-1`) with `parent_station` (`LAKE`) |
| `static_stop_times` | `(trip_id, stop_sequence)` | `arrival_seconds`, `departure_seconds`; original text kept in `arrival_time`, `departure_time` |
| `static_calendar` | `service_id` | Weekday booleans, `start_date`, `end_date` as `DATE` |
| `static_calendar_dates` | `(service_id, date)` | `exception_type` 1 = added, 2 = removed |
| `static_service_days` | `(service_id, service_date)` | Derived: every date each service runs |
| `static_feed_load` | - | Provenance: archive path, SHA-256, dated folder, source URL, retrieval, `feed_info` and calendar date ranges |

### GTFS times past midnight

GTFS times are **not wall-clock times**. `25:10:00` means 1 h 10 min after midnight at
the end of the service day, so they are never parsed as `TIME`. They are stored as
seconds after the service-day origin (`25:10:00` -> `90600`). The real archive has
1,996 stop times at or after `24:00:00` (latest `26:23:00`).

To turn seconds into an instant, GTFS measures from **noon minus 12 hours** local time
(`America/Los_Angeles`) on the service date. This equals midnight on normal days and
stays correct on the two daylight-saving changeover days.

### Validation

The build fails with a specific message for: a missing archive; a file that is not a
ZIP or has a corrupt member; a missing required file or column; ragged CSV rows; invalid
times (`25:61:00`, `8:00`), dates, integers, or booleans; and duplicate keys. Broken
references (e.g. a `stop_times` row whose `stop_id` is not in `stops.txt`) are logged
as warnings, because their effect shows up in the join-quality report.

## Archive provenance

Each archive lives at `data/raw/gtfs_static/<date>/google_transit.zip` with an optional
`source.json` beside it (`source_url`, `resolved_url`, `retrieved`, `sha256`, notes).
The build checks that `source.json` describes the exact archive (by SHA-256), copies
it into `static_feed_load`, and logs a `static_gtfs_issue` warning if `source.json` is
missing or if `feed_info.txt` validity dates don't cover the calendar.

### Selected archive (checked 2026-10-10)

| Field | Value |
|---|---|
| Source URL | `https://www.bart.gov/dev/schedules/google_transit.zip` (BART's official permalink) |
| Resolved to | `https://www.bart.gov/sites/default/files/2026-08/google_transit_20260810-20270108_v02.zip` |
| Server `Last-Modified` | Tue, 04 Aug 2026 18:23:24 GMT |
| Local copy | `data/raw/gtfs_static/2026-10-08/google_transit.zip` (downloaded 2026-10-08; exact time not recorded) |
| SHA-256 | `affdc4d70cac01f71e54f049c754ba36824a885edcdef2ef8b024820c9e93080` |
| Re-downloaded | 2026-10-10T06:59:57Z, **byte-identical** to the local copy, so no new dated archive was saved |
| `feed_info.txt` | `feed_version` 72, valid **2026-01-12 to 2026-08-30** |
| Calendar coverage | 2026-08-10 to 2027-01-10 (matches the file name `20260810-20270108`) |

**Stale `feed_info` is a source-data limitation.** The archive BART serves today says
it expired on 2026-08-30, but its calendar, the file name, and the server date all
point to the schedule that started 2026-08-10. The build reports this as a warning on
every run. Service dates come from `calendar.txt` and `calendar_dates.txt`, never from
`feed_info.txt`.

## Real-time views

| View | What it is |
|---|---|
| `rt_trip_updates` | `read_parquet` over `data/processed/trip_updates/**/*.parquet` with Hive partitions renamed to `collection_date_utc`, `collection_hour_utc`. No rows are copied into DuckDB. |
| `rt_predictions_enriched` | One row per real-time prediction, joined to static trips, routes, stops, and the scheduled stop time. Unmatched predictions stay in the view with a `match_status`. |
| `rt_join_quality` | One row of match counts (see below). |
| `rt_unmatched_summary` | Unmatched predictions grouped by status and trip, with stop IDs and time range. |
| `rt_feed_snapshots` | The transformer's snapshot manifest (one row per snapshot, empty feeds included). |

The build also creates the ETA revision dataset (`observed_arrival_proxy`,
`eta_revision_examples`, and supporting views) from `config/eta_revision.toml`,
documented in [observed_arrival_proxy.md](observed_arrival_proxy.md). It fails with
exit code 1 if any check in `eta_revision_quality_checks` fails.

The Parquet path is stored as an absolute path, so rebuild the warehouse after moving
the repository.

## Join keys and matching

| Join | Key |
|---|---|
| Prediction -> trip | `trip_id` |
| Prediction -> stop | `stop_id` (platform level, same format in both feeds) |
| Trip -> route | `static_trips.route_id` |
| Prediction -> scheduled stop time | `(trip_id, stop_id)` on the resolved `service_date` |

BART omits `stop_sequence` in real time, so the stop-time join can only use
`(trip_id, stop_id)`. Some trips are scheduled at the same stop twice: in the real
archive, 444 `(trip_id, stop_id)` pairs repeat, all at SFO on Red and Yellow trips
(e.g. sequence 26 at `24:14:00` and 27 at `24:16:00`).

### Service-date resolution

`inferred_service_date` (the transformer's 03:00 rule) is only a starting point:

1. Candidate dates are `inferred_service_date` - 1, + 0, and + 1.
2. A candidate is kept only if the trip's `service_id` runs that day according to
   `static_service_days` (calendar plus `calendar_dates` additions and removals).
3. Each scheduled occurrence on a kept date becomes a candidate instant, which is only
   valid within **±3 hours** of the prediction. Without this window, a trip whose
   service is removed today (a holiday) could match tomorrow's run, 24 hours away.
4. The nearest candidate wins. Candidate dates are 24 h apart, so this fixes the
   service date first, then picks the closest occurrence on that date.

The prediction time is `predicted_arrival`, or `predicted_departure` when there is no
arrival (`match_time_source` says which), compared with the scheduled arrival or
departure respectively.

### Match columns

| Column | Meaning |
|---|---|
| `match_status` | `matched`, `trip_not_found`, `stop_not_found`, `stop_time_not_found` (trip known, but not scheduled at that stop), `no_prediction_time`, `no_active_service_in_window` |
| `match_method` | `unique_stop_time` (one scheduled occurrence) or `nearest_scheduled_time` (several; nearest chosen) |
| `match_candidate_count` | Scheduled occurrences of this trip at this stop |
| `match_time_difference_seconds` | Prediction minus the chosen scheduled time (positive = later than scheduled) |
| `is_ambiguous_match` | Matched with more than one candidate |
| `include_in_primary_metrics` | Matched with exactly one candidate. **Ambiguous matches are excluded from primary metrics** until validation shows they are reliable. |
| `service_date`, `service_date_source`, `service_date_offset_days` | Calendar-resolved service date, `'static_calendar'`, and its offset from `inferred_service_date` |
| `trip_found`, `stop_found` | Whether the IDs exist in static GTFS |

## Join quality (first real build, 2026-10-10)

65 snapshots from 2026-10-09 15:42-17:02 PDT, archive `2026-10-08`
(SHA-256 `affdc4d7...`).

| Metric | Value |
|---|---|
| Predictions | 70,971 |
| Matched to a static trip | 70,047 (98.70%) |
| Matched to a stop | 70,971 (100.00%) |
| Matched to a scheduled stop time | 70,047 (98.70%) |
| Ambiguous (excluded) | 280 rows, 13 trips, all at SFO (`Y10-2`) |
| Eligible for primary metrics | 69,767 (98.30%) |
| Service date differs from inferred | 0 |

All 924 unmatched predictions are `trip_not_found`:

- **912 rows, 18 trips** with short IDs (`672`-`695`) at Pittsburg Center (`E20`) and
  Antioch (`E30`): the Antioch extension, which `PROJECT_SPEC.md` already excludes
  because its real-time trip IDs do not align with static GTFS.
- **12 rows, trip `920014920`**, `ADDED` in real time at Concord-area stops (`C60`-`C80`).
  Added trips are by definition not in the schedule.

**Delay agreement.** For a correct match, *predicted - scheduled* should be close to
BART's own `arrival_delay_s`. On unique matches it is within 120 s for 99.23% of rows.
The difference is consistently about one minute (median +58 s): BART's absolute
times are later than scheduled + delay, probably from rounding on BART's side.
Agreement is 100% for the ambiguous SFO rows too, but **this does not validate them**:
the two scheduled SFO visits are 120 s apart, so either one would pass a 120 s check.

## Known limitations

- **One static archive at a time.** Predictions are matched against the archive given
  to the build. When BART publishes a new schedule, older predictions should be matched
  against the archive that was valid when they were collected; that versioning is not
  implemented.
- **Stale `feed_info.txt`** in BART's current archive (see
  [Archive provenance](#archive-provenance)). It is reported on every build, not used.
- **Ambiguous SFO matches** stay excluded. Validating them needs something other
  than delay agreement, for example the order of stops within each real-time update.
- **Antioch extension and `ADDED` trips** cannot be matched to the schedule.
- **Search window.** Service dates are searched ±1 day from `inferred_service_date`,
  and matches must be within ±3 h of the schedule. The largest real difference so far
  is 1,014 s.
- **DST changeover days** use the GTFS noon-minus-12h rule, but no collected data or
  test covers a changeover yet.
- **Performance.** `rt_predictions_enriched` is computed at query time. That is fine at
  this size; with months of data it may need to be materialized.
- **Duplicate stop IDs.** If BART ever lists the same `stop_id` twice in one real-time
  update, the transformer keeps only the first (see `docs/trip_updates_schema.md`).
