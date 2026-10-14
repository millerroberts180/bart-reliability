import { addSeconds, classifyStability } from '../domain/eta';
import type {
  HealthStatus,
  ModelMetadata,
  PredictionHistoryPoint,
  PredictionResponse,
  Station,
  TrainPrediction,
} from '../domain/types';
import {
  FEED_AGE_SECONDS,
  MODEL_LAG_SECONDS,
  SIMULATED_ALERTS,
  SIMULATED_MODEL,
  SIMULATED_STATIONS,
  SIMULATED_TRAINS,
  type SimulatedTrain,
} from './fixtures/simulated';
import { PredictionClientError, type PredictionClient } from './PredictionClient';

/**
 * Which response the mock gives for predictions. "live" is the normal case;
 * the others exist so every interface state can be reviewed and tested.
 */
export type MockScenario = 'live' | 'loading' | 'error' | 'stale' | 'empty';

export const MOCK_SCENARIOS: readonly MockScenario[] = ['live', 'loading', 'error', 'stale', 'empty'];

export interface MockPredictionClientOptions {
  scenario?: MockScenario;
  /** Clock used to place fixture offsets in time. */
  now?: () => Date;
  /** Simulated network delay. */
  latencyMs?: number;
}

/** Deterministic simulated data: same scenario and clock, same response. */
export class MockPredictionClient implements PredictionClient {
  readonly scenario: MockScenario;
  private readonly now: () => Date;
  private readonly latencyMs: number;

  constructor({ scenario = 'live', now = () => new Date(), latencyMs = 0 }: MockPredictionClientOptions = {}) {
    this.scenario = scenario;
    this.now = now;
    this.latencyMs = latencyMs;
  }

  listStations(signal?: AbortSignal): Promise<Station[]> {
    return this.respond(() => structuredClone(SIMULATED_STATIONS), signal);
  }

  getPredictions(stationId: string, directionId: string, signal?: AbortSignal): Promise<PredictionResponse> {
    if (this.scenario === 'loading') return this.never(signal);
    if (this.scenario === 'error') {
      return this.fail(new PredictionClientError('unavailable', 'The prediction service did not respond.'), signal);
    }

    const fixture = SIMULATED_TRAINS[`${stationId}:${directionId}`];
    if (!fixture) {
      return this.fail(
        new PredictionClientError('not_found', `No direction ${directionId} at station ${stationId}.`),
        signal,
      );
    }

    return this.respond(() => {
      const feedAge = this.scenario === 'stale' ? FEED_AGE_SECONDS.stale : FEED_AGE_SECONDS.live;
      const feedTimestamp = addSeconds(this.now().toISOString(), -feedAge);
      const trains = this.scenario === 'empty' ? [] : fixture.map((t) => toPrediction(t, stationId, directionId, feedTimestamp));
      const alerts = (SIMULATED_ALERTS[stationId] ?? []).map(({ visibleForSeconds, ...alert }) => ({
        ...alert,
        visibleSince: addSeconds(feedTimestamp, -visibleForSeconds),
      }));
      return {
        stationId,
        directionId,
        feedTimestamp,
        generatedAt: addSeconds(feedTimestamp, MODEL_LAG_SECONDS),
        trains,
        alerts,
        model: { ...SIMULATED_MODEL },
      };
    }, signal);
  }

  getPredictionHistory(predictionId: string, signal?: AbortSignal): Promise<PredictionHistoryPoint[]> {
    const [stationId, directionId, tripId] = predictionId.split(':');
    const train = SIMULATED_TRAINS[`${stationId}:${directionId}`]?.find((t) => t.tripId === tripId);
    if (!train) {
      return this.fail(new PredictionClientError('not_found', `Unknown prediction ${predictionId}.`), signal);
    }
    return this.respond(() => {
      const latest = addSeconds(this.now().toISOString(), -FEED_AGE_SECONDS.live);
      // Five earlier snapshots, one per minute, drifting toward the current ETA.
      return [5, 4, 3, 2, 1, 0].map((minutesAgo) => {
        const feedTimestamp = addSeconds(latest, -minutesAgo * 60);
        const drift = Math.round((train.revisionSeconds / 3) * (minutesAgo / 5));
        const publishedEtaAt = addSeconds(latest, train.etaSeconds - drift);
        const publishedEtaSeconds = Math.round((Date.parse(publishedEtaAt) - Date.parse(feedTimestamp)) / 1000);
        return { feedTimestamp, publishedEtaAt, publishedEtaSeconds };
      });
    }, signal);
  }

  getModelMetadata(signal?: AbortSignal): Promise<ModelMetadata> {
    return this.respond(() => ({ ...SIMULATED_MODEL }), signal);
  }

  getHealth(signal?: AbortSignal): Promise<HealthStatus> {
    return this.respond(() => {
      const feedAge = this.scenario === 'stale' ? FEED_AGE_SECONDS.stale : FEED_AGE_SECONDS.live;
      return {
        status: this.scenario === 'live' ? 'ok' : 'degraded',
        latestFeedTimestamp: addSeconds(this.now().toISOString(), -feedAge),
      };
    }, signal);
  }

  private respond<T>(build: () => T, signal?: AbortSignal): Promise<T> {
    return this.settle((resolve) => resolve(build()), signal);
  }

  private fail<T>(error: Error, signal?: AbortSignal): Promise<T> {
    return this.settle((_, reject) => reject(error), signal);
  }

  private settle<T>(
    finish: (resolve: (value: T) => void, reject: (reason: Error) => void) => void,
    signal?: AbortSignal,
  ): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      if (signal?.aborted) return reject(abortError());
      const timer = setTimeout(() => finish(resolve, reject), this.latencyMs);
      signal?.addEventListener('abort', () => {
        clearTimeout(timer);
        reject(abortError());
      });
    });
  }

  /** A request that stays pending until aborted, for reviewing the loading state. */
  private never<T>(signal?: AbortSignal): Promise<T> {
    return new Promise<T>((_, reject) => {
      signal?.addEventListener('abort', () => reject(abortError()));
    });
  }
}

function toPrediction(t: SimulatedTrain, stationId: string, directionId: string, feedTimestamp: string): TrainPrediction {
  return {
    predictionId: `${stationId}:${directionId}:${t.tripId}`,
    tripId: t.tripId,
    lineName: t.lineName,
    headsign: t.headsign,
    carCount: t.carCount,
    currentEtaSeconds: t.etaSeconds,
    currentEtaAt: addSeconds(feedTimestamp, t.etaSeconds),
    predictedRevisionSeconds: t.revisionSeconds,
    revisionInterval: { lowerSeconds: t.interval[0], upperSeconds: t.interval[1], level: 0.8 },
    revisionProbability: t.probability,
    stability: classifyStability(t.probability),
  };
}

function abortError(): DOMException {
  return new DOMException('The request was aborted.', 'AbortError');
}
