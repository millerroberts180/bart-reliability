# Website architecture (Milestone 1 prototype)

**Status:** Milestone 1, the frontend foundation plus one vertical slice. Everything the site
displays is simulated. No model, API or BART data is connected yet.

The site, **ETA Reliability**, is the public explainer for the ETA-revision project ("How
stable are BART's published arrival estimates?"). Its first slice lets a visitor pick a
station, direction and train, and read one prediction in three steps:

1. **BART says now:** BART's current published clock time and the time remaining.
2. **Expected change:** how much BART is expected to change that estimate, always in words
   ("about 12 seconds later"), with an 80% likely range.
3. **Likely final published ETA:** the strongest value, as a clock time and time remaining.

The arithmetic behind it is shown as a secondary line:

```text
current published ETA + predicted revision = likely final published ETA
```

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
    ├── components/            SiteHeader, Opening, PredictionExample, TrainTimetable,
    │                          PredictionReadout, StabilityMark (+ tests)
    ├── data/
    │   ├── PredictionClient.ts        interface + PredictionClientError
    │   ├── MockPredictionClient.ts    deterministic simulated client (+ tests)
    │   ├── HttpPredictionClient.ts    placeholder for the future API
    │   ├── createPredictionClient.ts  VITE_DATA_MODE → client
    │   ├── PredictionClientContext.tsx  provider + hook (client and clock)
    │   └── fixtures/simulated.ts      the only place simulated values live
    ├── domain/
    │   ├── types.ts           data contracts
    │   └── eta.ts             ETA arithmetic, stability classes, freshness, formatting (+ tests)
    ├── hooks/                 useRequest (abortable, keyed loading), useNow (clock tick)
    ├── dev/                   development-only state selector (excluded from builds)
    ├── styles/                tokens.css, base.css, app.css
    └── test/setup.ts
```

## Data contracts

Defined in `web/src/domain/types.ts`. Timestamps are ISO 8601 UTC strings. Durations are
whole seconds.

| Type | Purpose |
|---|---|
| `Station` | `id` (GTFS stop id), `name`, `directions` |
| `Direction` | `id` (GTFS `direction_id`), rider-facing `label`, `destinations` |
| `TrainPrediction` | One trip-stop: `currentEtaSeconds` / `currentEtaAt` (BART's published ETA), `predictedRevisionSeconds` (positive = later), an 80% `revisionInterval`, `revisionProbability` (P(revision of more than the threshold, either way)), `stability` |
| `PredictionHistoryPoint` | One published ETA at one feed snapshot (for the later history chart) |
| `AlertContext` | An alert *visible in the feed* at prediction time: scope, category, header, `visibleSince`. Visibility is not evidence of a disruption (see `docs/service_alerts.md`) |
| `ModelMetadata` | `modelVersion`, `trainedThrough`, `revisionThresholdSeconds`, `simulated` |
| `PredictionResponse` | `feedTimestamp`, `generatedAt` (model timestamp), `trains`, `alerts`, `model` |
| `HealthStatus` | API status and latest feed snapshot |

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
  `describeRevisionRange` ("10 seconds earlier to 35 seconds later"), `describeTimeAway`, and
  `formatClock`. The two primary clocks (BART says now, likely final published ETA) always
  show seconds, so a sub-minute revision never makes the two estimates look identical.
  `formatClockMinute` (seconds dropped, not rounded) is used only for the stale-snapshot
  wording.
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
- takes a `scenario` (`live`, `loading`, `error`, `stale`, `empty`) so every interface
  state can be reproduced. `loading` never resolves until aborted;
- honours `AbortSignal`. `useRequest` aborts the previous request whenever the selection
  changes, so a slow response cannot overwrite a newer one;
- simulates latency (350 ms in the app, 0 in tests).

In development only, a dashed strip after the page content ("Dev · preview state")
switches the scenario. It sits in normal document flow, so it never covers content. It is loaded with a dynamic import that is guarded by
`import.meta.env.DEV`, so it does not appear in production builds (verified by searching
`dist/`).

## Future API boundary

`HttpPredictionClient` defines the boundary but makes no network requests: every method
rejects with `PredictionClientError('not_implemented')`. Provisional endpoints, one per
interface method:

| Method | Endpoint |
|---|---|
| `listStations()` | `GET /api/v1/stations` |
| `getPredictions(stationId, directionId)` | `GET /api/v1/predictions?station_id=...&direction_id=...` |
| `getPredictionHistory(predictionId)` | `GET /api/v1/predictions/{prediction_id}/history` |
| `getModelMetadata()` | `GET /api/v1/model/metadata` |
| `getHealth()` | `GET /api/v1/health` |

Responses are expected to match the TypeScript contracts above (camelCase JSON, or a mapping
layer added in the client). Select the client with:

```bash
VITE_DATA_MODE=mock   # default; simulated fixtures
VITE_DATA_MODE=http   # placeholder; every request fails with "not implemented"
VITE_API_BASE_URL=    # API origin for http mode (unused for now)
```

`VITE_*` values are compiled into the public bundle, so they must never hold secrets.

## Local development

```bash
cd web
npm install
npm run dev      # prints http://localhost:5173/
npm run test     # Vitest, once
npm run lint     # ESLint + tsc -b
npm run build    # type-check + production build into web/dist/
npm run preview  # serve the production build
```

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

1. **Lead with the answer.** The result reads in a fixed order: what BART says now, the
   expected change, then the likely final published ETA, which is the largest and heaviest
   value. Uncertainty, stability, freshness, alerts and model metadata stay visible but
   step down in size and contrast. The arithmetic is a secondary explanation, and each
   operator is kept on the same line as its value so it can't be separated when the line
   wraps.
2. **Disclose before claiming.** "Prototype using simulated data" sits beside the title,
   above the fold on desktop and mobile. It comes before any number is shown.
3. **Three typographic voices, each with one job.** Schibsted Grotesk for headings and
   controls, Source Serif 4 for prose, and JetBrains Mono for measurements, timestamps and
   labels. Mono is never decoration.
4. **Color only carries meaning.** A warm off-white ground, blue-tinted charcoal ink and a
   single signal blue for interaction and focus. Three muted state colors mark stability and
   freshness, and each is always paired with a text label and a distinct shape (a flat,
   one-step or two-step ETA trace). Every text pairing is at least 5.0:1.
5. **Rules, not cards.** Sections are separated by thin rules. The only framed surfaces are
   the disclosure and the readout. There are no shadows, gradients or nested containers.
6. **Show uncertainty as a range.** Each revision comes with its probability and an 80%
   range, and the copy says BART may revise the estimate. The interface never presents a
   single "true" time.
7. **Stable layout across states.** Loading, failure, stale and empty states keep the
   readout's position and minimum height. Motion is limited to state feedback (hover, the
   probability fill) and is disabled under `prefers-reduced-motion`.

## Deferred to later milestones

- Prediction-history chart (`getPredictionHistory` is implemented in the mock only)
- System findings, the exploration dashboard and filters
- Methodology section and full footer
- Live API, trained model and production data
- Deployment workflow (GitHub Pages)
- Dark color scheme

## Known limitations

- All values are simulated. Line and destination pairings follow BART's public network
  but are not checked against a specific timetable.
- Stability cutoffs (0.25 / 0.5) and the 120 s freshness limit are provisional.
- Freshness is re-evaluated every 15 s; the countdown does not tick every second.
- Clock times are formatted in Pacific time regardless of the viewer's time zone.
- The result describes changes to BART's published estimate only. It makes no claims about
  skipped or changed stops, missed connections or cancellations. A visible service alert is
  shown as context, never as a predicted change to the train.
