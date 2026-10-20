import { describe, expect, it, vi } from 'vitest';
import { hasForecast } from '../domain/types';
import { API_BASE, API_RECORDING, createFakeApi } from '../test/fakeApi';
import { HttpPredictionClient } from './HttpPredictionClient';
import { PredictionClientError } from './PredictionClient';

const REPLAY_AS_OF = '2026-10-15T17:00:00Z';
const CAST_BOARD = '/api/v1/stations/CAST/predictions?boarding_group=to-BAYF';

function setup() {
  const api = createFakeApi();
  return { api, client: new HttpPredictionClient(`${API_BASE}/`, { fetch: api.fetch }) };
}

describe('HttpPredictionClient', () => {
  it('builds endpoint URLs from the configured base without a doubled slash', () => {
    const client = new HttpPredictionClient(' http://127.0.0.1:8000// ');
    expect(client.endpoint('/stations/CAST/predictions', { boarding_group: 'to-BAYF' })).toBe(
      'http://127.0.0.1:8000/api/v1/stations/CAST/predictions?boarding_group=to-BAYF',
    );
  });

  it('requests each endpoint by its documented path, with the identifiers encoded', async () => {
    const calls: { url: string; init: RequestInit | undefined }[] = [];
    const api = createFakeApi();
    const client = new HttpPredictionClient(API_BASE, {
      fetch: (input, init) => {
        calls.push({ url: String(input), init });
        return api.fetch(input, init);
      },
    });

    await client.listStations();
    await client.getPredictions('CAST', 'to-BAYF');
    await client.getPredictionHistory('2026-10-15:1965774:2');
    await client.getModelMetadata();
    await client.getHealth();

    expect(calls.map((c) => c.url)).toEqual([
      `${API_BASE}/api/v1/stations`,
      `${API_BASE}/api/v1/stations/CAST/predictions?boarding_group=to-BAYF`,
      `${API_BASE}/api/v1/predictions/2026-10-15%3A1965774%3A2/history`,
      `${API_BASE}/api/v1/model/metadata`,
      `${API_BASE}/api/v1/health`,
    ]);
    // Read-only JSON requests that never send cookies.
    for (const { init } of calls) {
      expect(init).toMatchObject({ headers: { Accept: 'application/json' }, credentials: 'omit' });
    }

    // An identifier can never escape its path segment or add query parameters.
    await expect(client.getPredictions('A/B?x=1', 'to-X&y=1')).rejects.toMatchObject({ code: 'not_found' });
    expect(calls.at(-1)?.url).toBe(`${API_BASE}/api/v1/stations/A%2FB%3Fx%3D1/predictions?boarding_group=to-X%26y%3D1`);
  });

  it('decodes the recorded replay into the shared contract, labelled as historical replay', async () => {
    const { client } = setup();

    const stations = await client.listStations();
    expect(stations.map((s) => s.id)).toEqual(['ANTC', 'CAST', 'DBRK', 'HAYW']);
    expect(stations[1]?.boardingGroups.map((g) => [g.id, g.label, g.platform])).toEqual([
      ['to-WDUB', 'Toward Dublin/Pleasanton', '1'],
      ['to-BAYF', 'Toward Bay Fair and Daly City', '2'],
    ]);
    expect(stations.map((s) => s.endOfLine)).toEqual([true, false, false, false]);

    const response = await client.getPredictions('CAST', 'to-BAYF');
    expect(response).toMatchObject({
      dataProvenance: 'historical_replay',
      replay: { asOf: REPLAY_AS_OF },
      stationId: 'CAST',
      boardingGroupId: 'to-BAYF',
      feedTimestamp: '2026-10-15T16:59:23Z',
      generatedAt: REPLAY_AS_OF,
      model: { modelVersion: '0.1.0+8d942e17429c', simulated: false, revisionThresholdSeconds: 60 },
    });
    expect(response.alerts[0]).toMatchObject({ scope: 'system', category: 'planned_work' });
    expect(response.unplacedTrainCount).toBe(0);
    expect(response.terminatingTrainCount).toBe(0);
    await expect(client.getPredictions('ANTC', 'to-PCTR')).resolves.toMatchObject({ trains: [], unplacedTrainCount: 5 });

    const [first, ...rest] = response.trains;
    expect(first && hasForecast(first)).toBe(true);
    expect(first).toMatchObject({
      predictionId: '2026-10-15:1965774:2',
      currentEtaSeconds: 342,
      platform: '2',
      predictedRevisionSeconds: 0,
      revisionInterval: { lowerSeconds: -18, upperSeconds: 24, level: 0.8 },
      stability: 'likely_to_hold',
    });
    // Unsupported trains keep BART's ETA and carry no model numbers at all.
    expect(rest.length).toBeGreaterThan(0);
    for (const train of rest) {
      expect(train).toMatchObject({
        predictionStatus: 'outside_model_horizon',
        predictedRevisionSeconds: null,
        revisionInterval: null,
        revisionProbability: null,
        stability: null,
      });
    }

    const history = await client.getPredictionHistory('2026-10-15:1965774:2');
    expect(history.length).toBeGreaterThan(1);
    expect(history.at(-1)?.feedTimestamp).toBe('2026-10-15T16:59:23Z');

    await expect(client.getHealth()).resolves.toMatchObject({
      status: 'ok',
      dataProvenance: 'historical_replay',
      replay: { asOf: REPLAY_AS_OF },
    });
    await expect(client.getModelMetadata()).resolves.toMatchObject({ simulated: false });
  });

  it('decodes every recorded response', async () => {
    const { client } = setup();
    for (const path of Object.keys(API_RECORDING.responses)) {
      const predictions = /^\/api\/v1\/stations\/(\w+)\/predictions\?boarding_group=([\w-]+)$/.exec(path);
      const history = /^\/api\/v1\/predictions\/(.+)\/history$/.exec(path);
      if (predictions) await expect(client.getPredictions(predictions[1] ?? '', predictions[2] ?? '')).resolves.toBeTruthy();
      else if (history) await expect(client.getPredictionHistory(history[1] ?? '')).resolves.toBeInstanceOf(Array);
    }
  });

  it('uses the API’s own error code and message', async () => {
    const { api, client } = setup();
    api.respond('/api/v1/stations/NOPE/predictions?boarding_group=to-X', {
      status: 404,
      body: { error: { code: 'station_not_found', clientCode: 'not_found', message: 'Unknown station NOPE.' } },
    });
    api.respond('/api/v1/health', {
      status: 503,
      body: { error: { code: 'feed_stale', clientCode: 'unavailable', message: 'The warehouse does not cover as_of.' } },
    });

    await expect(client.getPredictions('NOPE', 'to-X')).rejects.toMatchObject({
      code: 'not_found',
      message: 'Unknown station NOPE.',
    });
    await expect(client.getHealth()).rejects.toMatchObject({
      code: 'unavailable',
      message: 'The warehouse does not cover as_of.',
    });
  });

  it('falls back on the HTTP status when the error body is not the API’s', async () => {
    const { api, client } = setup();
    api.respond('/api/v1/stations', { status: 502, body: '<html>Bad gateway</html>' });
    api.respond('/api/v1/model/metadata', { status: 404, body: null });
    await expect(client.listStations()).rejects.toMatchObject({ code: 'unavailable', message: 'The API returned HTTP 502.' });
    await expect(client.getModelMetadata()).rejects.toMatchObject({ code: 'not_found' });
  });

  it('reports an unreachable API as unavailable', async () => {
    const client = new HttpPredictionClient(API_BASE, { fetch: () => Promise.reject(new TypeError('Failed to fetch')) });
    const error = await client.listStations().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(PredictionClientError);
    expect(error).toMatchObject({ code: 'unavailable', message: `The prediction API at ${API_BASE} could not be reached.` });
  });

  it('refuses to request anything without a configured address', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>();
    const client = new HttpPredictionClient('', { fetch });
    await expect(client.listStations()).rejects.toMatchObject({
      code: 'unavailable',
      message: 'No API address is configured. Set VITE_API_BASE_URL.',
    });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('rejects responses that do not match the contract', async () => {
    const { api, client } = setup();
    const board = API_RECORDING.responses[CAST_BOARD] as Record<string, unknown>;
    const [okTrain, etaOnly] = board.trains as Record<string, unknown>[];
    const interval = (okTrain?.revisionInterval ?? {}) as Record<string, unknown>;
    const withTrain = (changes: Record<string, unknown>) => ({ ...board, trains: [{ ...okTrain, ...changes }] });

    const cases: [string, unknown, RegExp][] = [
      ['not JSON', undefined, /expected an object/],
      ['an unlabelled mode', { ...board, dataMode: 'live' }, /unrecognised data mode "live"/],
      ['no data mode', { ...board, dataMode: undefined }, /unrecognised data mode/],
      ['a probability above 1', { ...board, trains: [{ ...okTrain, revisionProbability: 1.2 }] }, /outside 0 to 1/],
      ['an inverted range', { ...board, trains: [{ ...okTrain, revisionInterval: { lowerSeconds: 30, upperSeconds: -30, level: 0.8 } }] }, /lower bound above upper bound/],
      ['model numbers on an unsupported train', { ...board, trains: [{ ...etaOnly, revisionProbability: 0.3 }] }, /must be null/],
      ['an unknown status', { ...board, trains: [{ ...okTrain, predictionStatus: 'guessed' }] }, /expected one of ok/],
      ['a negative unplaced count', { ...board, unplacedTrainCount: -1 }, /unplacedTrainCount: expected a whole number/],
      ['a fractional unplaced count', { ...board, unplacedTrainCount: 1.5 }, /unplacedTrainCount: expected a whole number/],
      ['no terminating count', { ...board, terminatingTrainCount: undefined }, /terminatingTrainCount: expected a finite number/],
      ['no boarding group', { ...board, boardingGroupId: undefined }, /boardingGroupId: expected a string/],
      // Interval coverage is a fraction above 0 and at most 1.
      ['a zero interval level', withTrain({ revisionInterval: { ...interval, level: 0 } }), /level: expected a fraction above 0/],
      ['a negative interval level', withTrain({ revisionInterval: { ...interval, level: -0.8 } }), /level: expected a fraction/],
      ['a percentage as the level', withTrain({ revisionInterval: { ...interval, level: 80 } }), /level: expected a fraction/],
      // An upcoming-train board never lists a train in the past.
      ['a negative ETA', withTrain({ currentEtaSeconds: -5 }), /currentEtaSeconds: expected a number of at least 0/],
      ['a fractional car count', withTrain({ carCount: 8.5 }), /carCount: expected a whole number/],
      ['a negative car count', withTrain({ carCount: -2 }), /carCount: expected a whole number/],
      ['a car count as text', withTrain({ carCount: '8' }), /carCount: expected a finite number/],
      // A time without a zone would be read in the visitor's own time zone.
      ['an ETA without a time zone', withTrain({ currentEtaAt: '2026-10-15T17:05:04' }), /currentEtaAt: expected an ISO 8601 timestamp with a time zone/],
      ['a snapshot without a time zone', { ...board, feedTimestamp: '2026-10-15T16:59:23' }, /feedTimestamp: expected an ISO 8601 timestamp with a time zone/],
      ['a date only', { ...board, generatedAt: '2026-10-15' }, /generatedAt: expected an ISO 8601 timestamp/],
      ['a platform number', withTrain({ platform: 2 }), /platform: expected a string/],
      ['a train listed twice', { ...board, trains: [okTrain, okTrain] }, /duplicate prediction "2026-10-15:1965774:2"/],
    ];
    for (const [label, body, message] of cases) {
      api.respond(CAST_BOARD, () =>
        Promise.resolve(new Response(body === undefined ? 'not json' : JSON.stringify(body), { status: 200 })),
      );
      const error = await client.getPredictions('CAST', 'to-BAYF').catch((e: unknown) => e);
      expect(error, label).toBeInstanceOf(PredictionClientError);
      expect((error as PredictionClientError).code, label).toBe('unavailable');
      expect((error as Error).message, label).toMatch(/^The API sent an unexpected response/);
      expect((error as Error).message, label).toMatch(message);
    }
  });

  it('accepts a full-coverage level and a zoned offset other than Z', async () => {
    const { api, client } = setup();
    const board = structuredClone(API_RECORDING.responses[CAST_BOARD]) as { trains: Record<string, unknown>[] };
    const [first] = board.trains;
    if (!first) throw new Error('fixture changed');
    first.revisionInterval = { lowerSeconds: -18, upperSeconds: 24, level: 1 };
    first.currentEtaAt = '2026-10-15T10:05:04-07:00';
    api.respond(CAST_BOARD, { body: board });
    await expect(client.getPredictions('CAST', 'to-BAYF')).resolves.toBeTruthy();
  });

  it('rejects station lists with duplicate or malformed entries', async () => {
    const { api, client } = setup();
    const stations = API_RECORDING.responses['/api/v1/stations'] as Record<string, unknown>[];
    const [antioch, castro] = stations as [Record<string, unknown>, Record<string, unknown>];
    const groups = castro.boardingGroups as Record<string, unknown>[];
    const cases: [string, unknown, RegExp][] = [
      ['a station listed twice', [antioch, castro, antioch], /stations: duplicate station "ANTC"/],
      ['a boarding group listed twice', [{ ...castro, boardingGroups: [groups[0], groups[0]] }], /duplicate boarding group "to-WDUB"/],
      ['the old directions field', [{ ...castro, boardingGroups: undefined, directions: [] }], /boardingGroups: expected an array/],
      ['no end-of-line flag', [{ ...castro, endOfLine: undefined }], /endOfLine: expected a boolean/],
      ['a numeric platform', [{ ...castro, boardingGroups: [{ ...groups[0], platform: 1 }] }], /platform: expected a string/],
    ];
    for (const [label, body, message] of cases) {
      api.respond('/api/v1/stations', { body });
      const error = await client.listStations().catch((e: unknown) => e);
      expect(error, label).toBeInstanceOf(PredictionClientError);
      expect((error as Error).message, label).toMatch(message);
    }
  });

  it('rejects a history with a repeated snapshot or a time without a zone', async () => {
    const { api, client } = setup();
    const path = '/api/v1/predictions/2026-10-15:1965774:2/history';
    const history = API_RECORDING.responses[path] as Record<string, unknown>[];
    const cases: [string, unknown, RegExp][] = [
      ['a repeated snapshot', [...history, history.at(-1)], /history: duplicate snapshot/],
      ['a snapshot without a zone', [{ ...history[0], feedTimestamp: '2026-10-15T16:00:00' }], /feedTimestamp: expected an ISO 8601 timestamp with a time zone/],
    ];
    for (const [label, body, message] of cases) {
      api.respond(path, { body });
      const error = await client.getPredictionHistory('2026-10-15:1965774:2').catch((e: unknown) => e);
      expect(error, label).toBeInstanceOf(PredictionClientError);
      expect((error as Error).message, label).toMatch(message);
    }
  });

  it('rejects an answer for a different station or boarding group', async () => {
    const { api, client } = setup();
    api.respond('/api/v1/stations/CAST/predictions?boarding_group=to-WDUB', {
      body: API_RECORDING.responses[CAST_BOARD],
    });
    await expect(client.getPredictions('CAST', 'to-WDUB')).rejects.toMatchObject({
      code: 'unavailable',
      message: 'The API answered for a different station or boarding group.',
    });
  });

  it('lets an aborted request reject as an abort, not as an API failure', async () => {
    const { api, client } = setup();
    let release: () => void = () => undefined;
    api.respond('/api/v1/stations', (init) => {
      return new Promise((_, reject) => {
        release = () => reject(new DOMException('The operation was aborted.', 'AbortError'));
        init?.signal?.addEventListener('abort', () => release());
      });
    });
    const controller = new AbortController();
    const pending = client.listStations(controller.signal);
    controller.abort();
    const error = await pending.catch((e: unknown) => e);
    expect(error).not.toBeInstanceOf(PredictionClientError);
    expect(error).toMatchObject({ name: 'AbortError' });
  });
});
