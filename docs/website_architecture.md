# Website architecture (prototype)

**Status:** Milestone 1 (frontend foundation and one prediction), Milestone 2 (ETA
history chart) and the local API integration. By default everything the site displays is
simulated. Started with `VITE_DATA_MODE=http`, it reads the local historical-replay API
(`docs/local_api.md`) instead and labels every value as a historical replay of recorded
BART data. Nothing is live, and the site is not deployed with the API.

The site, **ETA Reliability**, is the public explainer for the ETA-revision project ("How
stable are BART's published arrival estimates?"). Its first slice lets a visitor pick a
station, direction and train, and read one prediction. The result is built to be read at a
glance, for example on a platform:

1. **Compact identity:** station · destination, then the line (with its route-colour cue),
   direction, car count, trip number and the "Simulated" tag, all at supporting size.
2. **Likely final published ETA:** the largest element in the example, built for a glance.
   It shows a very large clock time, always to the minute ("6:27 PM"). Underneath is the
   time away rounded to whole minutes ("About 2 min away", or "Less than 1 min away"),
   then the 80% likely range and "Model forecast of BART's last published ETA, not an
   observed arrival."
3. **Calculation, directly beneath:** three labelled rows that reproduce the relationship
   without a paragraph:

   ```text
   BART currently says          5:56 PM · 10 min 10 sec away
   + Expected adjustment        About 2 min 20 sec later
   = Likely final published ETA 5:58 PM · about 12 min 30 sec away
   ```

   (current published ETA + predicted revision = likely final published ETA). The
   direction is always in words. The `+` and `=` are visual only; screen readers hear the
   labels.
4. **Detail, below:** adjustment range, ETA stability, the full caveat, service alerts,
   feed freshness and the model timestamp. All of it stays visible, at smaller sizes.

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
├── vite.config.ts             base-path handling and Vitest config
├── eslint.config.js
├── .env.example               documented VITE_* variables (no secrets)
└── src/
    ├── main.tsx               fonts, global CSS, React root
    ├── App.tsx                chooses the PredictionClient, composes the page
    ├── components/            SiteHeader, Opening, ExampleLink, PredictionExample,
    │                          TrainTimetable, PredictionReadout, StabilityMark,
    │                          EtaHistory, HistoryChart, ObservationTable (+ tests)
    ├── data/
    │   ├── PredictionClient.ts        interface + PredictionClientError
    │   ├── MockPredictionClient.ts    deterministic simulated client (+ tests)
    │   ├── HttpPredictionClient.ts    client for the local API (+ tests)
    │   ├── apiDecode.ts               runtime validation of the API's JSON
    │   ├── createPredictionClient.ts  VITE_DATA_MODE → client
    │   ├── PredictionClientContext.tsx  provider + hook (client and clock)
    │   ├── clientKey.ts               per-client request keys
    │   └── fixtures/
    │       ├── simulated.ts           the only place simulated values live
    │       └── apiReplay.json         recorded local-API responses, for tests only
    ├── domain/
    │   ├── types.ts           data contracts
    │   ├── eta.ts             ETA arithmetic, stability classes, freshness, formatting (+ tests)
    │   └── history.ts         history analysis, gaps, revision count, summary wording (+ tests)
    ├── hooks/                 useRequest (abortable, keyed loading), useNow (clock tick),
    │                          useFreshness, useDataSource (provenance for the opening),
    │                          useElementWidth (chart sizing)
    ├── dev/                   development-only state selector (excluded from builds)
    ├── styles/                tokens.css, base.css, app.css
    ├── clientContract.test.tsx  the page's states with both clients
    └── test/                  setup.ts, fakeApi.ts (fetch over the recorded responses)
```

## Data contracts

Defined in `web/src/domain/types.ts`. Timestamps are ISO 8601 UTC strings. Durations are
whole seconds.

| Type | Purpose |
|---|---|
| `Station` | `id` (GTFS stop id), `name`, `directions` |
| `Direction` | `id` (GTFS `direction_id`), rider-facing `label`, `destinations` |
| `TrainPrediction` | One trip-stop, either a `ForecastTrain` or an `EtaOnlyTrain`, told apart by `predictionStatus`. Both carry BART's published ETA (`currentEtaSeconds` / `currentEtaAt`). Only `predictionStatus: "ok"` adds model numbers: `predictedRevisionSeconds` (positive = later), `revisionProbability` (P(revision of more than the threshold, either way)), `stability`, and an 80% `revisionInterval` that is `null` when no range is supported. Every other status (`outside_model_horizon`, `outside_model_population`, `fallback_required`, `features_unavailable`) has all four set to `null` |
| `PredictionHistoryPoint` | One published ETA at one feed snapshot (for the later history chart) |
| `AlertContext` | An alert *visible in the feed* at prediction time: scope, category, header, `visibleSince`. Visibility is not evidence of a disruption (see `docs/service_alerts.md`) |
| `ModelMetadata` | `modelVersion`, `trainedThrough`, `revisionThresholdSeconds`, `simulated` |
| `PredictionResponse` | `dataProvenance` (`simulated` or `historical_replay`), `replay` (`{asOf}` exactly when replayed), `feedTimestamp`, `generatedAt` (model timestamp), `trains`, `unplacedTrainCount` (trains listed at the station with no known direction; 0 when simulated), `alerts`, `model` |
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
  is rounded to whole minutes by `describeAwayGlance`. The exact values sit in the
  calculation directly underneath. There, `needsSeconds(current, final)` is true when the
  two times differ but read the same to the minute, and then both calculation clocks show
  seconds ("6:27:06 PM" and "6:27:18 PM"). A sub-minute adjustment is therefore never
  hidden. The time-away values in the calculation are always exact ("2 min 22 sec").
- The screen-reader summary gives the glance first, then the exact calculation, labelled as
  such: "Likely final published ETA: 6:27 PM, about 2 min away. Exact calculation: BART
  currently says 6:27:06 PM, 2 min 10 sec away; expected adjustment about 12 seconds later;
  likely final published ETA 6:27:18 PM, about 2 min 22 sec away."
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
  `eta-only`) so every interface state can be reproduced. `loading` never resolves until
  aborted; `no-interval` drops every range and `eta-only` marks every train
  `outside_model_horizon`, the two shapes the API returns for trains without full support;
- takes a separate `historyScenario` (`normal`, `loading`, `error`, `single`, `none`,
  `gaps`) for the history states (see "ETA history" below);
- honours `AbortSignal`. `useRequest` aborts the previous request whenever the selection
  changes, so a slow response cannot overwrite a newer one;
- simulates latency (350 ms in the app, 0 in tests).

In development only, a dashed strip after the page content ("Dev · preview state")
switches the scenario ("Mock response") and the history scenario ("History response"). It sits in normal document flow, so it never covers content. It is loaded with a dynamic import that is guarded by
`import.meta.env.DEV`, so it does not appear in production builds (verified by searching
`dist/`).

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
  response (the mock remembers that snapshot per station and direction);
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
- The latest observation is the larger point, labelled "Latest" in the right gutter.
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
- The SVG is a labelled group. Each observation is a point with an accessible name that
  gives the snapshot time, BART's published arrival time, time away, and the change from
  the previous snapshot.
- The points use a roving tab stop, so the whole chart is one stop in the Tab order. The
  arrow keys move between snapshots, and Home and End jump to the first and last.
- Hovering, tapping or focusing a point updates a visible inspection line beneath the chart,
  so nothing depends on hover.
- "Show all N observations" opens a full data table with the same values, including gap
  rows. On narrow screens each row stacks into a labelled block, and explicit table roles
  keep the semantics when the display changes.
- The summary comes before the chart. Chart text stays at the 13 px label size, because the
  SVG is laid out from the measured container width, not scaled through a `viewBox`. The
  chart has no animation.

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
| `getPredictions(stationId, directionId)` | `GET /api/v1/stations/{station_id}/predictions?direction_id=...` |
| `getPredictionHistory(predictionId)` | `GET /api/v1/predictions/{prediction_id}/history` |
| `getModelMetadata()` | `GET /api/v1/model/metadata` |
| `getHealth()` | `GET /api/v1/health` |

- **Requests.** Path identifiers are URL-encoded, requests ask for JSON and never send
  cookies (`credentials: "omit"`), and the page's `AbortSignal` is passed through, so a
  superseded request is cancelled rather than overwriting a newer one.
- **Validation.** `apiDecode.ts` checks every field the page uses before the page sees it.
  A response whose `dataMode` is anything other than `historical_replay` is rejected, so
  unlabelled data cannot be shown. A forecast needs a probability between 0 and 1 and a
  range with lower ≤ upper; a train without a forecast must carry no model numbers at all.
  A board for a different station or direction than requested is rejected too. Extra API
  fields are ignored.
- **Errors.** Failures become `PredictionClientError`, so the page shows the same error
  states as with the mock. The API's own `error.clientCode` and message are used when
  present (404 → `not_found`, 503 → `unavailable`); otherwise 404 → `not_found` and anything
  else, an unreachable API or an invalid body → `unavailable`. With no address configured,
  every call fails with `unavailable` before any request is made.
- **Provenance.** Each response says where its data came from. With a replay, the readout
  shows a "Historical replay" tag and a banner: "Historical replay, not live. Recorded BART
  data as of Thu, Oct 15, 2026, 10:00 AM Pacific." The opening's disclosure becomes
  "Historical replay of recorded BART data" once `/health` confirms the replay mode
  ("Connecting to the prediction API" until then, "Prediction API unavailable" if it does
  not answer). The words "simulated" and "live" are never used for replayed data, except
  to say it is not live.
- **Freshness in a replay** is judged at the replay's as-of time, not against the
  visitor's clock, and it does not tick. A snapshot 37 s before the as-of time reads
  "Current · 37 s old at the replay time"; one older than 120 s gets the stale warning,
  worded "before the replay time".
- **Trains without full support.** A train with `predictionStatus` other than `ok` shows
  BART's published ETA only, as published, with one sentence saying why (for
  `outside_model_horizon`: "The model only forecasts trains BART shows about 5, 10 or 15
  minutes away."). The timetable marks it "BART ETA only". A forecast whose range is not
  supported shows the forecast and says "No likely range is shown". No value is ever
  simulated or invented in place of a missing one.
- **Empty boards** say why when the response shows it: trains toward the chosen station
  end their trips there (BART's feed almost never lists a train at its last stop), or
  the feed lists trains at the station that match no scheduled trip and so have no
  direction (`unplacedTrainCount`). Otherwise the page gives the general reasons: service
  may have ended, the direction may not be running, or the feed may not include it.

`web/src/clientContract.test.tsx` renders the whole page with the mock client and with the
HTTP client over a fake `fetch` serving recorded API responses
(`data/fixtures/apiReplay.json`, recorded at as-of 2026-10-15T17:00:00Z). The same checks
cover a forecast with and without a range, a train with no forecast, loading, no trains, a
stale snapshot, a failed request and its retry, missing history and a failed history request.
They also check that changing the station, direction and train requests the matching
data, and that the forecast and the history always describe the same train.

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
.venv/bin/bart-serve-local --warehouse data/warehouse/<snapshot>.duckdb   # API on http://127.0.0.1:8000
cd web && VITE_DATA_MODE=http npm run dev                                 # site on http://localhost:5173/
```

The API answers as of its default replay time (2026-10-15T17:00:00Z, see
`docs/local_api.md`), and the page shows that time in its replay banner.

## GitHub Pages base path

`vite.config.ts` serves from `/` in development. A production build defaults to
`/bart-reliability/`, the GitHub Pages project-site path. To change it, set
`VITE_BASE_PATH` (for example `VITE_BASE_PATH=/ npm run build` for a root or custom
domain). Components do not hard-code paths: in-page links are fragments, fonts and CSS go
through Vite's asset pipeline, and any future static asset should use
`import.meta.env.BASE_URL`. No deployment workflow exists yet.

## Design principles

These were chosen after studying one public editorial data story (for principles, not
appearance) and reconciling the result with this project's accuracy and accessibility
requirements.

1. **Lead with the answer.** The likely final published ETA comes first and is the largest
   value in the section: up to 92 px, against 17 px for the station heading and 15 px for
   the calculation rows. Its clock is always minute precision and is sized to the card
   (`cqi`), so the full time and AM/PM always fit on one line, down to 320 px. "About … away" sits directly under it, then the
   calculation, then detail that steps down in size and contrast. Time, AM/PM and the
   "away" phrase never wrap apart.
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

## Deferred to later milestones

- System findings, the exploration dashboard and filters
- Methodology section and a fuller footer. The current footer holds only the
  independence notice: "Independent project using BART open data. Not affiliated with or
  endorsed by BART."
- A live (not replayed) API, and hosting the API anywhere but the developer's machine
- Deployment workflow (GitHub Pages)
- Dark color scheme

## Known limitations

- In the default mode all values are simulated. Line and destination pairings follow
  BART's public network but are not checked against a specific timetable.
- With the local API, most trains show BART's ETA only: the model serves only published-time
  horizons of 5, 10 and 15 minutes (±60 s), so at a given moment only a few trains per
  board have a forecast (for example 1 of 3 at Castro Valley toward Daly City at the
  tested replay time). 9 of 100 boards are empty at the tested replay time, for the
  reasons in `docs/local_api.md` ("Empty boards").
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
