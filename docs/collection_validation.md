# Collection validation: 24-hour production test

**Result: PASS.** 1,440 of 1,440 polling intervals completed, both feeds were saved in
every cycle, and every one of the 2,882 snapshots is a valid, unmodified GTFS-Realtime
file. One automatic service restart (an OS security update) occurred and caused no
missed interval or lost data. The `PROJECT_SPEC.md` initial success criterion is
achieved.

This report covers only the original 24-hour window, audited on 2026-10-12. The later
audit of the first 10.5 days (to 2026-10-20) is a separate checkpoint:
[data_checkpoint_2026-10-20.md](data_checkpoint_2026-10-20.md). It found 15,088 of 15,088
intervals completed, and 27 temporary fetch failures all recovered on retry. That export
was the final backup: collection then ended and the server was retired
([deployment.md](deployment.md#status-retired)).

## Test interval

| | Start | End (exclusive) |
|---|---|---|
| UTC | 2026-10-10 08:17:48 | 2026-10-11 08:17:48 |
| Pacific | 2026-10-10 01:17:48 PDT | 2026-10-11 01:17:48 PDT |

The start is the collector's first start after the post-deployment reboot test. The
deployment is described in [deployment.md](deployment.md): a 1 vCPU / 1 GB Ubuntu
24.04 server running the `bart-collector` systemd unit from commit `81a1b58`.

**Success criterion** (from `PROJECT_SPEC.md`): at least 1,426 of 1,440 polling
cycles (99%) complete, with no lost or corrupt data. Valid feeds with zero entities
(e.g. no alerts in the feed) count as successful.

## Methodology

The audit was read-only: the collector was not stopped, restarted, or modified, and
no files were written on the server. Audited 2026-10-12.

- **Intervals.** The window is divided into 1,440 one-minute intervals starting at
  08:17:48 UTC. A `cycle_complete` event belongs to interval
  `floor((event time - start) / 60 s)`. An interval is *completed* if it contains at
  least one completed cycle, *missing* if it contains none, and *duplicate* if it
  contains more than one.
- **Events** come from the collector's JSON logs in the systemd journal. The rotated
  log file (`logs/collector.log-*.gz` plus `collector.log`) was parsed separately as a
  cross-check and gives identical counts.
- **Snapshots** are the `.pb` files whose filename timestamp (UTC collection time)
  falls in the window. Each was:
  - parsed with the project's validator (`gtfs-realtime-bindings`, required header
    fields, non-zero `header.timestamp`);
  - matched one-to-one with its `snapshot_saved` log event;
  - checked for size equal to the logged byte count, feed timestamp equal to the logged
    one, and file modification time within 5 s of the logged collection time
    (detects overwrites or later edits).
- **Service events** come from systemd's journal entries for the unit and from the
  apt / unattended-upgrades logs.

## Results

### Polling

| Metric | Result |
|---|---|
| Expected polling intervals | 1,440 |
| Intervals with a completed cycle | **1,440 (100.00%)** |
| Completed cycles | 1,441 |
| Cycles with both feeds saved | 1,441 (100%) |
| Missing intervals | 0 |
| Duplicate intervals | 1 (2026-10-11 06:29:48–06:30:48 UTC: cycles at 06:29:51 and 06:30:23, around the restart below) |
| Largest gap between cycles | 62.23 s (2026-10-11 05:02:51 → 05:03:53 UTC) |
| Gaps over 61 s | 3 (61.09 s, 61.69 s, 62.23 s) |
| Smallest gap | 32.65 s (the restart, below) |
| First / last cycle in window | 2026-10-10 08:17:51 / 2026-10-11 08:17:23 UTC |

### Failures and restarts

| Metric | Result |
|---|---|
| Failed fetch attempts (retries) | 0 |
| Snapshots that needed a retry | 0 |
| Warnings / errors in collector logs | 0 / 0 |
| `intervals_missed`, `feed_failed`, `snapshot_exists`, `storage_failed` events | 0 |
| systemd automatic restarts after a failure (`NRestarts`) | 0 |
| Service restarts of any kind | **1**, at 2026-10-11 06:30:22 UTC (23:30:22 PDT) |

**The restart.** Ubuntu's daily unattended upgrade (06:29:25–06:31:26 UTC) installed
security updates including `libssl3t64` and `openssl`. Its `needrestart` step then
ran `systemctl restart bart-collector.service` along with sshd, journald, and other
services using the old library. The collector stopped cleanly and started again in
the same second. Because restarts resume on a fresh 60 s schedule, the next cycle came
32.65 s after the previous one, so no interval was lost (it produced the one duplicate
interval above). This was a known risk, documented in `deployment.md` before the test.

### Snapshots

| Metric | `trip_updates` | `alerts` |
|---|---|---|
| Snapshots in window | 1,441 | 1,441 |
| Valid | 1,441 | 1,441 |
| Valid with zero entities | 0 | 1,333 |
| Size on disk (bytes, apparent) | 32,377,805 | 57,730 |
| Size on disk (bytes, allocated) | 35,188,736 | 5,902,336 |

Trip updates were never empty, even overnight. Alerts were empty (no alerts in the feed)
in 1,333 snapshots; these are valid feeds and count as successful.

| Integrity check | Result |
|---|---|
| Invalid or corrupt protobuf files | 0 |
| Zero-byte files | 0 |
| Leftover temporary files (`.*.tmp`) | 0 |
| Filename collisions (`snapshot_exists` events, duplicate logged paths) | 0 |
| Overwritten or modified files (size, feed timestamp, or mtime mismatch) | 0 |
| Logged snapshots with no file / files with no log event | 0 / 0 |
| Consecutive snapshots with an unchanged feed timestamp | 0 |

### Storage

| Item | Size |
|---|---|
| Raw snapshots, 24-hour window | 32.4 MB apparent, 41.1 MB allocated |
| Raw snapshot directory at audit time (5,092 files, includes before/after window) | 55.2 MB apparent |
| Collector log | 136 KB current + 118 KB compressed archive (2026-10-10 08:11 → 10-12 00:00) |
| systemd journal (whole server, bounded by journald) | 26.0 MB |

**Projected growth** at the observed rate (30 days): about **0.97 GB** of snapshot
data, **1.23 GB allocated on disk**. Most of the difference is small alert files each
taking a 4 KB block. Compressed logs add roughly 2 MB per month, and logrotate keeps
14 days. With 22.2 GB free, the disk lasts about 18 months at this rate. Weekday
daytime service may run larger than this Saturday-to-Sunday window.

### Service at audit time

| Item | Value |
|---|---|
| State | active (running), enabled |
| Running since | 2026-10-11 06:30:22 UTC (after the restart above) |
| Memory | 58.6 MB current, 58.9 MB peak |
| Disk | 22.2 GB available of 24.9 GB (11% used) |

### Log rotation

The first rotation happened at the second daily run (2026-10-12 00:00 UTC). On its
first run, logrotate only recorded the new log in its state file. The archive
`collector.log-20261012.gz` covers 2026-10-10 08:11:07 to 2026-10-12 00:00:23 without
gaps. The live log continues from the next cycle, so no lines were lost at truncation.
Both files are mode 0640, owned by `bart`.

### Backup

All 5,092 snapshots present at 2026-10-12 02:36:09 UTC (55,176,276 bytes) were copied
to a dated local backup. A path-and-size manifest and the SHA-256 of every file match
the server copy, and all files pass the validator locally. The server copy was not
changed. The backup is under the git-ignored `data/raw/`.

## Conclusion

| `PROJECT_SPEC.md` initial criterion | Result |
|---|---|
| ≥ 99% of expected polling intervals (≥ 1,426 of 1,440) | **Pass**: 1,440 (100%) |
| Avoid overwriting snapshots | **Pass**: 0 collisions, 0 modified files |
| Every stored protobuf file validates | **Pass**: 2,882 of 2,882 |
| Recover automatically from temporary network failures | **Not exercised in this window**: no network failure occurred (0 retries). Covered by unit tests here; exercised later (27 recovered retries, see the [2026-10-20 checkpoint](data_checkpoint_2026-10-20.md#collection)) |
| Logging sufficient to identify missing intervals and failures | **Pass**: every cycle and the restart are visible in the logs |
| Restart without corrupting previously collected data | **Pass**: one live restart, no corruption or loss |

**The initial success criterion passes.**

## Limitations

- **Network-failure recovery was not exercised in this window.** No fetch failed, so
  here retries and backoff are verified only by the test suite. The 10.5-day checkpoint
  later recorded 27 first-attempt failures, every one saved on the second attempt.
- **One window.** Saturday 01:17 PDT to Sunday 01:17 PDT. Weekday service levels,
  holidays, BART outages, and daylight-saving changeovers were not covered. The 10.5-day
  checkpoint adds weekdays and one holiday, but still no daylight-saving change or long
  outage.
- **Automatic security restarts remain possible.** `needrestart` will restart the
  collector after future library updates unless it is excluded (see
  `deployment.md`). Each restart costs at most part of one interval.
- **Second-resolution filenames.** Collection times in filenames are whole seconds;
  sub-second times are in the logs.
- **Interval accounting** uses the log event time of `cycle_complete`, which is up to
  about 1 s after the poll began.
