# Data checkpoint: 2026-10-20

A read-only audit of the production collector's first 10.5 days, a verified copy of
every snapshot, and a new local warehouse built from it. This is a data checkpoint: no
model was fitted or scored on it. The next evaluation is preregistered in
[modeling_plan.md](modeling_plan.md#preregistered-evaluation-2026-10-20-checkpoint).

The data measures **ETA revision**, not arrival accuracy. Revisions are measured against
BART's own final stable published estimate, a circular reference
([observed_arrival_proxy.md](observed_arrival_proxy.md)). More data does not change that.

**Result.** 15,088 of 15,088 polling intervals completed, all 30,180 snapshots are valid
and unmodified, the local copy matches the server's SHA-256 for every file, and every
warehouse quality check passes. The collector was not stopped, restarted or modified.

The earlier 24-hour production test is a separate, narrower report:
[collection_validation.md](collection_validation.md).

## Cutoff and period

| | |
|---|---|
| Export cutoff | **2026-10-20 19:40:00 UTC** (12:40:00 PDT) |
| Rule | Every completed `.pb` whose filename collection time is before the cutoff |
| Collected | 2026-10-10 08:11:07 UTC to 2026-10-20 19:39:23 UTC (251.5 h) |
| Audited | 2026-10-20, read-only. Inventory, SHA-256 and the project validator ran on the server at the lowest CPU and I/O priority, and nothing was written there |
| Server code | Commit `81a1b58`. Its validator differs from current `main` only in a docstring |
| Processing code | `bart-transform` and `bart-build-warehouse` from code identical to `main` at `2a0788a` |

The server is identified only by a local SSH alias. No address is recorded in any
manifest or document.

## Collection

The methodology is the one in [collection_validation.md](collection_validation.md#methodology),
applied to the whole period. Intervals are counted from the collector's first start
(2026-10-10 08:11:07 UTC).

| Metric | Result |
|---|---|
| 60 s intervals with a completed cycle | **15,088 of 15,088 (100.00%)**. The 99% threshold is 14,938 |
| Counted from the 24-hour test start (08:17:48 UTC) | 15,082 of 15,082 |
| Completed cycles | 15,090, every one saving both feeds |
| Missing / duplicate intervals | 0 / 1 (the 2026-10-11 restart) |
| Largest gap between cycles | 64.7 s (2026-10-12 13:11:23 → 13:12:28 UTC, an alerts retry) |
| Gaps over 61 s / over 90 s | 32 / **0** |
| Smallest gap | 32.7 s (the 2026-10-11 restart) |
| Snapshots per UTC date, each feed | 1,440 on every full date; 950 on 10-10 and 1,180 on 10-20 (start and cutoff) |

**Retries.** 27 fetch attempts failed on the first try, and all 27 snapshots were saved
on the second: 26 trip-update requests closed by the server without a response, and one
alerts read timeout. There were no `feed_failed`, `intervals_missed`, `snapshot_exists`
or `storage_failed` events, and no errors. Network-failure recovery, which the 24-hour
test could not exercise, has now worked in production.

**Restarts.** The collector started three times: the first start (2026-10-10 08:11 UTC),
after the reboot test (08:17), and after `needrestart` restarted it for an OpenSSL update
(2026-10-11 06:30). Both restarts are in the 24-hour report. Since then one process has
run without interruption, with systemd `NRestarts` 0, and unattended upgrades on later
days did not restart it.

**Logs.** The systemd journal and the rotated log files each hold the same 45,300
collector events, so no lines were lost at rotation.

## Snapshots and validation

| | `trip_updates` | `alerts` |
|---|---|---|
| Snapshots | 15,090 | 15,090 |
| Valid (server and local) | 15,090 | 15,090 |
| Bytes | 381,935,378 | 3,389,821 |
| Valid with zero entities | 0 | 5,940 |
| Entities per snapshot | 1 to 121 | 0 to 4 |

| Integrity check | Result |
|---|---|
| Invalid, zero-byte or malformed-name files | 0 |
| Leftover temporary files | 0 |
| Snapshots sharing a feed timestamp / byte-identical files | 0 / 0 |
| Logged snapshots with no file / files with no log event | 0 / 0 |
| Size, feed timestamp or entity count differing from the log | 0 |
| File modification time vs logged collection time | at most 0.026 s |

Trip updates were never empty, even overnight: at least one entity, and the smallest
file is 76 bytes. Empty alert feeds are valid and count as successful polls.

## Server state at the audit

| Item | Value |
|---|---|
| Service | active and enabled; running since 2026-10-11 06:30:22 UTC, `NRestarts` 0 |
| Memory | 35 to 59 MiB when checked; peak 113 MiB (58.9 MB at the 24-hour audit) |
| Disk | 21.7 GB free of 24.9 GB (13% used) |
| Raw snapshots | 385 MB apparent, 454 MB allocated |
| Logs / journal | 1.7 MB / 100 MB |
| Growth | about 1.3 GB per 30 days allocated, so roughly 16 months of free space |
| Pending | a reboot for two kernel updates (`/var/run/reboot-required`). Automatic reboot is off, and the audit did not reboot |

## Transfer

| | |
|---|---|
| Manifest | `data/raw/server_exports/2026-10-20/audit/export_manifest.tsv` (5,764,673 bytes, SHA-256 `e74816ca44bbca95f767690553f852ff03aa62953fff58a2534a54f638b6f509`) |
| Manifest columns | path, feed, bytes, SHA-256, collection time, feed timestamp, entity count, validity, server modification time |
| Also | `export_manifest.json` (summary and collector state at listing), `server_sha256.txt` |
| Copy | `rsync --files-from --ignore-existing --partial-dir` after a dry run: exactly the manifest's list, never overwriting |
| Local copy | `data/raw/server_exports/2026-10-20/gtfs_rt/`: 30,180 files, 385,325,199 bytes |
| Verification | count, bytes and SHA-256 of every file match the manifest; nothing missing or extra |
| Earlier exports | the 5,092 files of the 2026-10-12 export and 15,858 of the 2026-10-15 export are identical to the server's |
| Server afterwards | all 30,180 files re-hashed unchanged; the server copy was not removed |

Files collected after the cutoff stay on the server and are not part of this checkpoint.

## Processing and warehouse

**Transformer.** `bart-transform` read 15,090 trip-update snapshots into 10,593,789 rows
in 252 hourly partitions, and 15,090 alert snapshots into 10,130 observations of 27
versions. Nothing was quarantined or deduplicated. A second run produced byte-identical
output. Output: `data/processed/server_export_2026-10-20/` (1,013 files, 46,320,608
bytes).

**Warehouse.**

| | |
|---|---|
| File | `data/warehouse/bart_checkpoint_2026-10-20.duckdb` |
| Size | 45,101,056 bytes |
| SHA-256 | `19dd5cfc686bed4f223adbfe5c5d26ef8385e5d1a152da5aa2be7af9378e55cc` |
| Static GTFS | `data/raw/gtfs_static/2026-10-08/google_transit.zip`, SHA-256 `affdc4d70cac01f71e54f049c754ba36824a885edcdef2ef8b024820c9e93080` |
| Configuration | `config/eta_revision.toml` and `config/alert_annotations.csv`, both unchanged from the 2026-10-15 checkpoint |
| Quality checks | 11 `eta_revision_quality_checks` and 10 `alert_quality_checks`, **0 failures** |
| Warning | `feed_info.txt` validity (to 2026-08-30) does not cover the calendar; service dates come from the calendar |
| Consistency | Same 44 tables and views and 442 columns as the 2026-10-15 checkpoint. Events and examples for service dates 2026-10-09 to 10-14 are identical; 10-15 differs because it was partial then |

**Join rates** (all 10,593,789 predictions):

| Match | Rate |
|---|---|
| Trip | 98.30% |
| Stop | 100% |
| Scheduled stop time | 98.29% |
| Usable for primary metrics | 97.88% (97.6% to 98.7% by service date) |

| Unmatched rows (180,993) | Rows | Trips |
|---|---|---|
| Antioch extension (`E20`, `E30`) | 159,980 | 126 |
| Trips BART added outside the schedule | 20,082 | 656 |
| Real-time platform differs from the schedule | 770 | 189 |
| Other trip IDs not in the schedule | 143 | 7 |
| Cancelled trips not in the schedule | 18 | 3 |

Separately, 43,081 matched rows at SFO, which trains visit twice, are ambiguous and
excluded from primary metrics.

**ETA-revision dataset.**

| | Count |
|---|---|
| Candidate events | 134,319 |
| Eligible | 111,842 |
| Tier A / tier B | 104,235 / 7,607 |
| Examples (all eligible) at 5 / 10 / 15 min | 111,769 / 111,792 / 111,782 (99.93% / 99.96% / 99.95% of eligible) |
| Tier A examples at 5 / 10 / 15 min | 104,235 / 104,232 / 104,229 |

| Exclusion | Events |
|---|---|
| `trip_origin` | 5,584 |
| `trip_left_feed` | 5,541 |
| `added_trip` | 4,384 |
| `excluded_line` | 2,292 |
| `ambiguous_repeated_stop` | 1,743 |
| `no_confirming_snapshot` | 1,011 (all on 10-20, where the data ends at the cutoff) |
| `unstable_final_estimate` | 753 |
| `cancelled_trip` | 726 |
| `unmatched_stop_time_not_found` | 268 |
| `no_downstream_progression` | 115 |
| `insufficient_observations` | 29 |
| `unmatched_trip_not_found` | 22 |
| `no_horizon_history` | 9 |

`collection_gap` and `skipped_or_no_data_stop` never occurred.

**Alerts.** 27 alerts, each with one content version, in 31 visibility intervals. None
has a cause, effect or structured active period, and every one applies system-wide.
Alert state is known for 100% of revision examples, from snapshots at most 61 s old.
Six versions carry manual categories (5 incident-like, 1 planned notice); the 21 later
versions are `unclassified`. Suggested categories for them are drafted, pending
manual review, in [alert_annotation_review_2026-10-20.md](alert_annotation_review_2026-10-20.md).
The alert feed was empty all day on 2026-10-16.

## New in this data

- **Cancellations occur.** Trip-level `CANCELED` appeared on 9 of the 12 service dates
  (19,877 rows): 2 to 6 trips on most of those days, 29 on 2026-10-13. 726 events are
  excluded as `cancelled_trip`. No trip was marked `DELETED`.
- **No skipped stops.** Stop-level `schedule_relationship` was never populated, so no
  `SKIPPED` or `NO_DATA` record exists, and that rule is still covered only by
  synthetic tests.
- **No long outage.** No gap between cycles exceeded 65 s, so the 90 s `collection_gap`
  rule and the gap sensitivity remain untested on real data.

## Service days

A service day D runs from 03:00 on D to 03:00 on D+1, Pacific, the same cutoff as
`inferred_service_date`. It is **complete** when all 1,440 snapshots of that window
exist. Within complete days, trip-update snapshots were never more than 62 s apart.
There was no daylight-saving change (PDT throughout).

| Service day | Snapshots | Status | Events / eligible / tier A | Earlier use | Preregistered role |
|---|---|---|---|---|---|
| 10-09 Fri | 110 (7.6%) | partial: late-night tail | 40 / 22 / 18 | excluded | excluded |
| 10-10 Sat | 1,440 | complete | 11,674 / 9,464 / 8,778 | PR #7 training | training |
| 10-11 Sun | 1,440 | complete | 9,679 / 8,376 / 7,808 | PR #7 training | training |
| 10-12 Mon | 1,440 | complete | 13,749 / 12,031 / 11,287 | PR #7 training (holiday, weekday service) | training |
| 10-13 Tue | 1,440 | complete | 15,243 / 11,029 / 10,233 | PR #7 validation and interval calibration | training |
| 10-14 Wed | 1,440 | complete | 14,078 / 11,955 / 11,157 | PR #7 test and interval availability (spent) | training |
| 10-15 Thu | 1,440 | complete | 13,751 / 11,960 / 11,089 | local API and website replay day (as of 17:00 UTC); inspected | training |
| 10-16 Fri | 1,440 | complete | 13,894 / 11,954 / 11,032 | none | validation |
| 10-17 Sat | 1,440 | complete | 11,768 / 9,445 / 8,763 | none | validation |
| 10-18 Sun | 1,440 | complete | 9,706 / 8,416 / 7,937 | none | validation |
| 10-19 Mon | 1,440 | complete | 13,751 / 12,022 / 11,291 | none | **sealed test** |
| 10-20 Tue | 580 (40.3%) | partial: ends at the cutoff | 6,986 / 5,168 / 4,842 | none | excluded |

Before this checkpoint, 2026-10-16 to 10-19 were in no warehouse.

### What has been seen of the later days

This is the complete record of what this checkpoint exposed about 2026-10-16 onward:

- **Counts by day.** Snapshots, events, eligibility and exclusions by reason, join rates,
  alert visibility and cancelled trips were computed for every service day, including
  2026-10-19, to judge completeness. These count data; none is an ETA revision value.
- **One pooled summary.** The standard `bart-build-warehouse` log prints pooled
  summaries over all service dates in the build: ETA revision by horizon for tier A and
  all eligible events, final-estimate spread and persistence distributions. It was printed
  for this build and seen. It pools 12 service dates. 2026-10-19 contributes 11,291 of the
  104,235 tier-A events (10.8%). The same log lists five "questionable" events (persistence
  outliers): two from 10-13 and one each from 10-14, 10-15 and 10-17, none from 10-19.
- **Nothing daily.** No revision value, distribution, model prediction or metric was
  computed or examined for any single later day. No pooled number influenced the split
  or the evaluation plan. The pooled summary and the 10-17 event are a limitation of
  the sealed test, not a breach; they are recorded so the test is not described as
  more untouched than it is.

## Artifacts

All of these are under `data/`, which is ignored by Git. None is committed:

| Artifact | Path |
|---|---|
| Raw snapshots | `data/raw/server_exports/2026-10-20/gtfs_rt/` |
| Audit files (manifest, SHA-256 list, server inventory, journal and log dumps, audit summary, verification results, transform and build logs) | `data/raw/server_exports/2026-10-20/audit/` |
| Processed Parquet | `data/processed/server_export_2026-10-20/` |
| Warehouse | `data/warehouse/bart_checkpoint_2026-10-20.duckdb` |

The warehouse stores the absolute Parquet path, so each checkpoint keeps its own
processed directory.

## Limitations

- **Circular reference.** Every revision is measured against BART's own final estimate.
  The checkpoint adds days, not an independent arrival source.
- **10.5 days of one season.** No daylight-saving change and one holiday (10-12). There
  are weekday, Saturday and Sunday schedules, but each appears on only a few days.
- **One collector.** No outage longer than 65 s happened, so gap handling is untested on
  real data. A server outage would cost intervals; there is no second collector.
- **Unreviewed alerts.** 21 of 27 alert versions are `unclassified` until reviewed. This
  affects only descriptive alert context; the model features do not use alerts.
- **Static archive.** Every day joins to the 2026-10-08 static GTFS. The Antioch extension
  and BART-added trips stay unmatched.
- **Pending reboot.** The kernel updates take effect only after a deliberate reboot. The
  collector restarts with the server; the reboot test cost no interval.
