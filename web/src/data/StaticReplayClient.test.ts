import { describe, expect, it, vi } from 'vitest';
import { hasForecast, type PredictionResponse, type TrainPrediction } from '../domain/types';
import { createPublishedReplayHost, PUBLISHED_ROOT, publishedFiles } from '../test/publishedReplay';
import { createPredictionClient, resolveDataMode } from './createPredictionClient';
import { PredictionClientError } from './PredictionClient';
import { historyFile, STATIC_REPLAY_SCHEMA, StaticReplayClient } from './StaticReplayClient';

const AS_OF = '2026-10-20T17:00:00Z';
const EXPORT = 'v1-20261020T170000Z';

function setup() {
  const host = createPublishedReplayHost();
  return { host, client: new StaticReplayClient(PUBLISHED_ROOT, { fetch: host.fetch }) };
}

async function rejection(promise: Promise<unknown>): Promise<unknown> {
  return promise.then(
    () => {
      throw new Error('expected a rejection');
    },
    (error: unknown) => error,
  );
}

async function expectClientError(promise: Promise<unknown>, code: PredictionClientError['code']) {
  const error = await rejection(promise);
  expect(error).toBeInstanceOf(PredictionClientError);
  expect((error as PredictionClientError).code).toBe(code);
}

describe('StaticReplayClient', () => {
  it('is selected by VITE_DATA_MODE=static, at the replay under the base path', () => {
    expect(resolveDataMode('static')).toBe('static');
    expect(resolveDataMode('http')).toBe('http');
    expect(resolveDataMode(undefined)).toBe('mock');
    expect(resolveDataMode('live')).toBe('mock');
    const client = createPredictionClient({ mode: 'static', staticReplayRoot: '/bart-reliability/replay/' });
    expect(client).toBeInstanceOf(StaticReplayClient);
    expect((client as StaticReplayClient).root).toBe('/bart-reliability/replay/');
    expect(client.source).toBe('api');
  });

  it('reads the index once, then one same-origin file per request, under the base path', async () => {
    const host = createPublishedReplayHost();
    const calls: { url: string; init: RequestInit | undefined }[] = [];
    const client = new StaticReplayClient('/bart-reliability/replay', {
      fetch: (input, init) => (calls.push({ url: String(input), init }), host.fetch(input, init)),
    });

    await client.getHealth();
    await client.listStations();
    await client.getPredictions('MONT', 'to-EMBR');
    await client.getPredictionHistory('2026-10-20:1965254:11');
    await client.getModelMetadata();

    const base = `/bart-reliability/replay/${EXPORT}`;
    expect(calls.map((c) => c.url)).toEqual([
      '/bart-reliability/replay/index.json',
      `${base}/health.json`,
      `${base}/stations.json`,
      `${base}/boards/MONT/to-EMBR.json`,
      `${base}/history/2026-10-20_1965254_11.json`,
      `${base}/model.json`,
    ]);
    // Paths only: the page's own origin, with no host, port or API address.
    for (const { url, init } of calls) {
      expect(url).toMatch(/^\/bart-reliability\/replay\//);
      expect(init).toMatchObject({ headers: { Accept: 'application/json' }, credentials: 'omit' });
    }
  });

  it('decodes every published station, board and history, labelled as the October 20 replay', async () => {
    const { client, host } = setup();
    const health = await client.getHealth();
    expect(health).toMatchObject({ status: 'ok', dataProvenance: 'historical_replay', replay: { asOf: AS_OF } });
    expect(await client.getModelMetadata()).toEqual({
      modelVersion: '0.2.0+886fcd260732',
      trainedThrough: '2026-10-16T08:55:23Z',
      revisionThresholdSeconds: 60,
      simulated: false,
    });

    const stations = await client.listStations();
    expect(stations).toHaveLength(50);
    const boards: PredictionResponse[] = [];
    for (const station of stations) {
      for (const group of station.boardingGroups) {
        boards.push(await client.getPredictions(station.id, group.id));
      }
    }
    expect(boards).toHaveLength(95);
    expect(boards.every((b) => b.replay?.asOf === AS_OF && b.feedTimestamp === '2026-10-20T16:59:23Z')).toBe(true);
    expect(boards.every((b) => b.model.modelVersion === '0.2.0+886fcd260732' && !b.model.simulated)).toBe(true);

    const trains = boards.flatMap((b) => b.trains);
    const byStatus: Record<string, number> = {};
    for (const t of trains) byStatus[t.predictionStatus] = (byStatus[t.predictionStatus] ?? 0) + 1;
    expect(byStatus).toEqual({ ok: 79, outside_model_horizon: 949, outside_model_population: 27, fallback_required: 2 });
    expect(trains.filter(hasForecast).every((t) => t.revisionInterval !== null)).toBe(true);

    let points = 0;
    for (const train of trains) points += (await client.getPredictionHistory(train.predictionId)).length;
    expect(points).toBe(47_939);
    // Every published file was read exactly once, plus the index; nothing else.
    expect(host.requests).toHaveLength(1 + 1 + 1 + 1 + 95 + 1057);
    expect(new Set(host.requests).size).toBe(host.requests.length);
    expect(publishedFiles()).toHaveLength(1157);
  });

  it('serves each kind of train the page distinguishes', async () => {
    const { client } = setup();
    const board = (station: string, group: string) => client.getPredictions(station, group);
    const find = (b: PredictionResponse, id: string): TrainPrediction => {
      const train = b.trains.find((t) => t.predictionId === id);
      if (!train) throw new Error(`no train ${id}`);
      return train;
    };

    const forecast = find(await board('12TH', 'to-LAKE-WOAK'), '2026-10-20:1965177:12');
    expect(forecast.predictionStatus).toBe('ok');
    expect(hasForecast(forecast) && forecast.revisionInterval?.level).toBe(0.8);

    const horizon = find(await board('12TH', 'to-19TH'), '2026-10-20:1965678:16');
    expect(horizon).toMatchObject({ predictionStatus: 'outside_model_horizon', predictedRevisionSeconds: null });
    expect(horizon.statusReason).toMatch(/models serve only published-time horizons of 5, 10 and 15 minutes/);

    const origin = find(await board('BERY', 'to-MLPT'), '2026-10-20:1965501:0');
    expect(origin).toMatchObject({
      predictionStatus: 'outside_model_population',
      statusReason: 'trip origin: a departure, not an approach',
    });

    // The two trains at platforms the models never saw: BART's ETA only.
    for (const [station, group, id] of [
      ['PITT', 'to-PCTR', '2026-10-20:1965252:25'],
      ['WDUB', 'to-DUBL', '2026-10-20:1965828:16'],
    ] as const) {
      expect(find(await board(station, group), id)).toMatchObject({
        predictionStatus: 'fallback_required',
        statusReason: 'input outside demonstrated model support',
        predictedRevisionSeconds: null,
        revisionInterval: null,
        revisionProbability: null,
        stability: null,
      });
    }

    // Empty boards carry what the page explains them with.
    const empty = {
      'ANTC to-PCTR': { unplaced: 5, terminating: 0 },
      'COLS to-OAKL': { unplaced: 0, terminating: 0 },
      'OAKL to-COLS': { unplaced: 0, terminating: 0 },
      'PCTR to-ANTC': { unplaced: 9, terminating: 0 },
      'PCTR to-PITT': { unplaced: 9, terminating: 0 },
    };
    for (const [key, expected] of Object.entries(empty)) {
      const [station = '', group = ''] = key.split(' ');
      const b = await board(station, group);
      expect(b.trains).toEqual([]);
      expect({ unplaced: b.unplacedTrainCount, terminating: b.terminatingTrainCount }).toEqual(expected);
    }
  });

  it('answers not_found for a missing file, and for IDs the exporter never writes without asking', async () => {
    const { client, host } = setup();
    await expectClientError(client.getPredictions('MONT', 'to-NOWHERE'), 'not_found');
    await expectClientError(client.getPredictionHistory('2026-10-20:1:1'), 'not_found');
    const before = host.requests.length;
    for (const [station, group] of [
      ['../MONT', 'to-EMBR'],
      ['MONT', 'to-EMBR?x=1'],
      ['MONT', ''],
    ] as const) {
      await expectClientError(client.getPredictions(station, group), 'not_found');
    }
    for (const id of ['2026-10-20:1965254', '2026-10-20:19/65:1', '2026-10-20:1965254:011', 'x']) {
      await expectClientError(client.getPredictionHistory(id), 'not_found');
    }
    expect(host.requests.length).toBe(before);
    expect(historyFile('2026-10-20:1965254:11')).toBe('history/2026-10-20_1965254_11.json');
    expect(historyFile('2026-10-20:1965254:011')).toBeNull();
  });

  it('answers unavailable for invalid JSON, an unexpected shape, an HTTP error or a failed request', async () => {
    const board = `${EXPORT}/boards/MONT/to-EMBR.json`;
    const cases: [string, (host: ReturnType<typeof createPublishedReplayHost>) => void][] = [
      ['invalid JSON', (h) => h.respond(board, { body: '{"stationId": "MONT", ' })],
      ['a page instead of JSON', (h) => h.respond(board, { body: '<!doctype html><p>Hi</p>' })],
      ['unexpected shape', (h) => h.respond(board, { body: JSON.stringify({ stationId: 'MONT' }) })],
      ['server error', (h) => h.respond(board, { status: 500, body: '' })],
      ['network failure', (h) => h.respond(board, () => Promise.reject(new TypeError('Failed to fetch')))],
    ];
    for (const [, configure] of cases) {
      const { client, host } = setup();
      configure(host);
      await expectClientError(client.getPredictions('MONT', 'to-EMBR'), 'unavailable');
    }
  });

  it('refuses an answer for another station or another replay time', async () => {
    const { client, host } = setup();
    const other = await host.read<Record<string, unknown>>(`${EXPORT}/boards/EMBR/to-MONT.json`);
    host.respond(`${EXPORT}/boards/MONT/to-EMBR.json`, { body: JSON.stringify(other) });
    await expectClientError(client.getPredictions('MONT', 'to-EMBR'), 'unavailable');

    const health = await host.read<Record<string, unknown>>(`${EXPORT}/health.json`);
    host.respond(`${EXPORT}/health.json`, { body: JSON.stringify({ ...health, asOf: '2026-10-15T17:00:00Z' }) });
    await expectClientError(client.getHealth(), 'unavailable');
  });

  it('refuses an unsupported schema version, and asks for the index again after a failure', async () => {
    const { client, host } = setup();
    const index = await host.read<Record<string, unknown>>('index.json');
    expect(index.schemaVersion).toBe(STATIC_REPLAY_SCHEMA);
    host.respond('index.json', { body: JSON.stringify({ ...index, schemaVersion: 'static-replay-2' }) });
    await expectClientError(client.listStations(), 'unavailable');
    host.respond('index.json', { body: JSON.stringify({ ...index, export: '../elsewhere' }) });
    await expectClientError(client.listStations(), 'unavailable');
    host.respond('index.json', { status: 404, body: '' });
    await expectClientError(client.listStations(), 'not_found');

    host.respond('index.json', { body: JSON.stringify(index) });
    expect(await client.listStations()).toHaveLength(50);
    await client.getHealth();
    expect(host.requests.filter((r) => r === 'index.json')).toHaveLength(4);
  });

  it('cancels one request without failing the shared index for the others', async () => {
    const { client, host } = setup();
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => (release = resolve));
    const index = JSON.stringify(await host.read('index.json'));
    host.respond('index.json', async () => {
      await held;
      return new Response(index, { status: 200 });
    });

    const controller = new AbortController();
    const cancelled = client.listStations(controller.signal);
    const kept = client.getHealth();
    controller.abort();
    const error = await rejection(cancelled);
    expect(error).toBeInstanceOf(DOMException);
    expect((error as DOMException).name).toBe('AbortError');

    release();
    expect((await kept).status).toBe('ok');
    expect(host.requests.filter((r) => r === 'index.json')).toHaveLength(1);

    // A file request passes its signal on, so the host's fetch sees the cancellation.
    const late = new AbortController();
    let seen: AbortSignal | undefined;
    host.respond(`${EXPORT}/boards/MONT/to-EMBR.json`, (init) => {
      seen = init?.signal ?? undefined;
      return new Promise<Response>((_, reject) =>
        seen?.addEventListener('abort', () => reject(new DOMException('The operation was aborted.', 'AbortError'))),
      );
    });
    const board = client.getPredictions('MONT', 'to-EMBR', late.signal);
    await vi.waitFor(() => expect(seen).toBe(late.signal));
    late.abort();
    expect(((await rejection(board)) as DOMException).name).toBe('AbortError');

    // A request already cancelled is refused without asking for the file.
    const before = host.requests.length;
    expect(((await rejection(client.getPredictions('MONT', 'to-EMBR', late.signal))) as DOMException).name).toBe(
      'AbortError',
    );
    expect(host.requests.length).toBe(before);
  });
});
