import type {
  HealthStatus,
  ModelMetadata,
  PredictionHistoryPoint,
  PredictionResponse,
  ReplayInfo,
  Station,
} from '../domain/types';
import {
  DecodeError,
  decodeHealth,
  decodeHistory,
  decodeModelMetadata,
  decodePredictionResponse,
  decodeStations,
} from './apiDecode';
import { PredictionClientError, type PredictionClient } from './PredictionClient';

/** The published replay's format (docs/static_replay.md). Any other is refused. */
export const STATIC_REPLAY_SCHEMA = 'static-replay-1';

// The exporter's file names (src/bart_reliability/static_replay/export.py).
const SAFE_ID = /^[A-Za-z0-9-]{1,80}$/;
const EXPORT_NAME = /^v1-\d{8}T\d{6}Z$/;
const PREDICTION_ID = /^(\d{4}-\d{2}-\d{2}):([A-Za-z0-9-]{1,80}):(\d{1,6})$/;

interface ReplayIndex {
  /** Directory of the export the index names, ending in "/". */
  exportUrl: string;
  asOf: string;
}

export interface StaticReplayClientOptions {
  /** Injectable for tests; defaults to the browser's fetch. */
  fetch?: typeof fetch;
}

/**
 * Client for the static historical replay published with the site (docs/static_replay.md):
 * the local API's answers at one fixed moment, one JSON file per request. It reads only
 * same-origin files under `root`. First comes `index.json`, which names the export and
 * its schema. Each answer is fetched only when the page asks for it. Every file passes
 * the same decoders as the HTTP client, and failures map onto PredictionClientError, so
 * the page shows the same states and offers the same retry either way.
 */
export class StaticReplayClient implements PredictionClient {
  // The answers are the prediction API's, exported; each states its own data mode.
  readonly source = 'api' as const;
  /** URL path of the published replay, ending in "/", e.g. "/bart-reliability/replay/". */
  readonly root: string;
  private readonly fetchImpl: typeof fetch;
  private index: Promise<ReplayIndex> | null = null;

  constructor(root: string, { fetch: fetchImpl }: StaticReplayClientOptions = {}) {
    this.root = root.endsWith('/') ? root : `${root}/`;
    this.fetchImpl = fetchImpl ?? ((input, init) => globalThis.fetch(input, init));
  }

  listStations(signal?: AbortSignal): Promise<Station[]> {
    return this.read('stations.json', decodeStations, signal);
  }

  getPredictions(stationId: string, boardingGroupId: string, signal?: AbortSignal): Promise<PredictionResponse> {
    if (!SAFE_ID.test(stationId) || !SAFE_ID.test(boardingGroupId)) {
      return Promise.reject(new PredictionClientError('not_found', 'The replay has no board for that station.'));
    }
    return this.read(`boards/${stationId}/${boardingGroupId}.json`, decodePredictionResponse, signal, (response, index) => {
      if (response.stationId !== stationId || response.boardingGroupId !== boardingGroupId) {
        throw unavailable('The replay file holds a different station or boarding group.');
      }
      sameReplay(response.replay, index);
    });
  }

  getPredictionHistory(predictionId: string, signal?: AbortSignal): Promise<PredictionHistoryPoint[]> {
    const file = historyFile(predictionId);
    if (!file) return Promise.reject(new PredictionClientError('not_found', 'The replay has no history for that train.'));
    return this.read(file, decodeHistory, signal);
  }

  getModelMetadata(signal?: AbortSignal): Promise<ModelMetadata> {
    return this.read('model.json', (v) => decodeModelMetadata(v), signal);
  }

  getHealth(signal?: AbortSignal): Promise<HealthStatus> {
    return this.read('health.json', decodeHealth, signal, (health, index) => sameReplay(health.replay, index));
  }

  private async read<T>(
    file: string,
    decode: (body: unknown) => T,
    signal?: AbortSignal,
    check?: (value: T, index: ReplayIndex) => void,
  ): Promise<T> {
    const index = await this.loadIndex(signal);
    const body = await this.fetchJson(`${index.exportUrl}${file}`, file, signal);
    let value: T;
    try {
      value = decode(body);
    } catch (error) {
      if (error instanceof DecodeError) throw unavailable(`The replay file ${file} is not in the expected form (${error.message}).`);
      throw error;
    }
    check?.(value, index);
    return value;
  }

