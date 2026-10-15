import type {
  HealthStatus,
  ModelMetadata,
  PredictionHistoryPoint,
  PredictionResponse,
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
import { PredictionClientError, type PredictionClient, type PredictionClientErrorCode } from './PredictionClient';

export interface HttpPredictionClientOptions {
  /** Injectable for tests; defaults to the browser's fetch. */
  fetch?: typeof fetch;
}

const CLIENT_CODES: readonly PredictionClientErrorCode[] = ['not_found', 'unavailable', 'not_implemented'];

/**
 * Client for the local prediction API (docs/local_api.md). Each method calls one
 * endpoint, validates the JSON, and maps failures onto PredictionClientError so the
 * page shows the same error states as with the mock client. Aborted requests reject
 * with the browser's AbortError, which the page ignores.
 */
export class HttpPredictionClient implements PredictionClient {
  readonly source = 'api' as const;
  readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(baseUrl: string, { fetch: fetchImpl }: HttpPredictionClientOptions = {}) {
    this.baseUrl = baseUrl.trim().replace(/\/+$/, '');
    this.fetchImpl = fetchImpl ?? ((input, init) => globalThis.fetch(input, init));
  }

  /** Absolute URL for an endpoint path; exposed so the boundary is testable. */
  endpoint(path: string, query?: Record<string, string>): string {
    const search = query ? `?${new URLSearchParams(query).toString()}` : '';
    return `${this.baseUrl}/api/v1${path}${search}`;
  }

  listStations(signal?: AbortSignal): Promise<Station[]> {
    return this.get(this.endpoint('/stations'), decodeStations, signal);
  }

  async getPredictions(stationId: string, directionId: string, signal?: AbortSignal): Promise<PredictionResponse> {
    const url = this.endpoint(`/stations/${encodeURIComponent(stationId)}/predictions`, {
      direction_id: directionId,
    });
    const response = await this.get(url, decodePredictionResponse, signal);
    if (response.stationId !== stationId || response.directionId !== directionId) {
      throw new PredictionClientError('unavailable', 'The API answered for a different station or direction.');
    }
    return response;
  }

  getPredictionHistory(predictionId: string, signal?: AbortSignal): Promise<PredictionHistoryPoint[]> {
    return this.get(this.endpoint(`/predictions/${encodeURIComponent(predictionId)}/history`), decodeHistory, signal);
  }

  getModelMetadata(signal?: AbortSignal): Promise<ModelMetadata> {
    return this.get(this.endpoint('/model/metadata'), (v) => decodeModelMetadata(v), signal);
  }

  getHealth(signal?: AbortSignal): Promise<HealthStatus> {
    return this.get(this.endpoint('/health'), decodeHealth, signal);
  }

  private async get<T>(url: string, decode: (body: unknown) => T, signal?: AbortSignal): Promise<T> {
    if (!this.baseUrl) {
      throw new PredictionClientError('unavailable', 'No API address is configured. Set VITE_API_BASE_URL.');
    }
    let response: Response;
    let body: unknown;
    try {
      response = await this.fetchImpl(url, {
        ...(signal && { signal }),
        headers: { Accept: 'application/json' },
        credentials: 'omit',
      });
      body = await response.json().catch(() => undefined);
    } catch (error) {
      if (isAbort(error, signal)) throw error;
      throw new PredictionClientError('unavailable', `The prediction API at ${this.baseUrl} could not be reached.`);
    }
    if (!response.ok) throw errorFromResponse(response.status, body);
    try {
      return decode(body);
    } catch (error) {
      if (error instanceof DecodeError) {
        throw new PredictionClientError('unavailable', `The API sent an unexpected response (${error.message}).`);
      }
      throw error;
    }
  }
}

function isAbort(error: unknown, signal?: AbortSignal): boolean {
  return Boolean(signal?.aborted) || (error instanceof DOMException && error.name === 'AbortError');
}

/** Uses the API's own error code and message when it sent them (docs/local_api.md, "Errors"). */
function errorFromResponse(status: number, body: unknown): PredictionClientError {
  const detail =
    typeof body === 'object' && body !== null && 'error' in body && typeof body.error === 'object' && body.error
      ? (body.error as Record<string, unknown>)
      : {};
  const code =
    typeof detail.clientCode === 'string' && (CLIENT_CODES as readonly string[]).includes(detail.clientCode)
      ? (detail.clientCode as PredictionClientErrorCode)
      : status === 404
        ? 'not_found'
        : 'unavailable';
  const message = typeof detail.message === 'string' ? detail.message : `The API returned HTTP ${status}.`;
  return new PredictionClientError(code, message);
}
