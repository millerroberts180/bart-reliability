# Processed trip updates: schema and deduplication

Produced by `bart-transform` from raw GTFS-Realtime trip-update snapshots in
`data/raw/gtfs_rt/trip_updates/`. One row per `StopTimeUpdate`.

## Layout

```text
data/processed/trip_updates/
  date=YYYY-MM-DD/hour=HH/part.parquet   # UTC collection date and hour, zstd-compressed
  _quarantine.jsonl                       # inputs that could not be processed
data/processed/trip_update_snapshots/
  date=YYYY-MM-DD/hour=HH/part.parquet   # one row per processed snapshot (see below)
```

`--out-dir` changes the root, e.g. `data/processed/server_export_2026-10-12/` for a
server export.

### Snapshot manifest

`trip_update_snapshots` has one row per snapshot used (after duplicate-feed removal,
excluding quarantined files), **including valid feeds with no trips**:
`feed_timestamp`, `collected_at` (UTC timestamps), `source_file`, `entity_count`,
`row_count`. A snapshot that produced no rows therefore still shows the feed was
observed. The observed-arrival proxy depends on this to tell "trip absent" from
"no observation".

The `date=`/`hour=` directories are Hive-style partitions, so DuckDB can read them with
`read_parquet('data/processed/trip_updates/**/*.parquet', hive_partitioning = true)`.

## Columns

| Column | Arrow type | Nullable | Source |
|---|---|---|---|
| `feed_timestamp` | `timestamp[ms, UTC]` | no | `FeedMessage.header.timestamp` |
| `collected_at` | `timestamp[ms, UTC]` | no | Collector's UTC clock, parsed from the snapshot filename |
| `trip_id` | `string` | no | `TripDescriptor.trip_id` |
| `route_id` | `string` | yes | `TripDescriptor.route_id` (BART currently omits it) |
| `direction_id` | `int8` | yes | `TripDescriptor.direction_id` (BART currently omits it) |
| `stop_id` | `string` | no | `StopTimeUpdate.stop_id`, platform-level, e.g. `M10-1` |
| `stop_sequence` | `int32` | yes | `StopTimeUpdate.stop_sequence` (BART currently omits it) |
| `predicted_arrival` | `timestamp[ms, UTC]` | yes | `StopTimeUpdate.arrival.time` |
| `predicted_departure` | `timestamp[ms, UTC]` | yes | `StopTimeUpdate.departure.time` |
| `arrival_delay_s` | `int32` | yes | `StopTimeUpdate.arrival.delay`, as supplied by BART |
| `departure_delay_s` | `int32` | yes | `StopTimeUpdate.departure.delay`, as supplied by BART |
| `arrival_uncertainty_s` | `int32` | yes | `StopTimeUpdate.arrival.uncertainty` |
| `trip_schedule_relationship` | `string` | yes | Trip level: `TripDescriptor.schedule_relationship` enum name |
| `stop_schedule_relationship` | `string` | yes | Stop level: `StopTimeUpdate.schedule_relationship` enum name |
| `prediction_horizon_seconds` | `int64` | yes | `predicted_arrival - collected_at`; null when there is no arrival time |
| `inferred_service_date` | `date32` | no | **Provisional**; see [Service date](#service-date-provisional) |
| `source_file` | `string` | no | Snapshot path relative to `data/raw/gtfs_rt/` |

Timestamps hold whole seconds from the feed. Parquet has no seconds unit, so PyArrow
stores them as milliseconds; the values are unchanged.

`prediction_horizon_seconds` can be negative: BART keeps listing a stop for a few
minutes after its predicted arrival has passed (703 of 70,971 rows in the first real
batch, down to -596 s). These rows are kept; analysis decides how to treat them.

Optional protobuf fields that are absent are stored as null, never as the protobuf
default (0 or empty string). In particular, a null `stop_schedule_relationship` means
the feed omitted it; GTFS-Realtime defines the default as `SCHEDULED`.

Schedule relationships are kept at both levels because they mean different things: the
trip-level value says whether the whole trip is scheduled, added, or canceled; the
stop-level value says whether this one stop is served, skipped, or has no data. One is
never copied into the other.

Delay values are stored exactly as BART publishes them (seconds, negative when early).
They are not recomputed from `predicted_arrival`, and they are kept even when the
update carries a delay but no absolute time.

## Deduplication key

```text
(feed_timestamp, trip_id, stop_id)
```

This is a **BART-specific fallback key**. The standard GTFS-Realtime way to identify a
stop within a trip is `stop_sequence`, because a trip may visit the same stop more than
once (loops, or turning back through a station). The general key would be
`(feed_timestamp, trip_id, stop_sequence)`. BART omits `stop_sequence` from every
update, so `stop_id` stands in for it.

- `feed_timestamp` identifies one BART publication. Two downloads of an unrefreshed
  feed have different filenames but the same feed timestamp, and are the same data.
- `trip_id` + `stop_id` identify one prediction within a publication.
- Successive snapshots of the same trip and stop are **not** duplicates: each is a
  separate observation of how the prediction evolved.

Deduplication happens in two places:

1. **Across files.** When several snapshots share a `feed_timestamp`, only the one
   with the earliest `collected_at` is used. This runs before partitioning, so
   identical snapshots on either side of an hour boundary can't land in two partitions.
2. **Within a file.** If a `(trip_id, stop_id)` pair repeats, the first is kept.

### Repeated-stop limitation

If a BART trip ever lists the same `stop_id` twice in one update, the fallback key
can't tell the two visits apart: the second visit is dropped as a duplicate and counted
in the run summary's `rows_duplicate_in_file`, so its prediction is lost. This is
acceptable for now because `stop_id` is platform-level (e.g. `M10-1` vs `M10-2`) and no
repeats were found in 65 real snapshots (70,971 stop-time updates) on 2026-10-09. If
`rows_duplicate_in_file` is ever non-zero, the key needs revisiting, for example by
deriving a sequence from each stop's position in the update or from static GTFS
`stop_times`.

## Idempotency

Every run rebuilds each hour partition from the raw snapshots and atomically replaces
`part.parquet` (write to a temp file, then rename). Rerunning over the same inputs
produces the same rows, never appended copies. Partitions whose raw files were later
deleted are left in place.

## Service date (provisional)

BART service runs past midnight, so the calendar date is not the service date, and
BART's feed omits `TripDescriptor.start_date`. The transformer therefore stores only an
**inferred** value, named `inferred_service_date` so it can't be mistaken for the real
one:

```text
inferred_service_date = local date of collected_at in America/Los_Angeles,
                        minus one day if the local time is before 03:00
```

The 03:00 cutoff is an assumption, not verified against BART's schedule. **The
definitive service date will be determined during the static GTFS join**, by matching
each `trip_id` to its `service_id` in `trips.txt` and checking which dates that service
runs in `calendar.txt` / `calendar_dates.txt`. That step will add a separate
`service_date` column; `inferred_service_date` should not be used for analysis once it
exists.

## Excluded records

- **Quarantined files** (listed in `_quarantine.jsonl` with a reason): unrecognized
  filename, unreadable file, or bytes that fail GTFS-Realtime validation. Raw files are
  never moved or modified.
- **Skipped rows** (counted in the run summary): stop-time updates missing `trip_id` or
  `stop_id`, and duplicates removed by the key above.
