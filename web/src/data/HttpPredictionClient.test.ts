import { describe, expect, it, vi } from 'vitest';
import { hasForecast } from '../domain/types';
import { API_BASE, API_RECORDING, createFakeApi } from '../test/fakeApi';
import { HttpPredictionClient } from './HttpPredictionClient';
import { PredictionClientError } from './PredictionClient';

const REPLAY_AS_OF = '2026-10-15T17:00:00Z';

function setup() {
  const api = createFakeApi();
  return { api, client: new HttpPredictionClient(`${API_BASE}/`, { fetch: api.fetch }) };
}

describe('HttpPredictionClient', () => {
  it('builds endpoint URLs from the configured base without a doubled slash', () => {
    const client = new HttpPredictionClient(' http://127.0.0.1:8000// ');
    expect(client.endpoint('/stations/CAST/predictions', { direction_id: '1' })).toBe(
      'http://127.0.0.1:8000/api/v1/stations/CAST/predictions?direction_id=1',
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
    await client.getPredictions('CAST', '1');
    await client.getPredictionHistory('2026-10-15:1965774:2');
    await client.getModelMetadata();
    await client.getHealth();

    expect(calls.map((c) => c.url)).toEqual([
      `${API_BASE}/api/v1/stations`,
      `${API_BASE}/api/v1/stations/CAST/predictions?direction_id=1`,
      `${API_BASE}/api/v1/predictions/2026-10-15%3A1965774%3A2/history`,
      `${API_BASE}/api/v1/model/metadata`,
      `${API_BASE}/api/v1/health`,
    ]);
    // Read-only JSON requests that never send cookies.
    for (const { init } of calls) {
      expect(init).toMatchObject({ headers: { Accept: 'application/json' }, credentials: 'omit' });
    }

    // An identifier can never escape its path segment or add query parameters.
    await expect(client.getPredictions('A/B?x=1', '0')).rejects.toMatchObject({ code: 'not_found' });
    expect(calls.at(-1)?.url).toBe(`${API_BASE}/api/v1/stations/A%2FB%3Fx%3D1/predictions?direction_id=0`);
  });

  it('decodes the recorded replay into the shared contract, labelled as historical replay', async () => {
    const { client } = setup();

    const stations = await client.listStations();
    expect(stations.map((s) => s.id)).toEqual(['ANTC', 'CAST', 'DBRK']);
    expect(stations[1]?.directions.map((d) => d.label)).toEqual(['Toward Dublin/Pleasanton', 'Toward Bay Fair and Daly City']);

    const response = await client.getPredictions('CAST', '1');
    expect(response).toMatchObject({
      dataProvenance: 'historical_replay',
      replay: { asOf: REPLAY_AS_OF },
      stationId: 'CAST',
      directionId: '1',
      feedTimestamp: '2026-10-15T16:59:23Z',
      generatedAt: REPLAY_AS_OF,
      model: { modelVersion: '0.1.0+8d942e17429c', simulated: false, revisionThresholdSeconds: 60 },
    });
    expect(response.alerts[0]).toMatchObject({ scope: 'system', category: 'planned_work' });
    expect(response.unplacedTrainCount).toBe(0);
    await expect(client.getPredictions('ANTC', '0')).resolves.toMatchObject({ trains: [], unplacedTrainCount: 5 });

    const [first, ...rest] = response.trains;
    expect(first && hasForecast(first)).toBe(true);
    expect(first).toMatchObject({
      predictionId: '2026-10-15:1965774:2',
      currentEtaSeconds: 342,
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
      const predictions = /^\/api\/v1\/stations\/(\w+)\/predictions\?direction_id=(\d)$/.exec(path);
      const history = /^\/api\/v1\/predictions\/(.+)\/history$/.exec(path);
      if (predictions) await expect(client.getPredictions(predictions[1] ?? '', predictions[2] ?? '')).resolves.toBeTruthy();
      else if (history) await expect(client.getPredictionHistory(history[1] ?? '')).resolves.toBeInstanceOf(Array);
    }
  });

  it('uses the API’s own error code and message', async () => {
    const { api, client } = setup();
    api.respond('/api/v1/stations/NOPE/predictions?direction_id=0', {
      status: 404,
      body: { error: { code: 'station_not_found', clientCode: 'not_found', message: 'Unknown station NOPE.' } },
    });
    api.respond('/api/v1/health', {
      status: 503,
      body: { error: { code: 'feed_stale', clientCode: 'unavailable', message: 'The warehouse does not cover as_of.' } },
    });

    await expect(client.getPredictions('NOPE', '0')).rejects.toMatchObject({
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
    const board = API_RECORDING.responses['/api/v1/stations/CAST/predictions?direction_id=1'] as Record<string, unknown>;
    const [okTrain, etaOnly] = board.trains as Record<string, unknown>[];

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
    ];
    for (const [label, body, message] of cases) {
      api.respond('/api/v1/stations/CAST/predictions?direction_id=1', () =>
        Promise.resolve(new Response(body === undefined ? 'not json' : JSON.stringify(body), { status: 200 })),
      );
      const error = await client.getPredictions('CAST', '1').catch((e: unknown) => e);
      expect(error, label).toBeInstanceOf(PredictionClientError);
      expect((error as PredictionClientError).code, label).toBe('unavailable');
      expect((error as Error).message, label).toMatch(/^The API sent an unexpected response/);
      expect((error as Error).message, label).toMatch(message);
    }
  });

  it('rejects an answer for a different station or direction', async () => {
    const { api, client } = setup();
    api.respond('/api/v1/stations/CAST/predictions?direction_id=0', {
      body: API_RECORDING.responses['/api/v1/stations/CAST/predictions?direction_id=1'],
    });
    await expect(client.getPredictions('CAST', '0')).rejects.toMatchObject({
      code: 'unavailable',
      message: 'The API answered for a different station or direction.',
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
