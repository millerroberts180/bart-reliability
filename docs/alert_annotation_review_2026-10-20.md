# Alert annotation review: 2026-10-20 checkpoint

> **Status: PENDING MANUAL REVIEW. Nothing here has been applied.**
> Every category below is a suggestion awaiting the project owner's confirmation.
> `config/alert_annotations.csv` is unchanged, and these 21 versions stay
> `unclassified` in every warehouse until confirmed rows are added there.

The [2026-10-20 checkpoint](data_checkpoint_2026-10-20.md) contains 27 alert versions.
Six were reviewed on 2026-10-11. The 21 below appeared later and have no category.

## How the suggestions were made

- **From the published text only,** using the written rules in
  [service_alerts.md](service_alerts.md#how-planned-and-incident-like-are-determined):
  - `planned_notice`: the text announces scheduled work or a recurring planned service
    change;
  - `incident_like`: the text reports a current or recent unplanned delay with a
    specific cause. The rule's examples include "recovering from an earlier problem".
- **No ETA outcome was used.** No revision value, model result or alert-context
  statistic was consulted. The query read only the alert tables (`alert_versions`,
  `alert_visibility`, `alert_annotations`, `alert_informed_entities`).
- **What the feed gives.** Every version has the header "BART.gov Alert", the advisories
  URL, no cause, no effect and no structured active period. Each informs only agency
  `BART` (system-wide). The text is therefore the only evidence.
- **Visible in feed** is the first to the last snapshot that listed the version, in
  Pacific time (PDT). Snapshots are 60 s apart.

No version announces scheduled work, so none is suggested as `planned_notice`.

## Suggested categories

| # | Alert | Visible in feed (PDT) | Published text | Suggested category | Rationale | Status |
|---|---|---|---|---|---|---|
| 1 | `BSA_1604` | Mon 10-12 18:25 – 18:31 | "Trains are not stopping in the Richmond and Daly City directions at San Leandro." | `incident_like` (**borderline**) | Reports a current, unannounced service change. States neither a delay nor a cause, so it falls outside the written rule | Pending your confirmation |
| 2 | `BSA_1605` | Mon 10-12 18:36 – 22:09 | "BART is recovering from an earlier problem.  Regular service has been restored to San Leandro station." | `incident_like` | "Recovering from an earlier problem" is the rule's own example. Follows `BSA_1604`. No delay length or cause is stated | Pending your confirmation |
| 3 | `BSA_1607` | Tue 10-13 08:36 – 08:53 | "BART service has stopped between Antioch and Concord due to an equipment problem on the track between." | `incident_like` | Current unplanned stoppage with a specific cause (equipment problem). A stoppage rather than a delay (text truncated as published) | Pending your confirmation |
| 4 | `BSA_1608` | Tue 10-13 08:54 – 09:16 | "There is a major delay on the Antioch line due to an equipment problem on the track. BART service has stopped between Antioch and Concord stations. Tri Delta Transit is providing bus service between Concord and Antioch at this time. County Connection is providing bus service between Concord and North Concord on Bus 17." | `incident_like` | Current major delay with a specific cause | Pending your confirmation |
| 5 | `BSA_1611` | Tue 10-13 09:16 – 09:47 | "There is a major delay on the Antioch line in all directions due to an equipment problem on the track. Normal BART service has resumed between Antioch and Concord stations." | `incident_like` | Current major delay with a specific cause | Pending your confirmation |
| 6 | `BSA_1612` | Tue 10-13 09:45 – 12:53 | "BART is recovering from an earlier problem. There is a 20-minute delay on the Antioch line in the SFO and Antioch directions due to an earlier equipment problem on the track." | `incident_like` | Recovery wording, delay and cause; same pattern as the reviewed `BSA_1550` | Pending your confirmation |
| 7 | `BSA_1613` | Tue 10-13 12:58 – 13:10 and 14:33 – 15:32 | "There is a 20-minute delay on the Antioch line in the Antioch and SFO directions due to a PG&E power issue." | `incident_like` | Current delay with a specific cause. Visible twice, replaced by `BSA_1614` in between | Pending your confirmation |
| 8 | `BSA_1614` | Tue 10-13 13:11 – 14:32 | "There is a major delay on the Antioch line in the Antioch and SFO directions due to a PG&E power issue." | `incident_like` | Current major delay with a specific cause | Pending your confirmation |
| 9 | `BSA_1630` | Wed 10-14 06:21 – 06:24 | "There is a 20-minute delay in the SFO, Millbrae, and Berryessa directions due to an equipment problem on a train at 12th St. Oakland City Center." | `incident_like` | Current delay with a specific cause | Pending your confirmation |
| 10 | `BSA_1631` | Wed 10-14 06:24 – 06:55 | "BART is recovering from an earlier problem. There is a 20-minute delay in the Berryessa, SFO, and Millbrae directions due to an earlier equipment problem on a train at 12th St. station." | `incident_like` | Recovery wording, delay and cause | Pending your confirmation |
| 11 | `BSA_1673` | Thu 10-15 08:53 – 08:55 | "There is a 10-minute delay on the Berryessa line in the Daly City direction due to police activity at San Leandro and Coliseum stations." | `incident_like` | Current delay with a specific cause | Pending your confirmation |
| 12 | `BSA_1674` | Thu 10-15 08:57 – 09:27 | "BART is recovering from an earlier problem. There is a 10-minute delay on the Berryessa line in the Daly City direction due to earlier police activity at San Leandro and Coliseum stations." | `incident_like` | Recovery wording, delay and cause | Pending your confirmation |
| 13 | `BSA_1679` | Thu 10-15 14:52 – 15:26 | "BART is recovering from an earlier problem. There is a 10-minute delay on the Berryessa line in the Richmond, Daly City, and Berryessa directions due to earlier police activity." | `incident_like` | Recovery wording, delay and cause (no location given) | Pending your confirmation |
| 14 | `BSA_1680` | Thu 10-15 15:27 – 15:53 | "BART is recovering from an earlier problem. There is a 10-minute delay on the Berryessa line in the Richmond and Daly City directions due to earlier police activity at Fremont." | `incident_like` | Recovery wording, delay and cause | Pending your confirmation |
| 15 | `BSA_1687` | Thu 10-15 18:33 – 19:14 | "BART is recovering from an earlier problem. There is a 10-minute delay on the Berryessa line in the Berryessa and Dublin/Pleasanton directions due to earlier police activity at Bay Fair." | `incident_like` | Recovery wording, delay and cause | Pending your confirmation |
| 16 | `BSA_1761` | Sat 10-17 05:49 – 06:10 | "There is a 20-minute delay on the Berryessa line in the Richmond, Berryessa, and Daly City directions due to an equipment problem on the track between Union City and South Hayward." | `incident_like` | Current delay with a specific cause | Pending your confirmation |
| 17 | `BSA_1762` | Sat 10-17 06:12 – 07:19 | "BART is recovering from an earlier problem. There is a 20-minute delay on the Berryessa line in the Berryessa, Richmond, and Daly City directions due to an earlier equipment problem on the track." | `incident_like` | Recovery wording, delay and cause | Pending your confirmation |
| 18 | `BSA_1838` | Tue 10-20 07:19 – 07:27 | "There is a 10-minute delay on the Berryessa line in the Richmond and Daly City directions due to police activity at Hayward." | `incident_like` | Current delay with a specific cause | Pending your confirmation |
| 19 | `BSA_1839` | Tue 10-20 07:21 – 07:23 | "Trains are not stopping at Hayward Station in the Berryessa direction due to police activity." | `incident_like` (**borderline**) | Current unplanned skipped station with a specific cause. States no delay, so it falls outside the written rule | Pending your confirmation |
| 20 | `BSA_1840` | Tue 10-20 07:26 – 07:44 | "Trains are now making normal stops at Hayward." | leave `unclassified` (**borderline**) | Restoration notice only: reports no current delay, cause or planned work, and lacks the recovery wording | Pending your confirmation |
| 21 | `BSA_1841` | Tue 10-20 07:26 – 07:51 | "BART is recovering from an earlier problem. There is a 10-minute delay on the Berryessa line in the Richmond and Daly City directions due to earlier police activity at Hayward." | `incident_like` | Recovery wording, delay and cause | Pending your confirmation |

Summary of the suggestions: 20 `incident_like` (two borderline), 1 left `unclassified`
(borderline), 0 `planned_notice`.

## Decisions needed

1. **Confirm or change each row.** Only confirmed rows go into
   `config/alert_annotations.csv`, with `reviewed_on` set to the confirmation date.
2. **Service changes without a stated delay.** The written `incident_like` rule mentions
   only delays. Rows 1, 3 and 19 report a stoppage or skipped station instead. Decide
   whether `incident_like` covers unplanned service changes. If it does, reword the rule
   in `service_alerts.md` and the CSV header to match. If not, rows 1 and 19 stay
   `unclassified`.
3. **Restoration notices.** Rows 2 and 20 both announce restored service. Row 2 uses the
   "recovering from an earlier problem" wording, and row 20 does not. Decide whether that
   wording, or the restoration itself, is what counts.

## Which days these touch

- Training days (2026-10-10 to 10-15): rows 1 to 15.
- Validation day 2026-10-17: rows 16 and 17. No new version appeared on 10-16 (the feed
  was empty all day) or on 10-18.
- Sealed test day 2026-10-19: no new version. Only the already-reviewed planned notice
  `BSA_560` was visible.
- Excluded partial day 2026-10-20: rows 18 to 21.

The selected model features do not use alerts
([modeling_plan.md](modeling_plan.md#allowed-features)), so confirming these categories
changes the descriptive alert context, not the preregistered evaluation.

## Fingerprints

Needed for the `alert_fingerprint` column when rows are confirmed:

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
