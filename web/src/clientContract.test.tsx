// The same page, driven through the PredictionClient interface by the simulated client
// and by the HTTP client over recorded local-API responses. Every state the page can
// show must be reachable, and read the same way, with either client.

import { render, screen, within } from '@testing-library/react';
import userEvent, { type UserEvent } from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { App } from './App';
import { HttpPredictionClient } from './data/HttpPredictionClient';
import { MockPredictionClient, type MockHistoryScenario, type MockScenario } from './data/MockPredictionClient';
import type { PredictionClient } from './data/PredictionClient';
import { API_BASE, API_RECORDING, createFakeApi, type FakeApi } from './test/fakeApi';
import { chooseStation } from './test/picker';

type ClientName = 'mock' | 'http';

interface Recorded {
  client: PredictionClient;
  /** Calls the page made through the interface, e.g. "getPredictions CAST 1". */
  calls: string[];
  /** HTTP only: request paths as the API received them. */
  api?: FakeApi;
}

/** Wraps a client so the test sees which interface calls the page makes, for either kind. */
function recording(client: PredictionClient, api?: FakeApi): Recorded {
  const calls: string[] = [];
  const recorded: PredictionClient = {
    source: client.source,
    listStations: (signal) => (calls.push('listStations'), client.listStations(signal)),
    getPredictions: (stationId, groupId, signal) => (
      calls.push(`getPredictions ${stationId} ${groupId}`), client.getPredictions(stationId, groupId, signal)
    ),
    getPredictionHistory: (id, signal) => (calls.push(`getPredictionHistory ${id}`), client.getPredictionHistory(id, signal)),
    getModelMetadata: (signal) => (calls.push('getModelMetadata'), client.getModelMetadata(signal)),
    getHealth: (signal) => (calls.push('getHealth'), client.getHealth(signal)),
  };
  return api ? { client: recorded, calls, api } : { client: recorded, calls };
}

// The simulated client keeps the system clock, as in the app, so its snapshots are
// as fresh (or as stale) as each scenario intends.
function mock(scenario: MockScenario = 'live', historyScenario: MockHistoryScenario = 'normal'): Recorded {
  return recording(new MockPredictionClient({ scenario, historyScenario }));
}

function http(configure: (api: FakeApi) => void = () => undefined): Recorded {
  const api = createFakeApi();
  configure(api);
  return recording(new HttpPredictionClient(API_BASE, { fetch: api.fetch }), api);
}

const BOARD = (station: string, group: string) => `/api/v1/stations/${station}/predictions?boarding_group=${group}`;
const recordedBoard = (station: string, group: string) =>
  structuredClone(API_RECORDING.responses[BOARD(station, group)]) as { feedTimestamp: string; trains: Record<string, unknown>[] };

const readoutHeading = () => screen.findByRole('heading', { level: 3, name: /·|Prediction|No upcoming|Loading/ });
const history = () => screen.getByRole('region', { name: 'How this ETA has changed' });
const trainGroup = () => screen.getByRole('group', { name: 'Upcoming trains' });
const checkedTrain = () => within(trainGroup()).getAllByRole<HTMLInputElement>('radio').find((r) => r.checked)?.value;

/** A history with no change at all is shown compactly; open its full chart to read the key. */
async function chartKey(user: UserEvent) {
  await within(history()).findByTestId('history-summary');
  const toggle = within(history()).queryByRole('button', { name: 'Show the full chart' });
  if (toggle) await user.click(toggle);
  return within(history()).getByRole('list', { name: 'Chart key' });
}

/** How to reach a train with a forecast and its range from a fresh page. */
const OPEN_FORECAST: Record<ClientName, (user: UserEvent) => Promise<void>> = {
  mock: async () => undefined,
  http: async (user) => {
    await chooseStation(user, 'Castro Valley');
    await user.click(screen.getByRole('radio', { name: 'Toward Bay Fair and Daly City, Platform 2' }));
  },
};

