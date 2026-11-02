# Website architecture

**Status:** the curated historical showcase ([showcase_replay.md](showcase_replay.md)): three
views over one fixed replay moment, 2026-10-19 at 8:10 AM PDT. The site is a presentation layer
for the Python, SQL and modeling work: a static Vite and React build on GitHub Pages, with no
public API, server or database. It has three data modes, and nothing in any of them is live:
- **`static`:** the public build. It reads the curated replay in `web/public/replay/` and the
  showcase files in `web/public/showcase/`, both published with the site.
- **`http`:** for development. It reads the local historical-replay API
  ([local_api.md](local_api.md)). It has no showcase files, so Highlights and the Network map
  say they need the published build.
- **`mock`:** the default for the dev server and most tests. Everything it displays is
  simulated, and it has no showcase files either.

Each build bundles only its own mode's client and data (`build-tests/`).

## Three views

| View | Address | What it is for |
|---|---|---|
| Highlights (default) | `?view=highlights` | What the project is, three figures, and "Largest ETA changes in this replay" by horizon (`&horizon=300\|600\|900`) |
| Network map | `?view=map` | An original SVG schematic coloured by ETA revision (`&mode=forecast\|published`, `&station=<id>`) |
| Train explorer | `?view=explorer` | Station, direction and train (`&station=…&boarding=…&train=…`), the forecast and the ETA history |

**Navigation.**
- **No routing library.** The query string is the state (`web/src/hooks/useView.ts`).
- **History.** Moving to another view pushes a history entry, so back and forward work. A
  view's own choices (horizon, map mode, selection, train) update the address with
  `replaceState`, so they are shareable without filling the history.
- **Links.** Every link is a real `href` (`ViewLink`): it works in a new tab, and a plain
  click navigates in place.
- **Focus.** After a change of view, focus moves to the view's heading and the document
  title names the view.
- **Header.** The header shows the three views and "Source on GitHub" at every width. On
  phones the views take a row of their own, with no menu icon.

**On every view.** A strip under the header says "Fixed historical replay", the moment,
"Not live", and "The model predicts revisions to BART’s published ETA, not physical arrival
times."

### Three ETAs

The site keeps three values apart, and its words follow them:
- **BART published ETA:** what BART said at the snapshot.
- **Model-adjusted ETA:** BART's ETA plus the model's predicted revision.
- **BART later published (final published ETA):** retrospective, labelled so wherever it
  appears.

It never describes any of them as an arrival, and a revision is "ETA moved later" or "ETA
moved earlier", never anything about the train itself.

### Highlights