  /**
   * The index is fetched once and shared, without any one caller's signal, so a cancelled
   * request cannot fail it for the others. A failed index is forgotten, so retrying asks again.
   */
  private loadIndex(signal?: AbortSignal): Promise<ReplayIndex> {
    this.index ??= this.fetchJson(`${this.root}index.json`, 'index.json')
      .then((body) => parseIndex(body, this.root))
      .catch((error: unknown) => {
        this.index = null;
        throw error;
      });
    return abortable(this.index, signal);
  }

  private async fetchJson(url: string, file: string, signal?: AbortSignal): Promise<unknown> {
    let response: Response;
    try {
      response = await this.fetchImpl(url, {
        ...(signal && { signal }),
        headers: { Accept: 'application/json' },
        credentials: 'omit',
      });
    } catch (error) {
      if (isAbort(error, signal)) throw error;
      throw unavailable('The historical replay could not be loaded.');
    }
    if (response.status === 404) throw new PredictionClientError('not_found', `The replay has no file ${file}.`);
    if (!response.ok) throw unavailable(`The replay file ${file} returned HTTP ${response.status}.`);
    try {
      return await response.json();
    } catch (error) {
      if (isAbort(error, signal)) throw error;
      throw unavailable(`The replay file ${file} is not valid JSON.`);
    }
  }
}

/** history/<service date>_<trip>_<stop sequence>.json, or null for an ID the exporter never writes. */
export function historyFile(predictionId: string): string | null {
  const match = PREDICTION_ID.exec(predictionId);
  if (!match) return null;
  const [, day, trip, sequence] = match;
  if (String(Number(sequence)) !== sequence) return null;
  return `history/${day}_${trip}_${sequence}.json`;
}

function parseIndex(body: unknown, root: string): ReplayIndex {
  const index = typeof body === 'object' && body !== null && !Array.isArray(body) ? (body as Record<string, unknown>) : {};
  if (index.schemaVersion !== STATIC_REPLAY_SCHEMA) {
    throw unavailable(`The replay uses schema ${JSON.stringify(index.schemaVersion)}; this site reads ${STATIC_REPLAY_SCHEMA}.`);
  }
  if (index.dataMode !== 'historical_replay') throw unavailable('The replay is not labelled as a historical replay.');
  if (typeof index.export !== 'string' || !EXPORT_NAME.test(index.export)) {
    throw unavailable('The replay index names no valid export.');
  }
  if (typeof index.asOf !== 'string' || Number.isNaN(Date.parse(index.asOf))) {
    throw unavailable('The replay index has no valid replay time.');
  }
  return { exportUrl: `${root}${index.export}/`, asOf: index.asOf };
}

/** An answer from another replay time than the index names is not this replay's. */
function sameReplay(replay: ReplayInfo | null, index: ReplayIndex): void {
  if (!replay || Date.parse(replay.asOf) !== Date.parse(index.asOf)) {
    throw unavailable('The replay file is from a different replay time.');
  }
}

function unavailable(message: string): PredictionClientError {
  return new PredictionClientError('unavailable', message);
}

function isAbort(error: unknown, signal?: AbortSignal): boolean {
  return Boolean(signal?.aborted) || (error instanceof DOMException && error.name === 'AbortError');
}

/** `promise`, rejected with an AbortError as soon as `signal` aborts. */
function abortable<T>(promise: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (!signal) return promise;
  return new Promise<T>((resolve, reject) => {
    const abort = () => reject(new DOMException('The operation was aborted.', 'AbortError'));
    if (signal.aborted) abort();
    else signal.addEventListener('abort', abort, { once: true });
    promise.then(
      (value) => {
        signal.removeEventListener('abort', abort);
        resolve(value);
      },
      (error: unknown) => {
        signal.removeEventListener('abort', abort);
        reject(error);
      },
    );
  });
}
