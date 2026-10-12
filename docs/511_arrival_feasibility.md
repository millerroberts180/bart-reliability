# 511 stop-observation feasibility audit (BART)

**Question:** can the 511 regional historical feed (`stop_observations.txt`) give this
project an independent reference for when BART trains reached stops, either for a
standalone historical analysis or to label our collected October predictions?

**Conclusion: suitable only as an observed-arrival proxy. Not independent ground truth.**

- The evidence indicates that 511's BART timestamps are **BART's final published arrival
  estimates, reconstructed by 511 from archived GTFS-Realtime trip updates**. That is the
  same construct as this project's `observed_arrival_proxy`, so comparing BART's
  predictions against them is circular.
- They are also sparse (16.1% of scheduled stop events, about 13% after removing
  artifacts), concentrated on one line, and affected by an origin-stop artifact and
  conflicting duplicates.
- The ETA-revision framing in `PROJECT_SPEC.md` stands. This audit records why 511 data
  does not change it.

In this report, "observation" and "observation timestamp" mean 511's
`observed_arrival_time` field. Neither implies that an arrival was physically observed.

## Sources

| Source | Retrieved | Used for |
|---|---|---|
| 511 datafeeds API, `operator_id=RG&historic=2026-09-so` (`https://api.511.org/transit/datafeeds`) | 2026-10-12 04:16:05 UTC | The archive: 575,202,077 bytes, SHA-256 `3dd13d18a50946b3dd0bd0ddf0704f061c3808f79515f5da4b4a77475aaf6fc7` |
| 511 live `transit/tripupdates` and `transit/vehiclepositions`, `agency=BA` | 2026-10-12 ~04:20 UTC | Which BART real-time inputs 511 receives |
| [Interline, "Observed stop arrivals and departures through the SF Bay Area"](https://www.interline.io/blog/mtc-regional-stop-observations/) (Drew Dara-Abrams, 2022-07-15) | 2026-10-12 | How 511 derives stop observations |
| [511 Open Data FAQs](https://511.org/open-data/faqs) | 2026-10-12 | Historic feed structure and availability |
| [511 Transit open data page](https://511.org/open-data/transit) | 2026-10-12 | The `historic` parameter |
| 511 SF Bay Open Data Specification – Transit (PDF, 2025-05) | 2026-10-12 | Could not be text-extracted with local tools; **not read** |
| BART direct static GTFS `2026-10-08` and this project's real-time export (2026-10-10 to 10-12) | (existing) | Identifier comparison |

## Data handling

- The token was read from the git-ignored `.env` inside the downloading process. It was
  sent only as a request parameter and never appeared in a command, log, error message,
  or file.
- The archive, the BART subset extracted from it, and the provenance file
  (`RG_2026-09-so.provenance.json`, with `api_key=<redacted>`) live under the
  git-ignored `data/raw/511/2026-09/`. A scan of the repository, the 511 data files, and
  Git history found the token nowhere outside `.env`.

## Methodology

1. Download with `bart-511-download`.
2. Stream BART's rows out of the ZIP into all-string Parquet. The 2.9 GB
   `stop_observations.txt` is never extracted.
3. Compute coverage, identifier matching, and integrity with `bart-511-audit` against
   the project warehouse (BART's direct static GTFS).
4. Test identifiers four ways: exact, namespaced, normalized, and schedule-based.
5. Inspect a deterministic stratified sample: 113 trips with at least 5 observations,
   2 per route × daypart × weekday/weekend, ordered by hash.
6. Compare the documented derivation method with what the data and 511's live BART
   feeds show.

```bash
.venv/bin/bart-511-download --historic 2026-09-so --out-dir data/raw/511/2026-09
.venv/bin/bart-511-audit --zip data/raw/511/2026-09/RG_2026-09-so.zip \
    --bart-dir data/raw/511/2026-09/bart --first-date 20260901 --last-date 20260930
```

The audit prints JSON to stdout. Write any copy of it under git-ignored `data/`.

## Documented facts

These are statements from 511 and Interline/MTC documentation, quoted or closely
paraphrased:

1. **Source.** Stop observations are "derived retrospectively using an archive of the
   Regional GTFS Realtime Feed (updated every 15 seconds)" (Interline).
2. **Trip-update method.** "When an agency supplies GTFS Realtime trip updates, our
   workflow identifies the final `TripUpdate` sent before a vehicle reaches a given stop"
   and "extracts the most recent `StopTimeUpdate`" (Interline).
3. **Vehicle-position method.** Where an agency supplies vehicle positions, they are
   snapped to the route shape to decide which update to use (Interline).
4. **Status.** Observations are "inferred from public GTFS Realtime data feeds", with
   possible errors from GPS, CAD/AVL, feed emission, and aggregation (Interline).
5. **Format.** Historic feeds namespace IDs, rewrite calendars into `calendar_dates.txt`,
   and offer `stop_observations.txt` from March 2022 onward (511 FAQ).
6. **Gap.** None of the documents read describes BART specifically, or says whether BART
   supplies vehicle positions or actual times.

## Empirical observations

Everything here was measured in this study.

### Archive and BART records

- **Contents.** The archive is the full regional GTFS for all Bay Area operators. Its
  2,927,718,527-byte `stop_observations.txt` has these columns: `trip_id`,
  `trip_start_time`, `schedule_relationship`, `service_date`, `vehicle_id`,
  `stop_sequence`, `observed_arrival_time`, `observed_departure_time`, `uncertainty`,
  `dwell_time_secs`, `scheduled_dwell_time_secs`, `route_id`, `agency_id`,
  `direction_id`, `from_stop_id`, `to_stop_id`, `scheduled_arrival_time`, and
  `scheduled_departure_time`.
- **Time format.** Times are local GTFS service-day times (`HH:MM:SS`, which can pass
  24:00:00).
- **BART.** BART is agency `BA` (`America/Los_Angeles`).

| | Value |
|---|---|
| BART rows | 67,871 |
| Service dates | 2026-09-01 to 2026-09-30 (30 of 30) |
| `observed_arrival_time` populated | 67,835 (all but 36 cancelled rows) |
| `observed_departure_time` populated | 67,835, and **identical to the arrival field in every row** |
| `schedule_relationship` | 0 (scheduled) 66,527; 1 (`ADDED`) 1,308; 3 (`CANCELED`) 36 |
| Distinct stops | 97 of 105 BART platform stops |
| `trip_start_time` | never populated |
| `vehicle_id` | `3-door` 57,953; `2-door` 9,918 |
| `uncertainty` | 30 in 67,026 rows (98.8%); 0 in 845 |
| `dwell_time_secs` | most common values 18, 24, 48, 30, 36 |

### Coverage

| | Count | Share |
|---|---|---|
| Scheduled BART trip-days | 30,400 | |
| Trip-days with at least one observation | 18,218 | 59.9% |
| Scheduled stop events | 413,188 | |
| **Observed stop events (scheduled trips)** | **66,527** | **16.1%** |

### Origin artifact

- **16,264** observations are at a trip's first stop, and their median
  observed-minus-scheduled time is **+78 minutes**. That isn't plausible as an arrival.
- **15,580** of the 15,598 single-observation trip-days are exactly one such origin row.
  Most "observed" trips therefore contribute no usable timestamp.

### Duplicate conflicts

- **1,069** `(service_date, trip_id, stop_sequence)` keys appear more than once.
- **1,015** of them carry **different timestamps**, up to 2,292 s apart. Example: trip
  `1965216` at SFO, `stop_sequence` 27, 24:14:32 and 24:15:09.
- 47 rows are exact duplicates.

### Usable subset and route imbalance

Usable means non-origin observations on trips with more than one observation.

| | Value |
|---|---|
| Rows | **50,245**: 13.1% of the 382,788 non-origin scheduled stop events |
| Trip-days | 2,562 (8.4% of scheduled) |
| **Route imbalance** | Yellow-S 41,076 (**82%**); Yellow-N 2,155; Orange-N 2,013; Blue-N 1,770; Green-N 1,029; Orange-S 911; Blue-S 878; Green-S 241; Red-S 140; Red-N 32 |
| Observed minus scheduled | p5 +45 s, p25 +74 s, median +99 s, p75 +152 s, p95 +609 s |
| Earlier than scheduled | 0.5% |
| Within ±5 min of schedule | 88.5% |
| Consecutive timestamps decreasing | 347 of 47,683 pairs (0.7%) |

### Stratified sample

113 trips, covering all 10 routes, 5 dayparts, weekday and weekend:

- **Ordering.** 1,488 of 1,570 consecutive pairs increase in time and 3 are equal. All
  79 decreases involve the origin artifact.
- **Consecutive stations.** `from_stop_id` equals the previous `to_stop_id` in 1,551 of
  1,570 pairs. Time between consecutive observed stations differs from schedule by a
  median of +1 s (p5 -54 s, p95 +49 s).
- **Versus schedule.** Median +71 to +131 s by daypart.
- **Timezone.** Times are local service-day times: 9,048 are after 24:00:00, the maximum
  is 26:42:55, and 0.0015% differ from schedule by more than 3 hours. No UTC offset.

### Identifiers

| Kind | Regional form | Exact | Namespaced | Normalized |
|---|---|---|---|---|
| Trip | `BA:<trip_id>:<YYYYMMDD>`; the suffix is the feed date (`20260930`) for every trip; `ADDED` trips have none | 0 / 4,417 | 0 | **4,417 / 4,417** |
| Stop | numeric platform code, e.g. `900101` | 0 / 103 | 0 | **103 / 103** (= BART `stop_code`; names identical) |
| Route | `BA:<route_short_name>`, e.g. `BA:Blue-N` | 0 / 14 | 0 | **14 / 14** |
| Service | equals the trip ID; 132,510 running dates in `calendar_dates.txt` | | | |

- **Schedule-based.** All 57,188 regional stop times are identical to BART's own
  (trip, sequence, stop, arrival, departure).
- **Observations.** 66,563 of 67,871 rows (98.07%) match a BART static trip and stop
  time, all with agreeing stop and scheduled time. The other 1,308 rows are `ADDED`
  trips.
- **Our October predictions.** They map to regional keys for 1,493,809 of 1,521,621
  rows (98.17%), and all 15,869 eligible ETA-revision events map.

### BART real-time inputs at 511

- **No BART vehicle positions.** 511's live BART vehicle-positions feed had **0
  entities**.
- **Trip updates mirror BART.** 511's BART trip updates match BART's direct feed: trip
  IDs like `1973161`, vehicle label `3-door`, uncertainty 30.
- **The fields echo BART's prediction feed:**
  - `vehicle_id` holds the trip-update vehicle **label**, not a vehicle identifier;
  - `uncertainty` is BART's prediction constant, 30;
  - `dwell_time_secs` takes exactly the values of BART's predicted departure-minus-arrival
    gaps (18, 24, 30, 36, 48 s), yet the departure field always equals the arrival field.
- **Never early.** Observed minus scheduled is almost never negative (0.5%), like BART's
  published delays (minimum 0).
- **Close to our proxy.** The distribution resembles our own proxy's final stable estimate
  minus schedule on the October data: median +99 s vs +118 s, p25 +74 vs +88 s. The
  months differ, so this comparison is circumstantial.

## Inferences

These follow from the facts and observations above but are **not documented by 511 or
BART**:

1. **The evidence indicates these are BART's final published arrival estimates,
   reconstructed by 511 from archived trip updates.** 511 documents the "final
   `TripUpdate` before a vehicle reaches a stop" method (fact 2) and has no BART vehicle
   positions for the alternative method (fact 3). Every BART-specific field echoes BART's
   prediction feed.
2. **They are not independent vehicle observations,** since there are no BART positions
   to snap, **and not agency-supplied actual times,** since nothing in the documents or
   the data indicates BART sends any.
3. **They are circular for evaluating BART's predictions.** A label derived from the last
   prediction measures prediction revision, exactly like `observed_arrival_proxy`. They
   cannot measure physical arrival accuracy.
4. **The origin artifact and conflicting duplicates probably come from the
   reconstruction itself.** For example, it may be reacting to trips appearing or
   repeating in the archive. The cause is undocumented.

## Assessment

- **A standalone September historical analysis is not supported.** The timestamps are
  not independent of the predictions (inference 3). Only about 13% of non-origin stop
  events are usable, and 82% of those are on Yellow-S, so any estimate would be biased
  by which trips 511 happened to reconstruct.
- **The future October archive is useful only for comparing 511's 15-second
  reconstruction with our 60-second proxy.** Identifiers would map (98.17% of our rows),
  but the timestamps would again be BART's final estimates. They could check how much our
  60-second sampling and tier rules change the endpoint. They could not turn ETA
  revision into accuracy, and coverage would likely be similarly sparse.
- **ETA revision remains the primary framing.** 511 data stays at most an optional
  cross-check unless 511 or BART documents an independent BART source and coverage
  improves.

## Limitations

- One month (September 2026) and one archive. Coverage may vary by month.
- The provenance conclusion combines documented general methodology with
  circumstantial BART-specific evidence. 511 has not confirmed it. Asking
  `511sfbaydeveloperresources@googlegroups.com` how BART observations are derived would
  settle it.
- The vehicle-position check was one live snapshot, although the September fields show
  no sign of position-based observations.
- The 511 specification PDF could not be read locally.
- The October conclusions are projections. No October archive exists yet.

## Code

- `src/bart_reliability/open511/download.py` (`bart-511-download`): token-safe
  download with sanitized provenance.
- `src/bart_reliability/open511/extract.py`: streaming, all-string agency subset from a
  regional ZIP.
- `src/bart_reliability/open511/ids.py`: verified identifier rules.
- `src/bart_reliability/open511/audit.py` (`bart-511-audit`): coverage, matching, and
  integrity metrics.
- `tests/test_open511.py`: synthetic tests; no network and no real token.