/** The trains in the recorded Castro Valley board toward Dublin/Pleasanton are all outside the model horizon. */
const OPEN_ETA_ONLY: Record<ClientName, (user: UserEvent) => Promise<void>> = {
  mock: async () => undefined,
  http: async (user) => {
    await chooseStation(user, 'Castro Valley');
  },
};

interface StateCase {
  state: string;
  setup: Record<ClientName, () => Recorded>;
  open?: Record<ClientName, (user: UserEvent) => Promise<void>>;
  check: (user: UserEvent) => Promise<void>;
}

const STATES: StateCase[] = [
  {
    state: 'a forecast with its likely range',
    setup: { mock: () => mock(), http: () => http() },
    open: OPEN_FORECAST,
    check: async (user) => {
      const forecast = await screen.findByTestId('forecast');
      expect(forecast).toHaveTextContent(/^Likely final published ETA.*80% likely range: /);
      expect(screen.getByTestId('calc-adjust')).toHaveTextContent(/^\+?Expected adjustment/);
      expect(screen.getByTestId('calc-final')).toBeInTheDocument();
      expect(screen.getByTestId('summary-stability')).toHaveTextContent(/chance BART changes this estimate by more than 60 seconds/);
      const key = await chartKey(user);
      expect(key).toHaveTextContent(/Model’s likely final published ETA .*, with its 80% range at the right/);
    },
  },
  {
    state: 'a forecast without a likely range',
    setup: {
      mock: () => mock('no-interval'),
      http: () =>
        http((api) => {
          const board = recordedBoard('CAST', 'to-BAYF');
          for (const t of board.trains) if (t.predictionStatus === 'ok') t.revisionInterval = null;
          api.respond(BOARD('CAST', 'to-BAYF'), { body: board });
        }),
    },
    open: OPEN_FORECAST,
    check: async (user) => {
      expect(await screen.findByTestId('no-range')).toHaveTextContent(
        'No likely range is shown: the model’s range isn’t supported for this data.',
      );
      expect(screen.getByTestId('forecast')).not.toHaveTextContent(/likely range:/);
      expect(screen.getByText('Adjustment range').parentElement).toHaveTextContent('Not available for this forecast.');
      const key = await chartKey(user);
      expect(key).toHaveTextContent('; no likely range is available.');
    },
  },
  {
    state: 'a train with no model forecast',
    setup: { mock: () => mock('eta-only'), http: () => http() },
    open: OPEN_ETA_ONLY,
    check: async () => {
      const forecast = await screen.findByTestId('forecast');
      expect(forecast).toHaveTextContent(/^BART’s published ETA/);
      expect(screen.getByTestId('no-forecast')).toHaveTextContent(
        'No model forecast for this train. The model only forecasts trains BART shows about 5, 10 or 15 minutes away.',
      );
      // Nothing model-derived is drawn or stated for this train.
      expect(screen.queryByTestId('calc-adjust')).not.toBeInTheDocument();
      expect(screen.queryByText(/likely range/)).not.toBeInTheDocument();
      expect(screen.queryByText(/chance BART changes/)).not.toBeInTheDocument();
      expect(within(trainGroup()).getAllByText('BART ETA only').length).toBeGreaterThan(0);
      expect(
        await within(history()).findByText('No model forecast for this train, so the chart shows BART’s published ETA only.'),
      ).toBeInTheDocument();
    },
  },
  {
    state: 'loading',
    setup: {
      mock: () => mock('loading'),
      http: () => http((api) => api.respond('/api/v1/stations', () => new Promise<Response>(() => undefined))),
    },
    check: async () => {
      expect(await screen.findByRole('heading', { level: 3, name: 'Loading prediction…' })).toBeInTheDocument();
      expect(screen.queryByTestId('forecast')).not.toBeInTheDocument();
      expect(within(history()).getByText('Loading history…')).toBeInTheDocument();
    },
  },
  {
    state: 'no trains listed',
    // The recorded replay has no trains leaving Antioch, the first station.
    setup: { mock: () => mock('empty'), http: () => http() },
    check: async () => {
      expect(await screen.findByRole('heading', { level: 3, name: 'No upcoming trains' })).toBeInTheDocument();
      expect(within(trainGroup()).getByText('None listed')).toBeInTheDocument();
      expect(within(history()).getByText('No train is selected, so there is no history to show.')).toBeInTheDocument();
    },
  },
  {
    state: 'a stale snapshot',
    setup: {
      mock: () => mock('stale'),
      http: () =>
        http((api) => {
          // 9 min 40 s before the replay time, as in the simulated stale scenario.
          const board = recordedBoard('CAST', 'to-BAYF');
          board.feedTimestamp = '2026-10-15T16:50:20Z';
          api.respond(BOARD('CAST', 'to-BAYF'), { body: board });
        }),
    },
    open: OPEN_FORECAST,
    check: async () => {
      expect(await screen.findByRole('status')).toHaveTextContent(/^Stale data\. This snapshot is from .*, 9 min 4\d sec /);
      expect(screen.getByText('Stale')).toBeInTheDocument();
      expect(screen.getByTestId('calc-now')).toHaveTextContent(/^BART said at /);
      expect(await within(history()).findByText(/These snapshots end at .*, 9 min 4\d sec /)).toBeInTheDocument();
    },
  },
  {
    state: 'a failed prediction request, then a retry',
    setup: {
      mock: () => {
        const recorded = mock();
        let failures = 1;
        const inner = recorded.client;
        recorded.client = {
          ...inner,
          source: inner.source,
          getPredictions: (s, g, signal) =>
            failures-- > 0 ? Promise.reject(new Error('offline')) : inner.getPredictions(s, g, signal),
        };
        return recorded;
      },
      http: () =>
        http((api) => {
          let failures = 1;
          api.respond(BOARD('ANTC', 'to-PCTR'), () =>
            Promise.resolve(
              failures-- > 0
                ? Response.json({ error: { code: 'feed_unavailable', clientCode: 'unavailable', message: 'x' } }, { status: 503 })
                : Response.json(API_RECORDING.responses[BOARD('ANTC', 'to-PCTR')]),
            ),
          );
        }),
    },
    check: async (user) => {
      expect(await screen.findByRole('heading', { level: 3, name: 'Prediction unavailable' })).toBeInTheDocument();
      expect(screen.queryByTestId('forecast')).not.toBeInTheDocument();
      expect(within(history()).getByText('No history to show, because the prediction request failed.')).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: 'Try again' }));
      expect(await readoutHeading()).not.toHaveTextContent('Prediction unavailable');
    },
  },
  {
    state: 'a train with no earlier snapshots',
    setup: {
      mock: () => mock('live', 'none'),
      http: () => http((api) => api.respond('/api/v1/predictions/2026-10-15:1965774:2/history', { body: [] })),
    },
    open: OPEN_FORECAST,
    check: async () => {
      expect(await within(history()).findByTestId('history-summary')).toHaveTextContent(
        'No earlier snapshots of this ETA are available yet.',
      );
      expect(within(history()).queryByRole('figure')).not.toBeInTheDocument();
      // The prediction itself is unaffected.
      expect(screen.getByTestId('forecast')).toBeInTheDocument();
    },
  },
  {
    state: 'a failed history request',
    setup: {
      mock: () => mock('live', 'error'),
      http: () =>
        http((api) =>
          api.respond('/api/v1/predictions/2026-10-15:1965774:2/history', {
            status: 503,
            body: { error: { code: 'warehouse_unavailable', clientCode: 'unavailable', message: 'x' } },
          }),
        ),
    },
    open: OPEN_FORECAST,
    check: async () => {
      expect(await within(history()).findByText(/^The history request failed/)).toBeInTheDocument();
      expect(within(history()).getByRole('button', { name: 'Try again' })).toBeInTheDocument();
      expect(screen.getByTestId('forecast')).toBeInTheDocument();
    },
  },
];

