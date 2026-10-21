# Website architecture (prototype)

**Status:** Milestone 1 (frontend foundation and one prediction), Milestone 2 (ETA
history chart) and the local API integration. By default everything the site displays is
simulated. Started with `VITE_DATA_MODE=http`, it reads the local historical-replay API
(`docs/local_api.md`) instead and labels every value as a historical replay of recorded
BART data. Nothing is live, and the site is not deployed with the API.

The site, **ETA Reliability**, is the public explainer for the ETA-revision project ("How
stable are BART's published arrival estimates?"). Its first slice lets a visitor pick a
station, which way they are going (a boarding group, see below) and a train, and read one
prediction. The page opens briefly: the title, the question, one sentence saying the model
forecasts revisions to BART's published ETA and not physical arrivals, a call to action
and the data disclosure. The tool follows at once, and the full explanation ("The
question") comes after it. The result is built to be read at a glance, for example on a
platform:

1. **Compact identity:** station · destination, then the line (with its route-colour cue),
   platform, boarding group, car count and the "Simulated" tag, all at supporting size.
2. **Likely final published ETA:** the largest element in the example, built for a glance.
   It shows a very large clock time, always to the minute ("6:27 PM"). Underneath is the
   time away rounded to whole minutes ("About 2 min away", or "Less than 1 min away"),
   then the 80% likely range and "Model forecast of BART's last published ETA, not an
   observed arrival."
3. **Summary, directly beneath:** BART's own ETA, the expected adjustment and ETA
   stability, at the glance's precision:

   ```text
   BART said in this snapshot   5:56 PM · about 10 min away
   Expected adjustment          About 2 min 20 sec later
   ETA stability                Likely to hold · 8% chance BART changes this estimate by more than 60 seconds
   ```

   In a historical replay BART's ETA is always in the past tense ("BART said in this
   snapshot"); simulated data, which stands in for a live feed, says "BART currently says".
4. **How the forecast is calculated** (expandable, closed by default): the exact
   arithmetic, current published ETA + predicted revision = likely final published ETA,
   with seconds whenever the minute alone would hide the adjustment. The `+` and `=` are
   visual only; screen readers hear the labels. Then the adjustment range, the stability
   cutoffs and scale, and the full caveat.
5. **Service alerts** stay visible, because they can matter to a rider.
6. **Data and model details** (expandable): where the data came from (the full replay
   provenance, or "Simulated"), the feed snapshot and its freshness ("Fresh at replay
   time" in a replay), "Forecast generated", the model version and the date its training
   data runs to, and the trip number.

For a train without a model forecast, the result shows BART's published ETA, why there is
no forecast, and BART's exact ETA. If another train on the board has a forecast, a small
"View the next model forecast" button (or "View an earlier model forecast" when only
earlier trains have one) names that train and selects it on request. Focus then moves to
the result's heading. The earliest train is always the default; a later train is never
selected for the visitor.

The likely final published ETA is a forecast of BART's last published estimate before the
train reaches the stop. It is never an observed arrival (see `PROJECT_SPEC.md`, "Why not
arrival accuracy").

> `PROJECT_SPEC.md` describes the presentation layer as a custom React and TypeScript
> frontend, deployed as a static site separately from a future Python prediction API.

## Stack

| Choice | Why |
|---|---|
| React 19 + TypeScript (strict, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`) | Typed data contracts shared by the mock and future API clients |
| Vite 8 | Standard dev server and static build that fits GitHub Pages |
| Custom CSS with a token layer (`src/styles/tokens.css`) | Small, explicit design system; no Tailwind or component library |
| `@fontsource-variable/*` fonts | Self-hosted in the bundle; no third-party font requests |
| Vitest + React Testing Library + jsdom | Behaviour tests that query the page the way users and assistive tech do |
| ESLint (typescript-eslint strict, react-hooks, jsx-a11y strict) | Catches hook mistakes and static accessibility errors |

TypeScript is pinned to 6.0.x because `typescript-eslint` 8 does not support TypeScript 7
yet. ESLint is pinned to 9 because `eslint-plugin-jsx-a11y` does not declare ESLint 10
support.

## Directory structure

```text
web/
├── index.html                 page shell, metadata, inline favicon
├── vite.config.ts             base path, data-mode description, Vitest config
├── eslint.config.js
├── .env.example               documented VITE_* variables (no secrets)
└── src/
    ├── main.tsx               fonts, global CSS, React root
    ├── App.tsx                chooses the PredictionClient, composes the page
    ├── components/            SiteHeader, Opening, ExampleLink, PredictionExample,
    │                          StationPicker, TrainTimetable, PredictionReadout, StabilityMark,
    │                          EtaHistory, HistoryChart, ObservationTable, ProjectQuestion (+ tests)
    ├── data/
    │   ├── PredictionClient.ts        interface + PredictionClientError
    │   ├── MockPredictionClient.ts    deterministic simulated client (+ tests)
    │   ├── HttpPredictionClient.ts    client for the local API (+ tests)
    │   ├── apiDecode.ts               runtime validation of the API's JSON
    │   ├── createPredictionClient.ts  VITE_DATA_MODE → client
    │   ├── PredictionClientContext.tsx  provider + hook (client and clock)
    │   ├── clientKey.ts               per-client request keys
    │   └── fixtures/
    │       ├── simulated.ts           the three-station demo set and its scripted values
    │       ├── network.ts             all 50 stations and their boarding groups, from BART static GTFS (mock only)
    │       ├── networkTrains.ts       simulated trains (20 per boarding group) for network.ts
    │       └── apiReplay.json         recorded local-API responses, for tests only
    ├── domain/
    │   ├── types.ts           data contracts
    │   ├── eta.ts             ETA arithmetic, stability classes, freshness, formatting (+ tests)
    │   ├── history.ts         history analysis, gaps, revision count, summary wording (+ tests)
    │   ├── boardingSelection.ts  boarding group from a link, old ?direction= links, correction notes
    │   └── stationSearch.ts   station search, aliases, alphabetical browse (+ tests)
    ├── hooks/                 useRequest (abortable, keyed loading), useNow (clock tick),
    │                          useFreshness, useDataSource (provenance for the opening),
    │                          useElementWidth and useRootFontScale (chart sizing),
    │                          useRecentStations, useUrlSelection (URL, back and forward)
    ├── dev/                   development-only state selector (excluded from builds)
    ├── styles/                tokens.css, base.css, app.css
    ├── clientContract.test.tsx  the page's states with both clients
    ├── metadata.test.ts       index.html description, Open Graph and Twitter tags
    └── test/                  setup.ts, fakeApi.ts (fetch over the recorded responses)
```

## Data contracts

Defined in `web/src/domain/types.ts`. Timestamps are ISO 8601 strings with an explicit
time zone (UTC in practice). Durations are whole seconds.

| Type | Purpose |
|---|---|
| `Station` | `id` (GTFS parent stop id), `name`, `boardingGroups`, `endOfLine` (every train there starts or ends its trip there) |
| `BoardingGroup` | One way a train can leave the station (`docs/boarding_groups.md`): stable `id` such as `to-SHAY`, rider-facing `label`, `destinations`, `platform` (the one platform every train in the group uses that day, or `null`), `gtfsDirectionIds` (read only to translate old links) |
| `TrainPrediction` | One trip-stop, either a `ForecastTrain` or an `EtaOnlyTrain`, told apart by `predictionStatus`. Both carry BART's published ETA (`currentEtaSeconds` / `currentEtaAt`) and the scheduled `platform` (`null` when not certain). Only `predictionStatus: "ok"` adds model numbers: `predictedRevisionSeconds` (positive = later), `revisionProbability` (P(revision of more than the threshold, either way)), `stability`, and an 80% `revisionInterval` that is `null` when no range is supported. Every other status (`outside_model_horizon`, `outside_model_population`, `fallback_required`, `features_unavailable`) has all four set to `null` |
| `PredictionHistoryPoint` | One published ETA at one feed snapshot (for the later history chart) |
| `AlertContext` | An alert *visible in the feed* at prediction time: scope, category, header, `visibleSince`. Visibility is not evidence of a disruption (see `docs/service_alerts.md`) |
| `ModelMetadata` | `modelVersion`, `trainedThrough`, `revisionThresholdSeconds`, `simulated` |
| `PredictionResponse` | `dataProvenance` (`simulated` or `historical_replay`), `replay` (`{asOf}` exactly when replayed), `boardingGroupId`, `feedTimestamp`, `generatedAt` (when the forecast was generated; the replay time in a replay), `trains`, `unplacedTrainCount` (trains listed at the station that match no scheduled trip, so which way they leave is unknown), `terminatingTrainCount` (trains listed there whose trips end there; neither can be boarded or shown, both 0 when simulated), `alerts`, `model` |
| `HealthStatus` | API status, latest feed snapshot, and the same provenance fields |

Derived values are computed in exactly one place, `domain/eta.ts`:

- `likelyFinalEtaSeconds(current, revision) = current + revision`. The contract does not
  carry a separate "final" field, so the two can never disagree.
- `classifyStability(p)`: below 0.25 → *Likely to hold*; 0.25 up to 0.5 → *May be revised*;
  0.5 or higher → *Likely to be revised*. The API is expected to return the same class; the mock
  computes it with this function.
- `assessFreshness(feedTimestamp, now)`: a snapshot more than 120 s old (two collector
  polls) is stale. 120 s matches the alert-snapshot staleness limit
  (`ALERT_SNAPSHOT_MAX_AGE_S` in `src/bart_reliability/warehouse/alerts.py`).

- Display wording also lives there: `describeRevision` ("about 12 seconds later"),
  `describeRevisionRange` ("10 seconds earlier to 35 seconds later"), `describeTimeAway`,
  `formatClock` and `formatClockMinute` (seconds dropped, not rounded).
- **Glance versus exact.** The large forecast is always minute precision, and its time away
  is rounded to whole minutes by `describeAwayGlance`; the summary beneath it uses the same
  precision. The exact values sit in "How the forecast is calculated". There,
  `needsSeconds(current, final)` is true when the
  two times differ but read the same to the minute, and then both calculation clocks show
  seconds ("6:27:06 PM" and "6:27:18 PM"). A sub-minute adjustment is therefore never
  hidden. The time-away values in the calculation are always exact ("2 min 22 sec").
- The screen-reader summary gives the glance first, then the exact calculation, labelled as
  such: "Likely final published ETA: 6:27 PM, about 2 min away. Exact calculation: BART
  said in this snapshot 6:27:06 PM, 2 min 10 sec away; expected adjustment about 12 seconds
  later; likely final published ETA 6:27:18 PM, about 2 min 22 sec away." (Simulated data
  says "BART currently says".)
- **Time remaining is counted from the feed snapshot**, not from the visitor's clock. It
  matches what BART published and does not count down while the page is open. The readout
  says so next to the snapshot time, and a stale snapshot gets a warning. Switching to the
  visitor's clock later means changing only the readout's "away" values.

These cutoffs and the time reference are provisional product choices for the prototype, not
model results.

## Mock client design

Components never import fixtures. They call the `PredictionClient` from context
(`usePredictionEnvironment()`), and `App` decides which implementation to provide.

`MockPredictionClient` (in `data/MockPredictionClient.ts`):

- reads fixtures from `data/fixtures/simulated.ts`. Real station names, lines and
  destinations are used; every number is invented;
- stores times as **offsets** (ETA seconds, feed age, alert age) and turns them into
  timestamps using an injected clock. With the same scenario and clock, the response is
  identical, which keeps the tests deterministic, and the dev page still looks current;
- takes a `scenario` (`live`, `loading`, `error`, `stale`, `empty`, `no-interval`,
  `eta-only`, `model-horizon`) so every interface state can be reproduced. `loading` never
  resolves until aborted; `no-interval` drops every range and `eta-only` marks every train
  `outside_model_horizon`, the two shapes the API returns for trains without full support.
  `model-horizon` applies the real models' domain, forecasting only trains within 60 s of
  5, 10 or 15 minutes away, so a board mixes forecasts and BART-only trains;
- takes a separate `historyScenario` (`normal`, `loading`, `error`, `single`, `none`,
  `gaps`) for the history states (see "ETA history" below);
- honours `AbortSignal`. `useRequest` aborts the previous request whenever the selection
  changes, so a slow response cannot overwrite a newer one;
- simulates latency (350 ms in the app, 0 in tests).

In development only, a dashed strip after the page content ("Dev · preview state")
switches the scenario ("Mock response") and the history scenario ("History response"). It sits in normal document flow, so it never covers content. It is loaded with a dynamic import that is guarded by
`import.meta.env.DEV`, so it does not appear in production builds (verified by searching
`dist/`).

## Station and train selection

Station is the primary choice, because predictions belong to the boarding station. The
controls narrow step by step, so the page never shows every station and every train at
once:

1. **Where are you boarding?** When closed, a compact row shows the chosen station and a
   **Change** button. Opening it turns the row into a searchable combobox
   (`StationPicker.tsx`) with a panel anchored under the field:
   - With no query, the panel shows **Recent** (up to three) or, before any choice,
     **Suggested**: the current or default station. No location is guessed.
   - Typing filters immediately, case-insensitively and ignoring accents
     (`domain/stationSearch.ts`). Matches rank as: exact alias, name prefix, word prefix
     ("oakland" finds "12th Street / Oakland City Center"), alias prefix, substring.
     Results are limited to eight, with "Showing 8 of N" when there are more.
   - Aliases are each station's BART ID (`EMBR`) plus a deliberately tiny list: `SFO` and
     `OAK`. There is no speculative alias database.
   - **Browse all N stations** lists every station alphabetically inside the scrolling
     panel. The page height is unchanged; the panel is absolutely positioned.
   - Choosing a station closes the panel and returns focus to **Change**.
2. **Which way are you going?** One radio choice per boarding group: the label ("Toward
   Daly City and Richmond") and, when every train in the group leaves from one platform,
   a platform tag ("Platform 2"). Groups come from the schedule's platforms and
   neighbouring stations, never from GTFS `direction_id` (`docs/boarding_groups.md`); at
   Hayward this is what keeps Berryessa trains apart from Daly City and Richmond trains. A
   terminal has one choice and says so: "Antioch is the end of the line. Trains arriving
   here end their trips, so only trains leaving are listed."
3. **Upcoming trains:** the next four, in time order, then "Show N more trains" or "Show
   fewer trains" (`TrainTimetable.tsx`, `INITIAL_TRAIN_LIMIT`). Each row leads with BART's
   ETA as a clock time ("10:05 AM"), the time away beneath it ("5 min 42 s"). A train with
   a forecast adds its likely final published ETA and stability ("Likely final 10:05 AM ·
   Likely to hold"); one without says "BART ETA only". When the group has no single
   platform, each row names its train's platform. Collapsing never hides the selected
   train: a later selection stays listed after the first four, under "Later train you
   selected". No train is filtered out. An empty board shows only "None listed": the
   result beside it gives the one detailed explanation.

**Keyboard and screen readers** follow the ARIA 1.2 combobox pattern:
- Focus stays in the input. The input has `role="combobox"` and `aria-expanded`;
  `aria-controls` points to the listbox, and `aria-activedescendant` to the active option.
- Arrow Up and Arrow Down move through the options, Enter selects, and Escape closes with
  focus returned to Change. Tab moves to "Browse all" and then out, closing the panel.
- A polite live region announces the result count ("8 of 12 stations match 'st'.",
  "No stations match …", "All 50 stations, alphabetical.") and the selection
  ("MacArthur selected as your boarding station.").
- The Change button's accessible name includes the current station.
- The active option is outlined as well as tinted, so it never depends on colour alone.
  Options and controls are at least 44 px tall.

**Mobile:** at 320 and 390 px the panel spans the controls column under the always-visible
search field. It is at most 60% of the viewport tall and scrolls internally. There is no
horizontal overflow, nothing moves the page, and the panel scrolls without dragging the
page behind it.

**URL and recent stations** (`hooks/useUrlSelection.ts`, `domain/boardingSelection.ts`,
`hooks/useRecentStations.ts`):
- The station and boarding group are kept in the query string, e.g.
  `?station=HAYW&boarding=to-BAYF`, so a selection can be bookmarked or shared. There is no
  routing library. The page reads the values on load and keeps them current with
  `history.replaceState`, which doesn't add a history entry for every choice. Other query
  parameters and the hash are preserved.
- **Back and forward.** A `popstate` listener reads the address again whenever the
  browser moves through history (for example back across an in-page `#question` link), so
  the page always shows what the URL says. An address that matches what is shown changes
  nothing, so the chosen train is kept.
- IDs are matched case-insensitively (`boarding=TO-bayf` works) and written back
  canonically. An unknown station falls back to the first station the active client lists
  (Embarcadero in the demo set; the API's first station in HTTP mode) with a visible note.
  An unknown boarding group falls back to the station's first group, with a note naming
  what is shown instead. A boarding group given for an unknown station is not applied to
  its stand-in.
- **Old links** carry `?direction=0|1`. One is translated only when exactly one group at
  the station carries that GTFS direction (`direction=0` at Embarcadero becomes `to-WOAK`,
  silently). Otherwise the first group is shown with a note: at Hayward, for example,
  "This link's direction "1" is from an older version of the page and could mean either
  side of Hayward…". `direction` is removed from the URL once it has been read, and
  `boarding` wins when a link has both.
- Notes are status messages (`role="status"`) shown next to the control they concern, and
  they go once the visitor makes a choice.
- Up to three recent station IDs are stored in `localStorage` under
  `eta-reliability.recent-stations`. Only IDs are kept; no predictions or trips. They
  are never sent anywhere, and the page works when storage is blocked.

**Station sets:** `MockPredictionClient({ network })` serves either the three-station demo
(`'demo'`, the default) or the full network (`'full'`). The full network has all 50
stations from BART's static GTFS (feed of 2026-10-08): real names, IDs, boarding groups
(made by the API's own rule in `src/bart_reliability/api/boarding.py`), and the terminals,
lines and platforms of weekday trains leaving each way. Each group has 20 simulated,
deterministic trains. The dev panel's "Station set" group switches between them. The
fixture was generated once by a script outside the repository; regenerate it if the static
feed changes. The demo set's groups, platforms and group order are real too; its trains are invented.
Both sets list each station's groups in the API's order (platform order, then group ID), so
simulated development opens on the same group as HTTP mode; tests compare the order with the
recorded API wherever the stations overlap.

The full network is mock and test data only. The mock loads it with a dynamic import, so
every production build, including an HTTP-mode build, emits it as a separate chunk
(`fullNetwork-*.js`, about 29 KB) that is never fetched. In HTTP mode the picker searches
only the stations returned by `/api/v1/stations`, in the API's order. The small demo
fixture (`simulated.ts`) is still part of the main bundle, as it was before the picker.

While stations are still loading, a station in the URL is left as it is: the page doesn't
judge it, rewrite it or request a default board. Only once the list has arrived and the ID
has been checked does an unknown station produce the warning and a corrected URL.

**Deferred:** "Use my location" (geolocation) is not implemented, and the site never
requests location permission.

## ETA history (Milestone 2)

The section "How this ETA has changed" sits beneath the selection and prediction readout
and answers: *how has BART changed this train's published ETA as it approached the
station?*

### Data flow

```text
selected train (PredictionExample)
  → EtaHistory: PredictionClient.getPredictionHistory(train.predictionId)
      keyed by client + prediction id + the prediction's feed snapshot; aborted on change
  → domain/history.ts analyzeHistory(points, response.feedTimestamp)
      sorts, drops anything newer than the prediction's snapshot, marks gaps,
      computes each change, the net change and the revision count
  → summary sentence, HistoryChart (SVG), ObservationTable
```

The history uses the existing `PredictionHistoryPoint` contract: snapshot time, BART's
published arrival time, and seconds from snapshot to that time. Components never import
fixtures. The scripted histories live in `SIMULATED_HISTORY` in
`web/src/data/fixtures/simulated.ts`. There is one entry per selectable train, written as
one-minute snapshots counted back from the latest, the moments BART moved the ETA, and any
missing snapshots. `MockPredictionClient.getPredictionHistory` turns each script into
points that:

- end exactly at the snapshot and current published ETA of the matching predictions
  response (the mock remembers that snapshot per station and boarding group);
- never include a later snapshot (the UI also clips to the prediction's snapshot);
- keep `publishedEtaSeconds = publishedEtaAt − feedTimestamp`;
- are identical across reloads for the same scenario and clock.

Both thresholds are **provisional prototype assumptions**, defined once as named constants
in `web/src/domain/history.ts` and used everywhere from there. Neither has been checked
against real BART history yet.

- **Gap (`HISTORY_GAP_SECONDS = 90`):** consecutive snapshots more than 90 s apart. 90 s
  is continuous; 91 s is a gap. It matches `max_collection_gap_s` in
  `config/eta_revision.toml`.
- **Counted change (`REVISION_THRESHOLD_SECONDS = 30`):** a change of at least 30 s between
  consecutive snapshots. 29 s is drift; 30 s counts. It matches `tier_a_spread_s`. The
  summary names the threshold ("across three changes of 30 seconds or more"). Smaller
  changes are described as drift. The threshold only affects that count: the chart shows
  every change, and the net change is exact.
- **Across a gap, nothing is observed.** Only the snapshots either side of the gap are
  known, not how many times BART changed the ETA in between. A difference across a gap is
  never counted as a change or as drift.
  - With gaps, the summary separates endpoint movement from observed changes, e.g. "From
    the first to the latest available snapshot, the ETA ended 2 min 45 sec later. Two
    observed changes of 30 seconds or more occurred outside one gap; additional changes
    during the gap are unknown."
  - For the point after a gap, the inspection line, its accessible name and the table give
    the difference from the previous *available* snapshot and the gap's length, and say
    that changes during the gap are unknown.
  - Histories without gaps keep the single-sentence summary.

### Chart semantics

- A step chart, because BART's ETA holds until it is revised. The horizontal axis is
  snapshot time, from the earliest observation to the latest snapshot. The vertical axis is
  the published arrival clock time, so **up means BART moved the ETA later, down means
  earlier, and a flat line means it held.**
- A gap breaks the line and shades the missing span ("no data"). The line never
  connects across a gap.
- Marks appear only where something happened: a small dot at each observed revision, a
  hollow dot either side of a gap, and a larger dot at the latest observation, labelled
  "Latest" in the right gutter. Unchanged minutes get no mark, and the snapshot being
  inspected gets a ring.
- **A completely flat history** (no change and no gap) is shown calmly instead: one line,
  "Held at 10:05:02 AM in all 83 snapshots, from 8:37:23 AM to 9:59:23 AM.", over a
  quiet rule. "Show the full chart" (a button with `aria-expanded`) opens the same chart,
  and the observation table stays available.
- The model's likely final published ETA is a dashed blue reference line, labelled
  "Likely final". Its 80% range is a bracket in the right gutter, outside the time axis,
  because it is a forecast, not an observation. The legend says so.
- The y axis always spans at least 3 minutes, so a few seconds of drift don't look like a
  large move.
- Historical estimates are never called errors, and nothing on the chart is a physical
  arrival time.
- The summary above the chart covers later, earlier, no net change after
  counted changes, held steady, drift, one observation, no history, gaps, and stale data, where
  the window is anchored to the snapshot time.

### Accessibility

- The figure's accessible name comes from `describeChart` and states the data, for example
  "Chart of BART's published ETA for Embarcadero · Richmond train: 15 snapshots from
  9:45:26 AM to 9:59:26 AM". The marks are explained in a separate list labelled "Chart
  key", not in a `<figcaption>`, so a key entry such as "Shaded band: a span with no
  snapshots in the feed" can't be read as a statement about the current train. With no
  history at all, there is no figure; the summary says so.
- No point is exposed separately: a screen reader's virtual cursor finds no image per
  snapshot. The SVG is one `role="slider"` over the snapshots, named "Snapshots of
  {station} · {train}" and described by the figure's description. Its `aria-valuetext` is
  the inspected snapshot in words (snapshot time, BART's published arrival time, time away
  and the change from the previous snapshot), so the one changing value is announced as
  it moves.
- The chart is one stop in the Tab order. Left/Down and Right/Up move one snapshot,
  Page Down and Page Up ten, and Home and End jump to the first and last. Every snapshot
  is reachable, marked or not. Focus draws the signal-blue ring around the plot and a
  heavier ring on the inspected snapshot.
- Hovering or tapping the plot updates the same value and a visible inspection line
  beneath the chart, so nothing depends on hover.
- "Show all N observations" opens a full data table with the same values, including gap
  rows. On narrow screens each row stacks into a labelled block, and explicit table roles
  keep the semantics when the display changes.
- The summary comes before the chart. Chart text stays at the 13 px label size, because the
  SVG is laid out from the measured container width, not scaled through a `viewBox`, and
  its label margins grow with the visitor's text size (`useRootFontScale`). The chart has
  no animation.

### States

History loading, history failure (with retry), one observation, no history, gaps, and
stale data are all reproducible from the dev panel's "History response" and "Mock
response" groups. If the prediction itself fails or no trains are listed, the section
explains that there is no history to show.

### Real history

In HTTP mode the chart draws the API's history for the selected train: BART's published
ETAs from recorded snapshots up to the replay time (`docs/local_api.md`). The dashed
reference and its range appear only for a train with a forecast, and the range only when
the forecast has one; the key says so otherwise. Pagination and server-side gap detection
are not implemented.

## HTTP client (local API)

`HttpPredictionClient` implements the same `PredictionClient` interface over the local
historical-replay API (`docs/local_api.md`), one endpoint per method:

| Method | Endpoint |
|---|---|
| `listStations()` | `GET /api/v1/stations` |
| `getPredictions(stationId, boardingGroupId)` | `GET /api/v1/stations/{station_id}/predictions?boarding_group=...` |
| `getPredictionHistory(predictionId)` | `GET /api/v1/predictions/{prediction_id}/history` |
| `getModelMetadata()` | `GET /api/v1/model/metadata` |
| `getHealth()` | `GET /api/v1/health` |

- **Requests.** Path identifiers are URL-encoded, requests ask for JSON and never send
  cookies (`credentials: "omit"`), and the page's `AbortSignal` is passed through, so a
  superseded request is cancelled rather than overwriting a newer one.
- **Validation.** `apiDecode.ts` checks every field the page uses before the page sees it,
  and rejects the whole response if any check fails, so nothing partial or misleading is
  shown:
  - a `dataMode` other than `historical_replay`, so unlabelled data cannot be shown;
  - a forecast probability outside 0 to 1, a range with lower above upper, or a range
    `level` that is not above 0 and at most 1;
  - a negative `currentEtaSeconds` (the board lists upcoming trains only);
  - a `carCount` that is not `null` or a whole number of at least 0;
  - a timestamp without an explicit time zone ("2026-10-15T17:05:04" is refused; it would
    be read in the visitor's own time zone);
  - duplicate station IDs, duplicate boarding-group IDs within a station, duplicate
    prediction IDs on a board, and a repeated snapshot in a history;
  - model numbers on a train without a forecast;
  - a board for a different station or boarding group than requested.

  Extra API fields are ignored.
- **Errors.** Failures become `PredictionClientError`, so the page shows the same error
  states as with the mock. The API's own `error.clientCode` and message are used when
  present (404 → `not_found`, 503 → `unavailable`); otherwise 404 → `not_found` and anything
  else, an unreachable API or an invalid body → `unavailable`. With no address configured,
  every call fails with `unavailable` before any request is made.
- **Provenance.** Each response says where its data came from, and a replay is explained in
  exactly three places, not repeated elsewhere:
  - one banner, the opening's disclosure: "Historical replay of recorded BART data", with
    its as-of time, once `/health` confirms the replay mode ("Connecting to the prediction
    API" until then, "Prediction API unavailable" if it does not answer);
  - one concise reminder beside the result: "Historical replay—not live. BART data as of
    Thu, Oct 15, 2026, 10:00 AM Pacific.";
  - the full provenance under "Data and model details".

  The words "simulated" and "live" are never used for replayed data, except to say it is
  not live, and replayed values are never in the present tense ("BART said in this
  snapshot", never "currently says" or "right now").
- **Freshness in a replay** is judged at the replay's as-of time, not against the
  visitor's clock, and it does not tick. A snapshot 37 s before the as-of time reads
  "Fresh at replay time · 37 s old at the replay time"; one older than 120 s gets the
  stale warning, worded "before the replay time", which stays visible beside the result.
- **Trains without full support.** A train with `predictionStatus` other than `ok` shows
  BART's published ETA only, as published, with one sentence saying why (for
  `outside_model_horizon`: "The model only forecasts trains BART shows about 5, 10 or 15
  minutes away."). The timetable marks it "BART ETA only". A forecast whose range is not
  supported shows the forecast and says "No likely range is shown". No value is ever
  simulated or invented in place of a missing one.
- **Empty boards** say why when the response shows it:
  - the feed lists trains at the station whose trips end there, so they can't be boarded
    (`terminatingTrainCount`);
  - the feed lists trains there that match no scheduled trip, so which way they're going
    isn't known (`unplacedTrainCount`; Antioch's extension trains). No direction is
    invented for them.

  Otherwise the page gives the general reasons: service may have ended, trains may not be
  running this way right now, or the feed may not include them. A terminal also says it is
  the end of the line, next to its one boarding choice.

`web/src/clientContract.test.tsx` renders the whole page with the mock client and with the
HTTP client over a fake `fetch` serving recorded API responses
(`data/fixtures/apiReplay.json`, recorded at as-of 2026-10-15T17:00:00Z with model
`0.1.0+8d942e17429c`, and kept as a fixed contract recording). The same checks
cover a forecast with and without a range, a train with no forecast, loading, no trains, a
stale snapshot, a failed request and its retry, missing history and a failed history request.
They also check that changing the station, boarding group and train requests the matching
data, that the forecast and the history always describe the same train, and that Hayward's
two groups never mix Berryessa trains with Daly City or Richmond trains.

### Selecting the client

```bash
VITE_DATA_MODE=mock   # default; simulated fixtures (the dev server and every test)
VITE_DATA_MODE=http   # the local API at VITE_API_BASE_URL
VITE_API_BASE_URL=http://127.0.0.1:8000   # in web/.env.local (ignored by git)
```

The dev server stays on simulated data unless `VITE_DATA_MODE=http` is given for that run,
so design work and the dev panel are unaffected by `.env.local`. Tests pin
`VITE_DATA_MODE=mock` in `vite.config.ts` and inject any HTTP client they need, so they
never depend on a developer's local settings or a running API. The API address is read
only in HTTP mode, so a simulated build does not contain it. `VITE_*` values are compiled
into the public bundle, so they must never hold secrets, and no server or production
address is committed.

## Local development

```bash
cd web
npm install
npm run dev      # prints http://localhost:5173/ (simulated data)
npm run test     # Vitest, once
npm run lint     # ESLint + tsc -b
npm run build    # type-check + production build into web/dist/
npm run preview  # serve the production build
```

To run the site against the local historical-replay API, start two processes from the
repository root, each in its own terminal:

```bash
.venv/bin/bart-serve-local                     # API on http://127.0.0.1:8000
cd web && VITE_DATA_MODE=http npm run dev       # site on http://localhost:5173/
```

The API answers as of its default replay time, 2026-10-20T17:00:00Z (10:00 AM Pacific),
with model `0.2.0+886fcd260732` (see `docs/local_api.md`). The page shows that time in
its replay banner. The GitHub Pages build is the simulated one and never calls this API.

## GitHub Pages base path

`vite.config.ts` serves from `/` in development. A production build defaults to
`/bart-reliability/`, the GitHub Pages project-site path. To change it, set
`VITE_BASE_PATH` (for example `VITE_BASE_PATH=/ npm run build` for a root or custom
domain). Components do not hard-code paths: in-page links are fragments, fonts and CSS go
through Vite's asset pipeline, and any future static asset should use
`import.meta.env.BASE_URL`.

`.github/workflows/deploy-pages.yml` publishes the simulated build (`VITE_DATA_MODE=mock`,
`VITE_BASE_PATH=/bart-reliability/`) to <https://millerroberts180.github.io/bart-reliability/>
on every push to `main`, or when run by hand. The API is not deployed.

## Page metadata

`web/index.html` describes the historical-replay site: "A historical replay of recorded
BART data, with a model of how BART revises a train's published arrival estimate before it
arrives. Not live, and not a prediction of physical arrival." The same title and
description are given as Open Graph (`og:type`, `og:site_name`, `og:title`,
`og:description`) and Twitter (`twitter:card` "summary", `twitter:title`,
`twitter:description`) tags. A simulated build shows no BART data, so `vite.config.ts`
swaps all three descriptions for a simulated-data one in mock mode; the HTTP build keeps
the replay text. `metadata.test.ts` checks the tags.

The deployed build is the simulated one, so it carries the simulated description. Not done
yet for the deployed site:
- add `<link rel="canonical">` and `og:url` with its address;
- design a social image and add `og:image`, `og:image:alt`, `twitter:image` and
  `twitter:card` "summary_large_image".

## Design principles

These were chosen after studying one public editorial data story (for principles, not
appearance) and reconciling the result with this project's accuracy and accessibility
requirements.

1. **Lead with the answer.** The likely final published ETA comes first and is the largest
   value in the section: up to 92 px, against 17 px for the station heading and 15 px for
   the summary rows. Its clock is always minute precision and is sized to the card
   (`cqi`), so the full time and AM/PM always fit on one line, down to 320 px. "About …
   away" sits directly under it, then the summary, then detail that steps down in size and
   contrast, with the arithmetic and technical details one press away. A clock time and its
   AM/PM never wrap apart.
2. **Disclose before claiming.** "Prototype using simulated data" (or, with the local
   API, "Historical replay of recorded BART data" and its as-of time) sits beside the
   title, above the fold on desktop and mobile. It comes before any number is shown.
3. **Three typographic voices, each with one job.** Schibsted Grotesk for headings and
   controls, Source Serif 4 for prose, and JetBrains Mono for measurements, timestamps and
   labels. Mono is never decoration.
4. **Color only carries meaning.** A warm off-white ground, blue-tinted charcoal ink and a
   single signal blue for interaction and focus. Three muted state colors mark stability and
   freshness, and each is always paired with a text label and a distinct shape (a flat,
   one-step or two-step ETA trace). Every text pairing is at least 5.0:1.
5. **Route colour as a cue, never as meaning.** The line's colour comes from BART's static
   GTFS `route_color`, looked up from the line name in `domain/routeColors.ts`, so the
   contracts are unchanged. It appears as a 6 px rail on the card's left edge, beside the
   identity, forecast and calculation, and as a small swatch next to the line name. Both
   are cased in ink, so even pale Yellow stays visible (casing 15:1 on the card). The line
   name is always text, and the colour never signals forecast quality or stability.
6. **Rules, not cards.** Sections are separated by thin rules. The only framed surfaces are
   the disclosure and the readout. There are no shadows, gradients or nested containers.
7. **Show uncertainty as a range.** Each revision comes with its probability and an 80%
   range, and the copy says BART may revise the estimate. The interface never presents a
   single "true" time. When no range is supported, the page says so in words rather than
   drawing a substitute.
8. **Stable layout across states.** Loading, failure, stale and empty states keep the
   readout's position and minimum height. Motion is limited to state feedback (hover, the
   probability fill) and is disabled under `prefers-reduced-motion`.

## Backlog: deferred features

Recorded during the correction pass and deliberately not implemented:

1. **Aggregate reliability explorer** by station, line, hour and published-time horizon.
2. **"What actually happened?"**: an optional reveal of how BART's ETA ended, for a replayed
   train, shown only on request and never mixed into the forecast.
3. **Replay-time scrubber**, to choose the moment the replay answers as of.
4. **Curated example links**, for instance a revised train, a held train and an empty board.
5. **Alert visibility overlay** on the history chart.
6. **Favourite and nearest stations.** Nearest would need geolocation, which is never
   requested today.

## Deferred to later milestones

- System findings, the exploration dashboard and filters
- Methodology section and a fuller footer. The current footer holds only the
  independence notice: "Independent project using BART open data. Not affiliated with or
  endorsed by BART."
- A live (not replayed) API, and hosting the API anywhere but the developer's machine
- Dark color scheme
- "Use my location" in the station picker (no geolocation is requested today)

## Known limitations

- In the default mode all values are simulated. Line and destination pairings follow
  BART's public network but are not checked against a specific timetable.
- With the local API, most trains show BART's ETA only: the model serves only published-time
  horizons of 5, 10 and 15 minutes (±60 s), so at a given moment only a few trains per
  board have a forecast (for example 1 of 3 at Castro Valley toward Daly City at the
  tested replay time). 5 of 95 boards are empty at the tested replay time, for the
  reasons in `docs/local_api.md` ("Empty boards").
- Platform numbers come from the schedule. A platform change on the day is not detected,
  except that a train listed at a platform its schedule does not use there shows no
  platform number.
- Stability cutoffs (0.25 / 0.5) and the 120 s freshness limit are provisional.
- Freshness is re-evaluated every 15 s; the countdown does not tick every second.
- Clock times are formatted in Pacific time regardless of the viewer's time zone.
- The history scripts are hand-written. Real BART histories will have more jitter, longer
  feeds and irregular gaps, and the 30 s revision threshold and 90 s gap rule have not been
  checked against them yet.
- Chart tick labels omit AM/PM to save space; full times appear in the inspection line and
  the table.
- The result describes changes to BART's published estimate only. It makes no claims about
  skipped or changed stops, missed connections or cancellations. A visible service alert is
  shown as context, never as a predicted change to the train.
