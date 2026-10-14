import type {
  HealthStatus,
  ModelMetadata,
  PredictionHistoryPoint,
  PredictionResponse,
  Station,
} from '../domain/types';
import { PredictionClientError, type PredictionClient } from './PredictionClient';

/**
 * Placeholder for the future API client. It records the endpoint each method
 * will call but makes no network requests: every call rejects with
 * "not_implemented" until a later milestone provides the API.
 */
export class HttpPredictionClient implements PredictionClient {
  readonly baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  /** Absolute URL for an endpoint path; exposed so the boundary is testable. */
  endpoint(path: string, query?: Record<string, string>): string {
    const search = query ? `?${new URLSearchParams(query).toString()}` : '';
    return `${this.baseUrl}/api/v1${path}${search}`;
  }

  listStations(): Promise<Station[]> {
    return this.notImplemented(this.endpoint('/stations'));
  }

  getPredictions(stationId: string, directionId: string): Promise<PredictionResponse> {
    return this.notImplemented(
      this.endpoint('/predictions', { station_id: stationId, direction_id: directionId }),
    );
  }

  getPredictionHistory(predictionId: string): Promise<PredictionHistoryPoint[]> {
    return this.notImplemented(this.endpoint(`/predictions/${encodeURIComponent(predictionId)}/history`));
  }

  getModelMetadata(): Promise<ModelMetadata> {
    return this.notImplemented(this.endpoint('/model/metadata'));
  }

  getHealth(): Promise<HealthStatus> {
    return this.notImplemented(this.endpoint('/health'));
  }

  private notImplemented<T>(url: string): Promise<T> {
    return Promise.reject(
      new PredictionClientError('not_implemented', `The live API is not available yet (${url}).`),
    );
  }
}