describe.each(STATES)('the page shows $state', ({ setup, open, check }) => {
  it.each(['mock', 'http'] as const)('with the %s client', async (name) => {
    const user = userEvent.setup();
    render(<App client={setup[name]().client} />);
    await open?.[name](user);
    await check(user);
  });
});

/** The selection steps and what each should show, per client. */
const JOURNEYS: Record<
  ClientName,
  {
    first: { request: string; heading: string };
    station: { name: string; request: string; heading: string };
    boarding: { label: RegExp; request: string; heading: string };
    train: { radio: RegExp; heading: string };
  }
> = {
  mock: {
    first: { request: 'getPredictions EMBR to-MONT', heading: 'Embarcadero · SF Airport train' },
    station: { name: 'MacArthur', request: 'getPredictions MCAR to-ASHB-ROCK', heading: 'MacArthur · Richmond train' },
    boarding: {
      label: /^Toward San Francisco and Berryessa$/,
      request: 'getPredictions MCAR to-19TH',
      heading: 'MacArthur · SF Airport train',
    },
    train: { radio: /Millbrae/, heading: 'MacArthur · Millbrae train' },
  },
  http: {
    first: { request: 'getPredictions ANTC to-PCTR', heading: 'No upcoming trains' },
    station: { name: 'Downtown Berkeley', request: 'getPredictions DBRK to-NBRK', heading: 'Downtown Berkeley · Richmond train' },
    boarding: {
      label: /^Toward Berryessa\/North San Jose and Millbrae, Platform 2$/,
      request: 'getPredictions DBRK to-ASHB',
      heading: 'Downtown Berkeley · Millbrae train',
    },
    train: { radio: /Berryessa/, heading: 'Downtown Berkeley · Berryessa/North San Jose train' },
  },
};

