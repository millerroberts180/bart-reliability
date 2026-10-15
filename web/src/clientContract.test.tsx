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
    getPredictions: (stationId, directionId, signal) => (
      calls.push(`getPredictions ${stationId} ${directionId}`), client.getPredictions(stationId, directionId, signal)
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

const BOARD = (station: string, direction: string) => `/api/v1/stations/${station}/predictions?direction_id=${direction}`;
const recordedBoard = (station: string, direction: string) =>
  structuredClone(API_RECORDING.responses[BOARD(station, direction)]) as { feedTimestamp: string; trains: Record<string, unknown>[] };

const readoutHeading = () => screen.findByRole('heading', { level: 3, name: /·|Prediction|No upcoming|Loading/ });
const history = () => screen.getByRole('region', { name: 'How this ETA has changed' });
const trainGroup = () => screen.getByRole('group', { name: 'Upcoming trains' });
const checkedTrain = () => within(trainGroup()).getAllByRole<HTMLInputElement>('radio').find((r) => r.checked)?.value;

/** How to reach a train with a forecast and its range from a fresh page. */
const OPEN_FORECAST: Record<ClientName, (user: UserEvent) => Promise<void>> = {
  mock: async () => undefined,
  http: async (user) => {
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Station' }), 'Castro Valley');
    await user.click(screen.getByRole('radio', { name: 'Toward Bay Fair and Daly City' }));
  },
};

/** The trains in the recorded Castro Valley board toward Dublin/Pleasanton are all outside the model horizon. */
const OPEN_ETA_ONLY: Record<ClientName, (user: UserEvent) => Promise<void>> = {
  mock: async () => undefined,
  http: async (user) => {
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Station' }), 'Castro Valley');
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
    check: async () => {
      const forecast = await screen.findByTestId('forecast');
      expect(forecast).toHaveTextContent(/^Likely final published ETA.*80% likely range: /);
      expect(screen.getByTestId('calc-adjust')).toHaveTextContent(/^\+?Expected adjustment/);
      expect(screen.getByTestId('calc-final')).toBeInTheDocument();
      expect(screen.getByText(/chance BART changes this estimate by more than 60 seconds/)).toBeInTheDocument();
      const key = await within(history()).findByRole('list', { name: 'Chart key' });
      expect(key).toHaveTextContent(/Model’s likely final published ETA .*, with its 80% range at the right/);
    },
  },
  {
    state: 'a forecast without a likely range',
    setup: {
      mock: () => mock('no-interval'),
      http: () =>
        http((api) => {
          const board = recordedBoard('CAST', '1');
          for (const t of board.trains) if (t.predictionStatus === 'ok') t.revisionInterval = null;
          api.respond(BOARD('CAST', '1'), { body: board });
        }),
    },
    open: OPEN_FORECAST,
    check: async () => {
      expect(await screen.findByTestId('no-range')).toHaveTextContent(
        'No likely range is shown: the model’s range isn’t supported for this data.',
      );
      expect(screen.getByTestId('forecast')).not.toHaveTextContent(/likely range:/);
      expect(screen.getByText('Adjustment range').parentElement).toHaveTextContent('Not available for this forecast.');
      const key = await within(history()).findByRole('list', { name: 'Chart key' });
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
        'No model forecast right now. The model only forecasts trains BART shows about 5, 10 or 15 minutes away.',
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
    // The recorded replay has no trains at Antioch, the first station, in either direction.
    setup: { mock: () => mock('empty'), http: () => http() },
    check: async () => {
      expect(await screen.findByRole('heading', { level: 3, name: 'No upcoming trains' })).toBeInTheDocument();
      expect(screen.getByText('No trains listed in this snapshot.')).toBeInTheDocument();
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
          const board = recordedBoard('CAST', '1');
          board.feedTimestamp = '2026-10-15T16:50:20Z';
          api.respond(BOARD('CAST', '1'), { body: board });
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
          getPredictions: (s, d, signal) =>
            failures-- > 0 ? Promise.reject(new Error('offline')) : inner.getPredictions(s, d, signal),
        };
        return recorded;
      },
      http: () =>
        http((api) => {
          let failures = 1;
          api.respond(BOARD('ANTC', '0'), () =>
            Promise.resolve(
              failures-- > 0
                ? Response.json({ error: { code: 'feed_unavailable', clientCode: 'unavailable', message: 'x' } }, { status: 503 })
                : Response.json(API_RECORDING.responses[BOARD('ANTC', '0')]),
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
    direction: { label: string; request: string; heading: string };
    train: { radio: RegExp; heading: string };
  }
> = {
  mock: {
    first: { request: 'getPredictions EMBR 0', heading: 'Embarcadero · Antioch train' },
    station: { name: 'MacArthur', request: 'getPredictions MCAR 0', heading: 'MacArthur · Richmond train' },
    direction: { label: 'Toward San Francisco and Berryessa', request: 'getPredictions MCAR 1', heading: 'MacArthur · SF Airport train' },
    train: { radio: /Millbrae/, heading: 'MacArthur · Millbrae train' },
  },
  http: {
    first: { request: 'getPredictions ANTC 0', heading: 'No upcoming trains' },
    station: { name: 'Downtown Berkeley', request: 'getPredictions DBRK 0', heading: 'Downtown Berkeley · Richmond train' },
    direction: {
      label: 'Toward Berryessa/North San Jose and Millbrae',
      request: 'getPredictions DBRK 1',
      heading: 'Downtown Berkeley · Millbrae train',
    },
    train: { radio: /Berryessa/, heading: 'Downtown Berkeley · Berryessa/North San Jose train' },
  },
};

describe.each(['mock', 'http'] as const)('selection with the %s client', (name) => {
  it('requests the chosen station, direction and train, and moves the forecast and history together', async () => {
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

    await user.selectOptions(screen.getByRole('combobox', { name: 'Station' }), journey.station.name);
    await expectInStep(journey.station.heading, journey.station.request);

    await user.click(screen.getByRole('radio', { name: journey.direction.label }));
    await expectInStep(journey.direction.heading, journey.direction.request);

    const [nextTrain] = within(trainGroup()).getAllByRole('radio', { name: journey.train.radio });
    await user.click(nextTrain as HTMLElement);
    // Choosing a train re-reads nothing but that train's history.
    const boards = recorded.calls.filter((c) => c.startsWith('getPredictions')).length;
    await expectInStep(journey.train.heading, journey.direction.request);
    expect(recorded.calls.filter((c) => c.startsWith('getPredictions'))).toHaveLength(boards);

    if (recorded.api) {
      // What actually went over the wire, in order (repeats removed), with the encoded history ids decoded.
      const paths = recorded.api.requests.filter((p, i, all) => all.indexOf(p) === i);
      expect(paths).toEqual([
        '/api/v1/health',
        '/api/v1/stations',
        BOARD('ANTC', '0'),
        BOARD('DBRK', '0'),
        expect.stringMatching(/^\/api\/v1\/predictions\/2026-10-15:\d+:\d+\/history$/),
        BOARD('DBRK', '1'),
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
  const withUnplaced = (api: FakeApi, direction: string, unplacedTrainCount: number) =>
    api.respond(BOARD('ANTC', direction), { body: { ...recordedBoard('ANTC', direction), unplacedTrainCount } });

  it('gives the general reasons when nothing more is known (simulated)', async () => {
    render(<App client={mock('empty').client} />);
    expect(await emptyText()).toBe(
      'The latest snapshot lists no trains toward the East Bay from Embarcadero. Service may have ended for the night, ' +
        'this direction may not be running right now, or BART’s feed may not include it.',
    );
  });

  it('says when trains in the chosen direction end here, and counts trains without a direction', async () => {
    // Recorded replay: Antioch lists 5 unmatched trains; trains toward Antioch end there.
    render(<App client={http().client} />);
    expect(await emptyText()).toBe(
      'The latest snapshot lists no trains toward Antioch from Antioch. Trains toward Antioch end their trips here, ' +
        'and BART’s feed almost never lists a train at the last stop of its trip. BART’s feed does list 5 trains at ' +
        'Antioch that match no scheduled trip, so their direction isn’t known and they aren’t shown.',
    );
  });

  it('counts trains without a direction on the other board too', async () => {
    const user = userEvent.setup();
    render(<App client={http().client} />);
    await emptyText();
    await user.click(screen.getByRole('radio', { name: /^Toward Millbrae/ }));
    await screen.findByText(/^The latest snapshot lists no trains toward Millbrae/);
    expect(await emptyText()).toMatch(
      /from Antioch\. BART’s feed does list 5 trains at Antioch that match no scheduled trip, so their direction isn’t known and they aren’t shown\.$/,
    );
  });

  it('uses the singular for one train and falls back to the general reasons with none', async () => {
    const user = userEvent.setup();
    render(
      <App
        client={
          http((api) => {
            withUnplaced(api, '0', 1);
            withUnplaced(api, '1', 0);
          }).client
        }
      />,
    );
    expect(await emptyText()).toMatch(
      /BART’s feed does list 1 train at Antioch that matches no scheduled trip, so its direction isn’t known and it isn’t shown\.$/,
    );
    await user.click(screen.getByRole('radio', { name: /^Toward Millbrae/ }));
    await screen.findByText(/^The latest snapshot lists no trains toward Millbrae/);
    expect(await emptyText()).toMatch(/from Antioch\. Service may have ended for the night, .*may not include it\.$/);
  });

  it('matches a station to a destination despite different spacing', async () => {
    const stations = structuredClone(API_RECORDING.responses['/api/v1/stations']) as {
      name: string;
      directions: { destinations: string[] }[];
    }[];
    const [antioch] = stations;
    if (!antioch?.directions[0]) throw new Error('fixture changed');
    antioch.name = 'Dublin / Pleasanton';
    antioch.directions[0].destinations = ['Dublin/Pleasanton'];
    render(
      <App
        client={
          http((api) => {
            api.respond('/api/v1/stations', { body: stations });
            withUnplaced(api, '0', 0);
          }).client
        }
      />,
    );
    expect(await emptyText()).toMatch(/Trains toward Dublin \/ Pleasanton end their trips here, .* last stop of its trip\.$/);
  });
});

describe('data provenance', () => {
  it('labels the simulated client’s data as simulated, and never as a replay', async () => {
    render(<App client={mock().client} />);
    await screen.findByTestId('forecast');
    expect(screen.getByRole('complementary', { name: 'Prototype using simulated data' })).toBeInTheDocument();
    expect(screen.getByText(/All values are simulated\./)).toBeInTheDocument();
    expect(screen.getByText('Simulated')).toBeInTheDocument();
    expect(screen.queryByText('Historical replay')).not.toBeInTheDocument();
    expect(screen.queryByTestId('replay-notice')).not.toBeInTheDocument();
  });

  it('labels API data as a historical replay at its as-of time, and never as live or simulated', async () => {
    const user = userEvent.setup();
    render(<App client={http().client} />);
    await OPEN_FORECAST.http(user);
    await screen.findByTestId('forecast');

    const opening = screen.getByRole('region', { name: 'ETA Reliability' });
    expect(within(opening).getByRole('complementary', { name: 'Historical replay of recorded BART data' })).toHaveTextContent(
      'This page replays BART’s recorded feeds as they stood at Thu, Oct 15, 2026, 10:00 AM Pacific.',
    );
    expect(within(opening).getByRole('link', { name: 'Try a historical replay' })).toBeInTheDocument();
    expect(screen.getByText('Historical replay')).toHaveClass('replay-tag');
    expect(screen.getByTestId('replay-notice')).toHaveTextContent(
      'Historical replay, not live. Recorded BART data as of Thu, Oct 15, 2026, 10:00 AM Pacific.',
    );
    expect(screen.getByText(/Values are a historical replay of recorded BART data as of Thu, Oct 15, 2026, 10:00 AM, not live\./));
    expect(screen.getByText(/0\.1\.0\+8d942e17429c/)).toHaveTextContent('10:00:00 AM (replay time) · 0.1.0+8d942e17429c');
    // Freshness is judged at the replay time, not against today's clock.
    expect(screen.getByText('Current')).toBeInTheDocument();
    expect(screen.getByText(/37 s old at the replay time/)).toBeInTheDocument();

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
    const disclosure = await screen.findByRole('complementary', { name: 'Prediction API unavailable' });
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
