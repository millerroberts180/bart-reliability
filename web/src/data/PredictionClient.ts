import type {
  HealthStatus,
  ModelMetadata,
  PredictionHistoryPoint,
  PredictionResponse,
  Station,
} from '../domain/types';

/**
 * The only boundary components use to obtain data. Each method mirrors one
 * provisional endpoint of the future API (see docs/website_architecture.md).
 */
export interface PredictionClient {
  /** GET /api/v1/stations */
  listStations(signal?: AbortSignal): Promise<Station[]>;
  /** GET /api/v1/predictions?station_id=...&direction_id=... */
  getPredictions(stationId: string, directionId: string, signal?: AbortSignal): Promise<PredictionResponse>;
  /** GET /api/v1/predictions/{prediction_id}/history */
  getPredictionHistory(predictionId: string, signal?: AbortSignal): Promise<PredictionHistoryPoint[]>;
  /** GET /api/v1/model/metadata */
  getModelMetadata(signal?: AbortSignal): Promise<ModelMetadata>;
  /** GET /api/v1/health */
  getHealth(signal?: AbortSignal): Promise<HealthStatus>;
}

export type PredictionClientErrorCode = 'not_found' | 'unavailable' | 'not_implemented';

export class PredictionClientError extends Error {
  readonly code: PredictionClientErrorCode;

  constructor(code: PredictionClientErrorCode, message: string) {
    super(message);
    this.name = 'PredictionClientError';
    this.code = code;
  }
}