describe.each(['mock', 'http'] as const)('selection with the %s client', (name) => {
  it('requests the chosen station, boarding group and train, and moves the forecast and history together', async () => {
    const user = userEvent.setup();
    const recorded = name === 'mock' ? mock() : http();
    const journey = JOURNEYS[name];
    render(<App client={recorded.client} />);

    /** The readout and the history describe the same train, and its history was the last one requested. */
    async function expectInStep(heading: string, request: string) {
      expect(await screen.findByRole('heading', { level: 3, name: heading })).toBeInTheDocument();
      expect(recorded.calls.filter((c) => c.startsWith('getPredictions')).at(-1)).toBe(request);
      if (heading === 'No upcoming trains') return;
      expect(await within(history()).findByText(`${heading} · BART’s published arrival time at each feed snapshot`)).toBeInTheDocument();
      await within(history()).findByTestId('history-summary');
      const selected = checkedTrain();
      expect(selected).toBeDefined();
      expect(recorded.calls.filter((c) => c.startsWith('getPredictionHistory')).at(-1)).toBe(`getPredictionHistory ${selected}`);
    }

    await expectInStep(journey.first.heading, journey.first.request);

    await chooseStation(user, journey.station.name);
    await expectInStep(journey.station.heading, journey.station.request);

    await user.click(screen.getByRole('radio', { name: journey.boarding.label }));
    await expectInStep(journey.boarding.heading, journey.boarding.request);

    const [nextTrain] = within(trainGroup()).getAllByRole('radio', { name: journey.train.radio });
    await user.click(nextTrain as HTMLElement);
    // Choosing a train re-reads nothing but that train's history.
    const boards = recorded.calls.filter((c) => c.startsWith('getPredictions')).length;
    await expectInStep(journey.train.heading, journey.boarding.request);
    expect(recorded.calls.filter((c) => c.startsWith('getPredictions'))).toHaveLength(boards);

    if (recorded.api) {
      // What actually went over the wire, in order (repeats removed), with the encoded history ids decoded.
      const paths = recorded.api.requests.filter((p, i, all) => all.indexOf(p) === i);
      expect(paths).toEqual([
        '/api/v1/health',
        '/api/v1/stations',
        BOARD('ANTC', 'to-PCTR'),
        BOARD('DBRK', 'to-NBRK'),
        expect.stringMatching(/^\/api\/v1\/predictions\/2026-10-15:\d+:\d+\/history$/),
        BOARD('DBRK', 'to-ASHB'),
        '/api/v1/predictions/2026-10-15:1965638:4/history',
        '/api/v1/predictions/2026-10-15:1965440:4/history',
      ]);
    }
  });
});

