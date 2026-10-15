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
  SIMULATED_HISTORY,
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

/**
 * Which response the mock gives for ETA history. "normal" follows each train's
 * script; the others force a state for review and tests.
 */
export type MockHistoryScenario = 'normal' | 'loading' | 'error' | 'single' | 'none' | 'gaps';

export const MOCK_HISTORY_SCENARIOS: readonly MockHistoryScenario[] = ['normal', 'loading', 'error', 'single', 'none', 'gaps'];

/** Snapshots removed by the "gaps" history scenario (minutes before the latest). */
const FORCED_GAP_MINUTES = [8, 7, 6];

export interface MockPredictionClientOptions {
  scenario?: MockScenario;
  historyScenario?: MockHistoryScenario;
  /** Clock used to place fixture offsets in time. */
  now?: () => Date;
  /** Simulated network delay. */
  latencyMs?: number;
}

/** Deterministic simulated data: same scenario and clock, same response. */
export class MockPredictionClient implements PredictionClient {
  readonly scenario: MockScenario;
  readonly historyScenario: MockHistoryScenario;
  private readonly now: () => Date;
  private readonly latencyMs: number;
  /**
   * Feed snapshot of the latest predictions response per station and direction, so
   * history ends exactly at the snapshot the visitor is looking at.
   */
  private readonly latestSnapshots = new Map<string, string>();

  constructor({
    scenario = 'live',
    historyScenario = 'normal',
    now = () => new Date(),
    latencyMs = 0,
  }: MockPredictionClientOptions = {}) {
    this.scenario = scenario;
    this.historyScenario = historyScenario;
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
      const feedTimestamp = this.currentSnapshot();
      this.latestSnapshots.set(`${stationId}:${directionId}`, feedTimestamp);
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
    if (this.historyScenario === 'loading') return this.never(signal);
    if (this.historyScenario === 'error') {
      return this.fail(new PredictionClientError('unavailable', 'The history service did not respond.'), signal);
    }

    const [stationId, directionId, tripId] = predictionId.split(':');
    const train = SIMULATED_TRAINS[`${stationId}:${directionId}`]?.find((t) => t.tripId === tripId);
    const script = SIMULATED_HISTORY[predictionId];
    if (!train || !script) {
      return this.fail(new PredictionClientError('not_found', `Unknown prediction ${predictionId}.`), signal);
    }

    return this.respond(() => {
      const latest = this.latestSnapshots.get(`${stationId}:${directionId}`) ?? this.currentSnapshot();
      const currentEtaAt = addSeconds(latest, train.etaSeconds);
      const missing = new Set([...(script.missing ?? []), ...(this.historyScenario === 'gaps' ? FORCED_GAP_MINUTES : [])]);
      let minutesAgo = Array.from({ length: script.snapshots }, (_, i) => script.snapshots - 1 - i).filter(
        (m) => m === 0 || !missing.has(m),
      );
      if (this.historyScenario === 'single') minutesAgo = [0];
      if (this.historyScenario === 'none') minutesAgo = [];

      return minutesAgo.map((m) => {
        const feedTimestamp = addSeconds(latest, -m * 60);
        // Steps at or after this snapshot (minutesAgo < m) had not happened yet.
        const pending = script.steps.filter(([stepMinutes]) => stepMinutes < m).reduce((sum, [, d]) => sum + d, 0);
        const publishedEtaAt = addSeconds(currentEtaAt, -pending);
        const publishedEtaSeconds = Math.round((Date.parse(publishedEtaAt) - Date.parse(feedTimestamp)) / 1000);
        return { feedTimestamp, publishedEtaAt, publishedEtaSeconds };
      });
    }, signal);
  }

  getModelMetadata(signal?: AbortSignal): Promise<ModelMetadata> {
    return this.respond(() => ({ ...SIMULATED_MODEL }), signal);
  }

  getHealth(signal?: AbortSignal): Promise<HealthStatus> {
    return this.respond(
      () => ({ status: this.scenario === 'live' ? 'ok' : 'degraded', latestFeedTimestamp: this.currentSnapshot() }),
      signal,
    );
  }

  /** The newest feed snapshot for this scenario, placed against the clock. */
  private currentSnapshot(): string {
    const feedAge = this.scenario === 'stale' ? FEED_AGE_SECONDS.stale : FEED_AGE_SECONDS.live;
    return addSeconds(this.now().toISOString(), -feedAge);
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