- **First screen:** the title, the question ("How might BART revise a published ETA as a
  train approaches?"), and one sentence on what the model does and does not predict. The
  replay moment follows, then three figures on a rule (supported forecasts, stations
  represented, model version) and the curation disclosure.
- **Largest ETA changes:** a horizon control (5, 10 or 15 minutes, `aria-pressed`) shows at
  most five trains for that horizon, from `largest-changes.json`.
  - Each entry reads "BART said → Model expected → BART later published", with the
    predicted and realized change.
  - It then says whether the direction matched and how far the model-adjusted ETA was from
    what BART later published.
  - Each entry links to that train in the explorer.
- **Not on this page:** general test metrics, which do not describe this snapshot.

### Network map

- **The drawing:** an original octilinear schematic from `network-map.json`, built in
  Python from the GTFS station order on a grid ([showcase_replay.md](showcase_replay.md)).
  It is not BART's map artwork, and it uses no BART logo. Tracks are one neutral grey.
- **What a station shows:** a bubble for its median ETA revision. The bubble's area grows
  with the size of the revision, and its colour deepens from 15 s to 90 s.
  - **Direction:** a later ETA runs from amber through orange to red as the revision
    grows, so a larger miss in BART's estimate looks worse; an earlier one deepens in teal.
    The pair stays apart for the common colour-vision deficiencies. The direction is also a
    chevron inside the bubble, so it never depends on colour.
  - **Little or no change** (under 15 s) is a small stone dot.
  - **No supported forecast at this replay moment** is a small grey ring.
  - **Why bubbles:** almost every revision at this moment is 15 to 90 s later. Size and
    colour show that spread, where same-coloured symbols would not.
- **Two modes:** "Model forecast at the time" draws the median predicted revision. A
  dotted ring then shows what BART later published, so the gap between bubble and ring is
  the model's miss. "What BART later published" draws the median realized revision, with a
  thin ring for the forecast. Rings are drawn only where they differ visibly from the
  bubble.
- **One line at a time:** a "Line" control (All, Red, Orange, Yellow, Green, Blue,
  `&line=`) does three things:
  - it draws that line's track in its route colour over an ink casing;
  - it fades the other lines;
  - it recomputes every bubble, the station panel, the table and the takeaway from that
    line's trains only (`network-map.json` `trains`, `web/src/domain/mapData.ts`).
- **Summary:** a computed takeaway above the map says how many stations moved later or
  earlier.
- **Stations:** each is a focusable button, in reading order, with a full accessible name.
  Enter or Space selects it. A skip link passes the 50 stops.
- **Station panel:** the selected station's supported train count, its largest predicted
  and realized revisions (the current mode's first) with destination and line, and a link
  to that train in the explorer.
- **Table fallback:** an expandable table lists every station.
- **Fit:**
  - The drawing always fits the window: it takes the frame's width, and on a wide screen
    is capped at the window's height. The page never scrolls sideways.
  - On a phone the station panel sits directly under the map. Only line ends, junctions
    and the selected station are named, at a readable size: the ends first, and any other
    name that would touch one already placed is left out. The table names the rest.
  - **Label placement** (`web/src/views/mapLabels.ts`): a greedy pass tries eight sides
    and takes the first that collides with no name or bubble.
    - Five stations in the Oakland and downtown San Francisco core are placed by hand.
    - "West Oakland" and "Oakland Airport" take two lines, so the core stays legible
      whatever size its bubbles are drawn.
    - A test checks that no two names overlap on any line, in either mode.

### Train explorer

- **What it keeps:** the existing station search, boarding-group choice, train list,
  forecast readout and ETA history.
- **What it lists:** only trains with a supported model forecast. The curated replay
  contains no others, and the development modes leave the rest out too, so the site has no
  "BART ETA only" state.
- **First train:** with no train in the address, it opens the Highlights view's first entry.
- **The readout, in order:**
  1. BART published ETA at the replay moment (the large clock);
  2. the model's expected ETA revision ("Expected to move about 1 min later");
  3. the model-adjusted ETA ("not an observed arrival time");
  4. the uncertainty (stability, the chance of a revision over 60 s, the 80% range);
  5. "BART later published", with a Retrospective tag, a dashed outline, and whether the
     direction matched;
  6. then the ETA history.

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
├── public/replay/             the published static replay (static mode only; tracked)
├── vite.config.ts             base path, data mode ('@data-mode' alias), description, Vitest config
├── vitest.build.config.ts     config for the build-artifact tests
├── build-tests/               isolation.test.ts: builds all three modes and checks each holds only
│                              its own client and data; buildMode.ts makes one build for it
├── eslint.config.js
├── .env.example               documented VITE_* variables (no secrets)
└── src/
    ├── main.tsx               fonts, global CSS, React root; renders '@data-mode'
    ├── App.tsx                composes the page for the PredictionClient it is given
    ├── modes/                 mock.tsx, http.tsx, static.tsx: one per data mode, each rendering
    │                          App with its own client; vite.config.ts picks one per build (+ tests)
    ├── components/            SiteHeader, Opening, ExampleLink, PredictionExample,
    │                          StationPicker, TrainTimetable, PredictionReadout, StabilityMark,
    │                          EtaHistory, HistoryChart, ObservationTable, ProjectQuestion (+ tests)
    ├── data/
    │   ├── PredictionClient.ts        interface + PredictionClientError
    │   ├── MockPredictionClient.ts    deterministic simulated client (+ tests)
    │   ├── HttpPredictionClient.ts    client for the local API (+ tests)
    │   ├── StaticReplayClient.ts      client for the published static replay (+ tests)
    │   ├── apiDecode.ts               runtime validation of the API's JSON
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
    ├── clientContract.test.tsx  the page's states with the mock and HTTP clients
    ├── staticReplay.test.tsx  the page on the published static replay
    ├── metadata.test.ts       index.html description, Open Graph and Twitter tags
    └── test/                  setup.ts, fakeApi.ts (fetch over the recorded responses),
                               publishedReplay.ts (fetch over web/public/replay)
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
  such, in the readout's order: "BART said in this snapshot: 6:27:06 PM, 2 min 10 sec away.
  Expected to move about 12 seconds later. Model-adjusted ETA: 6:27:18 PM, about 2 min 22
  sec away." (Simulated data says "BART currently says".)
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
   ETA as a clock time ("10:05 AM"), the time away beneath it ("5 min 42 s"), then its
   model-adjusted ETA and stability ("Model-adjusted 10:05 AM · Likely to hold"). Only
   trains with a supported forecast are listed. When the group has no single
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
- The model-adjusted ETA is a dashed blue reference line, labelled "Model-adjusted".
  Its 80% range is a bracket in the right gutter, outside the time axis,
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
    its as-of time written out ("Tuesday, October 20, 2026 at 10:00 AM Pacific") and the
    statement that the data is fixed at that moment, is not live, and that nothing on
    the page updates or counts down. It appears once health confirms the replay mode.
    Until then the banner reads "Loading the data", and "Data unavailable" if health
    does not answer. These two labels suit both the local API and the static replay;
  - one concise reminder beside the result: "Historical replay—fixed, not live. BART data
    as of Tuesday, October 20, 2026 at 10:00 AM Pacific.";
  - the full provenance under "Data and model details".

  The words "simulated" and "live" are never used for replayed data, except to say it is
  not live, and replayed values are never in the present tense ("BART said in this
  snapshot", never "currently says" or "right now").
- **Freshness in a replay** is judged at the replay's as-of time, not against the
  visitor's clock, and it does not tick. A snapshot 37 s before the as-of time reads
  "Fresh at replay time · 37 s old at the replay time"; one older than 120 s gets the
  stale warning, worded "before the replay time", which stays visible beside the result.
- **Trains without full support.** A train with `predictionStatus` other than `ok` shows
  not listed at all: the explorer shows only trains with a supported forecast. A board with
  none says "No model-eligible trains", with the reason. A forecast whose range is not
  supported shows the forecast without a range. No value is ever simulated or invented in
  place of a missing one.
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

## Static replay client (GitHub Pages)

`StaticReplayClient` implements the same `PredictionClient` interface over the static
historical replay in `web/public/replay/` ([static_replay.md](static_replay.md)). It
declares the same `source` as the HTTP client, so no component knows which of the two it
is talking to. Each method reads one file:

| Method | File, under `<base path>replay/<export>/` |
|---|---|
| `listStations()` | `stations.json` |
| `getPredictions(stationId, boardingGroupId)` | `boards/<station>/<boarding group>.json` |
| `getPredictionHistory(predictionId)` | `history/<service date>_<trip>_<stop sequence>.json` |
| `getModelMetadata()` | `model.json` |
| `getHealth()` | `health.json` |

- **Index first.** It first reads `<base path>replay/index.json`, which names the export
  directory, its schema version (`static-replay-1`; any other is refused) and its replay
  time.
  - The index is requested once and shared, without any one caller's signal, so a
    cancelled request cannot fail it for the others.
  - A failed index is forgotten, so "Try again" asks for it again.
- **Lazy loading.** The page asks for the station list and health first, then only the
  board on screen and the selected train's history. A first visit fetches five data files
  of about 41 KB (3.8 KB gzipped). The other 1,050 histories and 94 boards are fetched
  only when chosen.
- **Same origin, under the base path.** URLs are built from `import.meta.env.BASE_URL`
  (`/bart-reliability/` in the Pages build, `/` in development). They are paths on the
  page's own origin, with no host, API address or external service.
- **Safe IDs.** A station, boarding-group or prediction ID that the exporter would never
  write as a file name (anything but letters, digits and `-`, or a malformed prediction
  ID) answers `not_found` without a request.
- **Validation.** Every file passes the same `apiDecode.ts` decoders as the HTTP client.
  The client also refuses a board for a different station or group, and a board or health
  answer from a different replay time than the index names.
- **Errors.** The client maps failures onto the existing `PredictionClientError`
  interface:
  - a missing file (404) is `not_found`;
  - invalid JSON, an unexpected shape, an unsupported schema version, another HTTP
    error or a failed request is `unavailable`.

  The page shows the same error states, with "Try again", as in the other modes.
- **Cancellation and stale responses.** The page's `AbortSignal` is passed to every file
  request, and `useRequest` discards any result for an older key. A slow board or
  history can therefore never replace a newer choice.

`web/src/data/StaticReplayClient.test.ts` reads every published station, board and
history through the client. `web/src/staticReplay.test.tsx` renders the page on the
published files and checks:
- the wording;
- that a first visit requests exactly the index, health, stations, one board and one
  history;
- deep links, a fallback train and an empty board;
- recovery from a missing or corrupted file and from an unsupported schema.

### Selecting the client

```bash
VITE_DATA_MODE=mock     # default; simulated fixtures (the dev server and every test)
VITE_DATA_MODE=http     # the local API at VITE_API_BASE_URL
VITE_DATA_MODE=static   # the published static replay in web/public/replay (GitHub Pages)
VITE_API_BASE_URL=http://127.0.0.1:8000   # in web/.env.local (ignored by git)
```

The mode is chosen when the site is built or served, not when the page runs, so each build
contains only its own client and that client's data:
- **One module per mode.** `src/modes/mock.tsx`, `http.tsx` and `static.tsx` each export
  `Site`, which renders `App` with that mode's client. `App` takes the client as a prop and
  imports no client.
- **One alias.** `src/main.tsx` imports `Site` from `'@data-mode'`. `vite.config.ts` resolves
  that name to `src/modes/<VITE_DATA_MODE>.tsx` alone, so no other mode's module is ever
  part of the build. `vite-env.d.ts` declares the module, and `src/modes/modes.test.tsx`
  checks at compile time that all three modules match the declaration.
- **Explicit selection.**
  - An unset `VITE_DATA_MODE` means `mock`.
  - Any value other than `mock`, `http` or `static` stops the dev server or build with an
    error, so a typo can never quietly build the simulated site.
  - The dev server and each build print the mode they use.
  - `npm run dev:http` and `npm run dev:static` select the other two modes for one run.
- **What each build holds.**

  | Build | Client | Data |
  |---|---|---|
  | Static (GitHub Pages) | `StaticReplayClient` and the API decoders | `public/replay/` |
  | HTTP | `HttpPredictionClient`, the API decoders and the API address | none |
  | Mock | `MockPredictionClient` | its simulated fixtures, with the 50-station network as a separate chunk |

  The development state selector is in no production build.
- **Checked.** `npm run test:build` (`build-tests/isolation.test.ts`, also run in CI) makes
  the three production builds into temporary directories. It fails if a build contains:
  - another mode's source modules, chunks or distinctive strings, such as a fixture's
    made-up alert, the API's paths or the replay's schema name;
  - an API address, unless it is the HTTP build;
  - any data file, unless it is the static build, which must ship `public/replay/` byte
    for byte.

  The shared page code still holds the wording for every kind of data source (for example
  the simulated-data disclosure). It is part of `App`, not of a client.

The dev server stays on simulated data unless another mode is given for that run,
so design work and the dev panel are unaffected by `.env.local`. Tests pin
`VITE_DATA_MODE=mock` in `vite.config.ts` and inject any client they need, so they never
depend on a developer's local settings or a running API. `public/` is copied into the
static build only. `VITE_*` values are compiled into the public bundle, so they must never
hold secrets, and no server or production address is committed.

## Local development

```bash
cd web
npm install
npm run dev         # prints http://localhost:5173/ (simulated data)
npm run dev:static  # the same, on the published static replay
npm run dev:http    # the same, on the local API at VITE_API_BASE_URL
npm run test        # Vitest unit tests, once
npm run test:build  # build-artifact tests: each mode's build holds only its own client and data
npm run lint        # ESLint + tsc -b
npm run build       # type-check + production build into web/dist/
npm run preview     # serve the production build
```

To run the site against the local historical-replay API, start two processes from the
repository root, each in its own terminal:

```bash
.venv/bin/bart-serve-local                     # API on http://127.0.0.1:8000
cd web && npm run dev:http                      # site on http://localhost:5173/
```

The API answers as of its default replay time, 2026-10-20T17:00:00Z (10:00 AM Pacific),
with model `0.2.0+886fcd260732` (see `docs/local_api.md`). The page shows that time in
its replay banner. The GitHub Pages build never calls this API.

To run the site on the published static replay, as GitHub Pages serves it, with no API
running:

```bash
cd web && npm run dev:static                    # site on http://localhost:5173/
```

## GitHub Pages base path

`vite.config.ts` serves from `/` in development. A production build defaults to
`/bart-reliability/`, the GitHub Pages project-site path. To change it, set
`VITE_BASE_PATH` (for example `VITE_BASE_PATH=/ npm run build` for a root or custom
domain). Components do not hard-code paths: in-page links are fragments, fonts and CSS go
through Vite's asset pipeline, and any future static asset should use
`import.meta.env.BASE_URL`.

`.github/workflows/deploy-pages.yml` publishes the static historical-replay build
(`VITE_DATA_MODE=static`, `VITE_BASE_PATH=/bart-reliability/`) to
<https://millerroberts180.github.io/bart-reliability/>.
- **Check first.** Before building, it runs `bart-static-replay check web/public/replay`,
  the offline check of the published replay. It installs only the package and pydantic,
  and needs no warehouse, model or API.
- **Push to main only.** It deploys only after a push to `main`, such as a merged pull
  request. A manual run from any branch, `main` included, checks and builds but does not
  deploy. The repository's `github-pages` environment also accepts deployments only from
  `main`.
- **No API.** Nothing beyond static files is deployed.
- **CI.** It runs the same check and also builds the static Pages build, the simulated
  build and the HTTP build.

## Page metadata

`web/index.html` describes the historical-replay site: "A historical replay of recorded
BART data, with a model of how BART revises a train's published arrival estimate before it
arrives. Not live, and not a prediction of physical arrival." The same title and
description are given as Open Graph (`og:type`, `og:site_name`, `og:title`,
`og:description`) and Twitter (`twitter:card` "summary", `twitter:title`,
`twitter:description`) tags. A simulated build shows no BART data, so `vite.config.ts`
swaps all three descriptions for a simulated-data one in mock mode. The static (deployed)
and HTTP builds keep the replay text. `metadata.test.ts` checks the tags.

Not done yet for the deployed site:
- add `<link rel="canonical">` and `og:url` with its address;
- design a social image and add `og:image`, `og:image:alt`, `twitter:image` and
  `twitter:card` "summary_large_image".

## Data credit and independence

The footer (`SiteFooter.tsx`) is the same in every data mode. It states where the data
comes from and who publishes the site:

> Source data: GTFS schedule and GTFS-Realtime feeds from BART (San Francisco Bay Area
> Rapid Transit District), published through BART's developer program and used under
> the BART Developer License Agreement.
>
> ETA Reliability is an independent project. It is not an official BART product, and it
> is not affiliated with or endorsed by BART.

The two links:
- "developer program" goes to <https://www.bart.gov/about/developers>;
- "BART Developer License Agreement" goes to
  <https://www.bart.gov/schedules/developers/developer-license-agreement>.

The agreement does not allow BART trademarks or copyrighted materials to be used with
the data. The site therefore has no BART logo and no official system map. Its only
graphics are its own:
- the ETA history chart;
- the stability marks;
- the line-colour cues, from GTFS `route_color`;
- the favicon.

The historical-replay disclosures in the opening and beside the forecast are separate
from the footer, and the footer does not replace them. `App.test.tsx` checks the
footer's wording and links.

## Design principles

These were chosen after studying one public editorial data story (for principles, not
appearance) and reconciling the result with this project's accuracy and accessibility
requirements.

1. **Lead with what BART said.** BART's published ETA at the replay moment comes first and
   is the largest value in the section; the model's revision and the model-adjusted ETA
   follow, then what BART later published, marked retrospective: up to 92 px, against 17 px for the station heading and 15 px for
   the summary rows. Its clock is always minute precision and is sized to the card
   (`cqi`), so the full time and AM/PM always fit on one line, down to 320 px. "About …
   away" sits directly under it, then the summary, then detail that steps down in size and
   contrast, with the arithmetic and technical details one press away. A clock time and its
   AM/PM never wrap apart.
2. **Disclose before claiming.** "Historical replay of recorded BART data", with its
   as-of time and a fixed-not-live statement (in the static and HTTP builds), or
   "Prototype using simulated data" (mock), sits beside the title, above the fold on
   desktop and mobile. It comes before any number is shown.
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
- Methodology section and a fuller footer. The current footer holds the data credit and
  the independence notice ([Data credit and independence](#data-credit-and-independence)).
- A live (not replayed) API, and hosting the API anywhere but the developer's machine
- Dark color scheme
- "Use my location" in the station picker (no geolocation is requested today)

## Known limitations

- **One moment.** The public site is one fixed moment, 2026-10-19 at 8:10 AM PDT. A
  station, group or train outside the curated replay is not found; the explorer falls back
  to the first supported train.
- **A curated subset.** The showcase lists only the model-eligible trains (83 of the 1,067
  board entries at that snapshot). Most trains on a board are outside the 5-, 10- and
  15-minute windows.
- **No physical arrivals.** "BART later published" is BART's own final stable estimate, not
  an observed arrival.
- **Map touch targets and labels on phones.** On a phone the whole network is scaled to the
  screen. Station hit areas are then smaller than 44 px, and most station names are left
  off, so the station table is the reliable way to choose and identify a station there.
- **Map scale.** The schematic is not to geographic scale. Station positions come from a
  grid that follows the GTFS station order.
- **Platforms.** Platform numbers come from the schedule. A platform change on the day is
  not detected.
- **Provisional settings.** The stability cutoffs (0.25 and 0.5) and the 120 s freshness
  limit are provisional.
- **Time zone.** Clock times are in Pacific time regardless of the viewer's time zone.
- **Development modes.** In mock mode all values are simulated, and Highlights and the map
  have no data.