describe('empty boards', () => {
  const emptyText = async () => {
    await screen.findByRole('heading', { level: 3, name: 'No upcoming trains' });
    return screen.getByText(/^The latest snapshot lists no trains/).textContent;
  };
  const withCounts = (api: FakeApi, unplacedTrainCount: number, terminatingTrainCount = 0) =>
    api.respond(BOARD('ANTC', 'to-PCTR'), {
      body: { ...recordedBoard('ANTC', 'to-PCTR'), unplacedTrainCount, terminatingTrainCount },
    });
  const ANTIOCH_GROUP = 'toward Millbrae (Caltrain Transfer Platform) and San Francisco International Airport';

  it('gives the general reasons when nothing more is known (simulated)', async () => {
    render(<App client={mock('empty').client} />);
    expect(await emptyText()).toBe(
      'The latest snapshot lists no trains toward Daly City, SFO and Millbrae from Embarcadero. Service may have ended for the night, ' +
        'trains may not be running this way at the snapshot time, or BART’s feed may not include them.',
    );
  });

  it('counts trains with no known way out, and says a terminal is the end of the line', async () => {
    // Recorded replay: Antioch lists 5 unmatched trains, and every train there starts or ends its trip.
    render(<App client={http().client} />);
    expect(await emptyText()).toBe(
      `The latest snapshot lists no trains ${ANTIOCH_GROUP} from Antioch. BART’s feed does list 5 trains at Antioch ` +
        'that match no scheduled trip, so which way they’re going isn’t known and they aren’t shown.',
    );
    // One way out, and no invented direction for the unmatched trains.
    expect(within(screen.getByRole('group', { name: 'Which way are you going?' })).getAllByRole('radio')).toHaveLength(1);
    expect(
      screen.getByText('Antioch is the end of the line. Trains arriving here end their trips, so only trains leaving are listed.'),
    ).toBeInTheDocument();
  });

  it('uses the singular for one train and falls back to the general reasons with none', async () => {
    const first = render(<App client={http((api) => withCounts(api, 1)).client} />);
    expect(await emptyText()).toMatch(
      /BART’s feed does list 1 train at Antioch that matches no scheduled trip, so which way it’s going isn’t known and it isn’t shown\.$/,
    );
    first.unmount();
    render(<App client={http((api) => withCounts(api, 0)).client} />);
    expect(await emptyText()).toMatch(/from Antioch\. Service may have ended for the night, .*may not include them\.$/);
  });

  it('says when trains listed here end their trips, so they cannot be boarded', async () => {
    const one = render(<App client={http((api) => withCounts(api, 0, 1)).client} />);
    expect(await emptyText()).toBe(
      `The latest snapshot lists no trains ${ANTIOCH_GROUP} from Antioch. BART’s feed lists 1 train at Antioch that ` +
        'ends its trip here, so it can’t be boarded and isn’t shown.',
    );
    one.unmount();
    render(<App client={http((api) => withCounts(api, 5, 2)).client} />);
    expect(await emptyText()).toMatch(
      /BART’s feed lists 2 trains at Antioch that end their trips here, so they can’t be boarded and aren’t shown\. BART’s feed does list 5 trains/,
    );
  });
});

