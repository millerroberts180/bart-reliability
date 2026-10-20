# Alert annotation review: 2026-10-20 checkpoint

> **Status: REVIEW COMPLETE.** The project owner reviewed all 21 versions manually and
> confirmed every one as `incident_like` on 2026-10-20. The rows are in
> `config/alert_annotations.csv` with `reviewed_on` 2026-10-20, and they take effect on the
> next warehouse build. The checkpoint warehouse (`19dd5cfc…`) was built before the review
> and is deliberately not rebuilt, so it still shows these versions as `unclassified`.

The [2026-10-20 checkpoint](data_checkpoint_2026-10-20.md) contains 27 alert versions.
Six were reviewed on 2026-10-11. The 21 below appeared later.

## How the review was done

- **Draft from the published text only.** Suggestions were drafted using the rules in
  [service_alerts.md](service_alerts.md#how-planned-and-incident-like-are-determined) as
  they stood. No ETA outcome was used: no revision value, model result or alert-context
  statistic was consulted. The query read only the alert tables (`alert_versions`,
  `alert_visibility`, `alert_annotations`, `alert_informed_entities`).
- **Owner's manual confirmation, 2026-10-20.** The owner confirmed all 21 versions as
  `incident_like` and widened the `incident_like` rule to cover all of these:
  - active delays;
  - skipped stations;
  - stopped or suspended service;
  - recovery messages;
  - restoration-to-normal-service messages tied to an incident.

  The earlier `incident_like` rows already fit the widened rule.
- **What the feed gives.** Every version has the header "BART.gov Alert", the advisories
  URL, no cause, no effect and no structured active period. Each informs only agency
  `BART` (system-wide). The text is therefore the only evidence.
- **Visible in feed** is the first to the last snapshot that listed the version, in
  Pacific time (PDT). Snapshots are 60 s apart.

No version announces scheduled work, so none is `planned_notice`.

## Confirmed categories

| # | Alert | Visible in feed (PDT) | Published text | Draft suggestion | Confirmed 2026-10-20 | Basis under the confirmed rule |
|---|---|---|---|---|---|---|
| 1 | `BSA_1604` | Mon 10-12 18:25 – 18:31 | "Trains are not stopping in the Richmond and Daly City directions at San Leandro." | `incident_like` (borderline) | `incident_like` | Skipped station (unplanned service change) |
| 2 | `BSA_1605` | Mon 10-12 18:36 – 22:09 | "BART is recovering from an earlier problem.  Regular service has been restored to San Leandro station." | `incident_like` | `incident_like` | Recovery and restoration message, tied to the San Leandro incident of row 1 |
| 3 | `BSA_1607` | Tue 10-13 08:36 – 08:53 | "BART service has stopped between Antioch and Concord due to an equipment problem on the track between." | `incident_like` | `incident_like` | Stopped service with a specific cause (equipment problem) |
| 4 | `BSA_1608` | Tue 10-13 08:54 – 09:16 | "There is a major delay on the Antioch line due to an equipment problem on the track. BART service has stopped between Antioch and Concord stations. Tri Delta Transit is providing bus service between Concord and Antioch at this time. County Connection is providing bus service between Concord and North Concord on Bus 17." | `incident_like` | `incident_like` | Active major delay with a specific cause; stopped service |
| 5 | `BSA_1611` | Tue 10-13 09:16 – 09:47 | "There is a major delay on the Antioch line in all directions due to an equipment problem on the track. Normal BART service has resumed between Antioch and Concord stations." | `incident_like` | `incident_like` | Active major delay with a specific cause |
| 6 | `BSA_1612` | Tue 10-13 09:45 – 12:53 | "BART is recovering from an earlier problem. There is a 20-minute delay on the Antioch line in the SFO and Antioch directions due to an earlier equipment problem on the track." | `incident_like` | `incident_like` | Recovery message with delay and cause; same pattern as the reviewed `BSA_1550` |
| 7 | `BSA_1613` | Tue 10-13 12:58 – 13:10 and 14:33 – 15:32 | "There is a 20-minute delay on the Antioch line in the Antioch and SFO directions due to a PG&E power issue." | `incident_like` | `incident_like` | Active delay with a specific cause. Visible twice, replaced by `BSA_1614` in between |
| 8 | `BSA_1614` | Tue 10-13 13:11 – 14:32 | "There is a major delay on the Antioch line in the Antioch and SFO directions due to a PG&E power issue." | `incident_like` | `incident_like` | Active major delay with a specific cause |
| 9 | `BSA_1630` | Wed 10-14 06:21 – 06:24 | "There is a 20-minute delay in the SFO, Millbrae, and Berryessa directions due to an equipment problem on a train at 12th St. Oakland City Center." | `incident_like` | `incident_like` | Active delay with a specific cause |
| 10 | `BSA_1631` | Wed 10-14 06:24 – 06:55 | "BART is recovering from an earlier problem. There is a 20-minute delay in the Berryessa, SFO, and Millbrae directions due to an earlier equipment problem on a train at 12th St. station." | `incident_like` | `incident_like` | Recovery message with delay and cause |
| 11 | `BSA_1673` | Thu 10-15 08:53 – 08:55 | "There is a 10-minute delay on the Berryessa line in the Daly City direction due to police activity at San Leandro and Coliseum stations." | `incident_like` | `incident_like` | Active delay with a specific cause |
| 12 | `BSA_1674` | Thu 10-15 08:57 – 09:27 | "BART is recovering from an earlier problem. There is a 10-minute delay on the Berryessa line in the Daly City direction due to earlier police activity at San Leandro and Coliseum stations." | `incident_like` | `incident_like` | Recovery message with delay and cause |
| 13 | `BSA_1679` | Thu 10-15 14:52 – 15:26 | "BART is recovering from an earlier problem. There is a 10-minute delay on the Berryessa line in the Richmond, Daly City, and Berryessa directions due to earlier police activity." | `incident_like` | `incident_like` | Recovery message with delay and cause (no location given) |
| 14 | `BSA_1680` | Thu 10-15 15:27 – 15:53 | "BART is recovering from an earlier problem. There is a 10-minute delay on the Berryessa line in the Richmond and Daly City directions due to earlier police activity at Fremont." | `incident_like` | `incident_like` | Recovery message with delay and cause |
| 15 | `BSA_1687` | Thu 10-15 18:33 – 19:14 | "BART is recovering from an earlier problem. There is a 10-minute delay on the Berryessa line in the Berryessa and Dublin/Pleasanton directions due to earlier police activity at Bay Fair." | `incident_like` | `incident_like` | Recovery message with delay and cause |
| 16 | `BSA_1761` | Sat 10-17 05:49 – 06:10 | "There is a 20-minute delay on the Berryessa line in the Richmond, Berryessa, and Daly City directions due to an equipment problem on the track between Union City and South Hayward." | `incident_like` | `incident_like` | Active delay with a specific cause |
| 17 | `BSA_1762` | Sat 10-17 06:12 – 07:19 | "BART is recovering from an earlier problem. There is a 20-minute delay on the Berryessa line in the Berryessa, Richmond, and Daly City directions due to an earlier equipment problem on the track." | `incident_like` | `incident_like` | Recovery message with delay and cause |
| 18 | `BSA_1838` | Tue 10-20 07:19 – 07:27 | "There is a 10-minute delay on the Berryessa line in the Richmond and Daly City directions due to police activity at Hayward." | `incident_like` | `incident_like` | Active delay with a specific cause |
| 19 | `BSA_1839` | Tue 10-20 07:21 – 07:23 | "Trains are not stopping at Hayward Station in the Berryessa direction due to police activity." | `incident_like` (borderline) | `incident_like` | Skipped station with a specific cause (police activity) |
| 20 | `BSA_1840` | Tue 10-20 07:26 – 07:44 | "Trains are now making normal stops at Hayward." | leave `unclassified` (borderline) | `incident_like` | Restoration to normal stops, tied to the Hayward police incident of rows 18, 19 and 21. Treated like row 2 |
| 21 | `BSA_1841` | Tue 10-20 07:26 – 07:51 | "BART is recovering from an earlier problem. There is a 10-minute delay on the Berryessa line in the Richmond and Daly City directions due to earlier police activity at Hayward." | `incident_like` | `incident_like` | Recovery message with delay and cause |

**Result:** 21 `incident_like`.
- **Rows 1, 3 and 19** were borderline under the old rule, which mentioned only delays.
  The widened rule covers them.
- **Row 20** was drafted as `unclassified`. The owner classified it `incident_like` as a
  restoration message tied to an incident, consistent with row 2.

In `config/alert_annotations.csv`, each row's `basis` is the full published text, quoted.

## Decisions made

1. **Every row confirmed** as `incident_like` by the project owner on 2026-10-20.
2. **Service changes without a stated delay.** Skipped stations and stopped or suspended
   service are `incident_like`. The rule in `service_alerts.md` and the CSV header now say
   so.
3. **Restoration notices.** A restoration-to-normal-service message tied to an incident
   is `incident_like`, with or without the "recovering from an earlier problem" wording.

## Which days these touch

- Training days (2026-10-10 to 10-15): rows 1 to 15.
- Validation day 2026-10-17: rows 16 and 17. No new version appeared on 10-16 (the feed
  was empty all day) or on 10-18.
- Sealed test day 2026-10-19: no new version. Only the already-reviewed planned notice
  `BSA_560` was visible.
- Excluded partial day 2026-10-20: rows 18 to 21.

The selected model features do not use alerts
([modeling_plan.md](modeling_plan.md#allowed-features)). The review changes the
descriptive alert context of later builds, not the preregistered evaluation.

## Fingerprints

As recorded in `config/alert_annotations.csv`:

| # | Alert | `alert_fingerprint` |
|---|---|---|
| 1 | `BSA_1604` | `921daf59d94914dee96f3192e966e259d993e5652057a95a105acbcc6fd3985f` |
| 2 | `BSA_1605` | `290fb68a366c64dcb5ef11b9e461d83b9ff9db54bbe03f5c50ed29d4060e7512` |
| 3 | `BSA_1607` | `c66f5c268726a09eb49735a6e58120ed1405f0bf6a43c4962b65616bede22776` |
| 4 | `BSA_1608` | `151164c50a62d849ffe3518108b3da28d26817cf8bfe5e3729a5968067cbb0f1` |
| 5 | `BSA_1611` | `587ab0ba032e80bf5df9d2fb53a865c40905e615a280c5c5979be33b591f2d22` |
| 6 | `BSA_1612` | `5d65599e07fb2493d7a64bb8dc1d1836319f06f6e9e3cf262d83524360be1ad5` |
| 7 | `BSA_1613` | `c6b80fc34a556c28a39adc28c5bef61f529879631d0e7bd795acfd5347c66e1d` |
| 8 | `BSA_1614` | `4e68bb98f29a7241b85487faf678230b0879c8ddc6175b05cbbe3f1c432f80b1` |
| 9 | `BSA_1630` | `058f38ea41aa958eaea12d33ea6a5aedabcdb9d1dc7166fbf914b6e2ddaa104c` |
| 10 | `BSA_1631` | `b2d03ddc77d320b295262ca14356ab8a47587aa8dac2c2e00ebd491cd6de748b` |
| 11 | `BSA_1673` | `14bf3038e7dd95df92dedf73efce6ea0efd2922081ea67141e8c8d411a01950c` |
| 12 | `BSA_1674` | `573a4b2e8e82abe9ac117eaca25491c9fd3ccfc98e2e4e679c1eece32856829b` |
| 13 | `BSA_1679` | `7b54708e600e714589f5900f24ea12dbd094d48bf3b35977383caf7f0b0bf42b` |
| 14 | `BSA_1680` | `6917cd471b3ce989c3a91d2591363ac6a5ad0604e8fe402003a810f8dee79423` |
| 15 | `BSA_1687` | `281d29fcdbca29a84eed8ab2c77fbf772618ed2519b5bd892636a1fc1b33fbba` |
| 16 | `BSA_1761` | `5a9f6c269ae34c920565d046bae0930c185d34a48b004a2aa2d430f1edd6ab9b` |
| 17 | `BSA_1762` | `08cfe9af3e0fc4acaef2ae51b654cf32ca4e738bbd365cc2f63cc3ff9cdc4516` |
| 18 | `BSA_1838` | `23357a0fcb33ce11a08be3f0f6d1356d0750ef7c584765ba93bdec3dc0270012` |
| 19 | `BSA_1839` | `3af0dce0b79db85e83ae8ce88ee0988bc774acabdede07678705fe3131df9832` |
| 20 | `BSA_1840` | `3d359fb92903be6c8b533bacfa9429697914049f321ba430b73c407d354e20e3` |
| 21 | `BSA_1841` | `d9c035c2020dd6db5abe48c3e98ed162f09c2b1b7cc1b61a89992ac5fae9938b` |