describe('boarding groups over the recorded replay', () => {
  it('never mixes Berryessa trains with Daly City or Richmond trains at Hayward', async () => {
    const user = userEvent.setup();
    const recorded = http();
    render(<App client={recorded.client} />);
    await chooseStation(user, 'Hayward');
    await screen.findByRole('heading', { level: 3, name: /^Hayward · / });
    const ways = within(screen.getByRole('group', { name: 'Which way are you going?' })).getAllByRole('radio');
    expect(ways.map((r) => r.closest('label')?.textContent)).toEqual([
      'Toward Berryessa/North San Jose, Platform 1',
      'Toward Daly City and Richmond, Platform 2',
    ]);
    const headsigns = () => new Set([...document.querySelectorAll('.timetable__headsign')].map((h) => h.textContent));
    await user.click(screen.getByRole('button', { name: 'Show 5 more trains' }));
    expect(headsigns()).toEqual(new Set(['Berryessa', 'Berryessa/North San Jose']));

    await user.click(ways[1] as HTMLElement);
    await screen.findByRole('heading', { level: 3, name: 'Hayward · Richmond train' });
    await user.click(screen.getByRole('button', { name: 'Show 3 more trains' }));
    expect(headsigns()).toEqual(new Set(['Richmond', 'Daly City']));
    expect(recorded.api?.requests.filter((p) => p.includes('/predictions?'))).toEqual([
      BOARD('ANTC', 'to-PCTR'),
      BOARD('HAYW', 'to-SHAY'),
      BOARD('HAYW', 'to-BAYF'),
    ]);
  });

  it('offers the next model forecast at Hayward without selecting it', async () => {
    const user = userEvent.setup();
    render(<App client={http().client} />);
    await chooseStation(user, 'Hayward');
    // The earliest train is outside the model's horizons; the next one has a forecast.
    expect(await screen.findByRole('heading', { level: 3, name: 'Hayward · Berryessa train' })).toBeInTheDocument();
    expect(checkedTrain()).toMatch(/^2026-10-15:1965544:/);
    expect(screen.getByTestId('forecast')).toHaveTextContent(/^BART’s published ETA/);
    await user.click(screen.getByRole('button', { name: 'View the next model forecast' }));
    expect(await screen.findByRole('heading', { level: 3, name: 'Hayward · Berryessa/North San Jose train' })).toBeInTheDocument();
    expect(screen.getByTestId('forecast')).toHaveTextContent(/^Likely final published ETA/);
    expect(checkedTrain()).toMatch(/^2026-10-15:1965438:/);
  });
});

describe('data provenance', () => {
  it('labels the simulated client’s data as simulated, and never as a replay', async () => {
    render(<App client={mock().client} />);
    await screen.findByTestId('forecast');
    expect(screen.getByRole('complementary', { name: 'Prototype using simulated data' })).toBeInTheDocument();
    expect(screen.getByTestId('data-details')).toHaveTextContent('Simulated. Every station reading, train and number is invented.');
    expect(screen.getByText('Simulated')).toBeInTheDocument();
    expect(screen.queryByText('Historical replay')).not.toBeInTheDocument();
    expect(screen.queryByTestId('replay-notice')).not.toBeInTheDocument();
  });

  it('labels API data as a historical replay at its as-of time, and never as live or simulated', async () => {
    const user = userEvent.setup();
    render(<App client={http().client} />);
    await OPEN_FORECAST.http(user);
    await screen.findByTestId('forecast');

    // The disclosure follows /health, a request separate from the board's.
    const opening = screen.getByRole('region', { name: 'ETA Reliability' });
    expect(await within(opening).findByRole('complementary', { name: 'Historical replay of recorded BART data' })).toHaveTextContent(
      'This page replays BART’s recorded feeds as they stood on Thursday, October 15, 2026 at 10:00 AM Pacific. ' +
        'The data is fixed at that moment: it is not live, and nothing on the page updates or counts down.',
    );
    expect(within(opening).getByRole('link', { name: 'Try a historical replay' })).toBeInTheDocument();
    // One concise reminder beside the result.
    expect(screen.getByTestId('replay-notice')).toHaveTextContent(
      'Historical replay—fixed, not live. BART data as of Thursday, October 15, 2026 at 10:00 AM Pacific.',
    );
    // The full provenance is in one labelled, expandable section.
    const details = screen.getByTestId('data-details');
    expect(details.tagName).toBe('DETAILS');
    expect(details).toHaveTextContent(
      'Historical replay of recorded BART data as of Thursday, October 15, 2026 at 10:00 AM Pacific. The data is fixed ' +
        'at that moment, and the forecast uses only what was known then. Nothing here is live.',
    );
    expect(details).toHaveTextContent('Forecast generated10:00:00 AM (the replay time)');
    expect(details).toHaveTextContent('ModelVersion 0.1.0+8d942e17429c, trained on data through Tue, Oct 13, 2026, 2:11 AM Pacific');
    // Freshness is judged at the replay time, not against today's clock.
    expect(within(details).getByText('Fresh at replay time')).toHaveClass('freshness--current');
    expect(details).toHaveTextContent(/37 s old at the replay time/);
    // Not repeated elsewhere: one banner, one reminder, one details section.
    const example = screen.getByRole('region', { name: 'Try an ETA forecast' });
    const intro = example.querySelector('.example__intro');
    expect(intro).not.toHaveTextContent(/replay|live|simulat/i);
    // Paragraphs that explain the replay (the call to action only names it).
    const replayMentions = [...document.querySelectorAll('p:not(.opening__cta), dd')].filter(
      (el) => /historical replay|replays BART/i.test(el.textContent ?? '') && !el.querySelector('p, dd'),
    );
    expect(replayMentions.map((el) => el.closest('aside, [data-testid="replay-notice"], details')?.tagName ?? el.tagName)).toEqual([
      'ASIDE', // banner label
      'ASIDE', // banner body
      'P', // the reminder itself
      'DETAILS',
    ]);

    // Past tense for a replay: BART said this in the snapshot; nothing "currently" or "right now".
    expect(screen.getByTestId('summary-said')).toHaveTextContent(/^BART said in this snapshot/);
    expect(screen.getByTestId('calc-now')).toHaveTextContent(/^BART said in this snapshot/);
    // The history is named by its snapshot time, not as "the last N minutes".
    expect(await within(history()).findByTestId('history-summary')).toHaveTextContent(
      /^In the \d+ minutes before the 9:59:23 AM snapshot, /,
    );
    expect(document.body.textContent).not.toMatch(/currently says|right now|\bCurrent\b|Over the last/);
    // Still clear that the forecast concerns BART's final published ETA, not a physical arrival.
    expect(screen.getByTestId('forecast')).toHaveTextContent('Model forecast of BART’s last published ETA, not an observed arrival.');

    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/simulat/i);
    // "live" appears only where the page says the data is not live.
    expect(text.replace(/not live|Nothing here is live/g, '')).not.toMatch(/\blive\b/i);
    expect(screen.getByText(/visible since/)).toHaveTextContent('Systemwide · planned work · visible since Oct 13, 7:56:22 PM');
  });

  it('says so when the API cannot be reached, without showing any data, and recovers when it returns', async () => {
    const user = userEvent.setup();
    const api = createFakeApi();
    let up = false;
    const client = new HttpPredictionClient(API_BASE, {
      fetch: (input, init) => (up ? api.fetch(input, init) : Promise.reject(new TypeError('Failed to fetch'))),
    });
    render(<App client={client} />);
    const disclosure = await screen.findByRole('complementary', { name: 'Data unavailable' });
    expect(await screen.findByRole('heading', { level: 3, name: 'Prediction unavailable' })).toBeInTheDocument();
    expect(screen.queryByTestId('forecast')).not.toBeInTheDocument();
    expect(screen.queryByText('Historical replay')).not.toBeInTheDocument();

    up = true;
    await user.click(within(disclosure).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('complementary', { name: 'Historical replay of recorded BART data' })).toBeInTheDocument();
    await user.click(within(screen.getByRole('region', { name: /No upcoming|Prediction unavailable/ })).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { level: 3, name: 'No upcoming trains' })).toBeInTheDocument();
  });
});
