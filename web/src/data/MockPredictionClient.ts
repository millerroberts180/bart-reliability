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
export type MockScenario =
  | 'live'
  | 'loading'
  | 'error'
  | 'stale'
  | 'empty'
  | 'no-interval'
  | 'eta-only'
  | 'model-horizon';

export const MOCK_SCENARIOS: readonly MockScenario[] = [
  'live',
  'loading',
  'error',
  'stale',
  'empty',
  'no-interval',
  'eta-only',
  'model-horizon',
];

/**
 * The real models serve only ETAs within this many seconds of these published-time
 * horizons (docs/local_api.md); the "model-horizon" scenario applies the same rule.
 */
const SERVED_HORIZONS_SECONDS = [300, 600, 900];
const HORIZON_TOLERANCE_SECONDS = 60;

/**
 * Which response the mock gives for ETA history. "normal" follows each train's
 * script; the others force a state for review and tests.
 */
export type MockHistoryScenario = 'normal' | 'loading' | 'error' | 'single' | 'none' | 'gaps';

export const MOCK_HISTORY_SCENARIOS: readonly MockHistoryScenario[] = ['normal', 'loading', 'error', 'single', 'none', 'gaps'];

/**
 * Which station set the mock serves: the small hand-written demo (three stations) or
 * the full 50-station network derived from BART's static GTFS, with 20 trains each.
 */
export type MockNetwork = 'demo' | 'full';

export const MOCK_NETWORKS: readonly MockNetwork[] = ['demo', 'full'];

type FullNetwork = typeof import('./fixtures/fullNetwork');

/** Snapshots removed by the "gaps" history scenario (minutes before the latest). */
const FORCED_GAP_MINUTES = [8, 7, 6];

export interface MockPredictionClientOptions {
  scenario?: MockScenario;
  historyScenario?: MockHistoryScenario;
  network?: MockNetwork;
  /** Clock used to place fixture offsets in time. */
  now?: () => Date;
  /** Simulated network delay. */
  latencyMs?: number;
}

/** Deterministic simulated data: same scenario and clock, same response. */
export class MockPredictionClient implements PredictionClient {
  readonly source = 'simulated' as const;
  readonly scenario: MockScenario;
  readonly historyScenario: MockHistoryScenario;
  readonly network: MockNetwork;
  private fullNetwork: FullNetwork | null = null;
  private fullNetworkLoad: Promise<FullNetwork> | null = null;
  private readonly now: () => Date;
  private readonly latencyMs: number;
  /**
   * Feed snapshot of the latest predictions response per station and boarding group, so
   * history ends exactly at the snapshot the visitor is looking at.
   */
  private readonly latestSnapshots = new Map<string, string>();

  constructor({
    scenario = 'live',
    historyScenario = 'normal',
    network = 'demo',
    now = () => new Date(),
    latencyMs = 0,
  }: MockPredictionClientOptions = {}) {
    this.scenario = scenario;
    this.historyScenario = historyScenario;
    this.network = network;
    this.now = now;
    this.latencyMs = latencyMs;
  }

  listStations(signal?: AbortSignal): Promise<Station[]> {
    if (this.network !== 'full') return this.respond(() => structuredClone(SIMULATED_STATIONS), signal);
    return this.ready().then(() => this.respond(() => structuredClone(this.full().NETWORK_STATIONS), signal));
  }

  getPredictions(stationId: string, boardingGroupId: string, signal?: AbortSignal): Promise<PredictionResponse> {
    if (this.network !== 'full') return this.predictionsFor(stationId, boardingGroupId, signal);
    return this.ready().then(() => this.predictionsFor(stationId, boardingGroupId, signal));
  }

  private predictionsFor(stationId: string, groupId: string, signal?: AbortSignal): Promise<PredictionResponse> {
    if (this.scenario === 'loading') return this.never(signal);
    if (this.scenario === 'error') {
      return this.fail(new PredictionClientError('unavailable', 'The prediction service did not respond.'), signal);
    }

    const fixture = this.trainsFor(stationId, groupId);
    if (!fixture) {
      return this.fail(
        new PredictionClientError('not_found', `No boarding group ${groupId} at station ${stationId}.`),
        signal,
      );
    }

    return this.respond(() => {
      const feedTimestamp = this.currentSnapshot();
      this.latestSnapshots.set(`${stationId}:${groupId}`, feedTimestamp);
      const trains =
        this.scenario === 'empty'
          ? []
          : fixture.map((t) => toPrediction(t, stationId, groupId, feedTimestamp, this.scenario));
      const alerts = (SIMULATED_ALERTS[stationId] ?? []).map(({ visibleForSeconds, ...alert }) => ({
        ...alert,
        visibleSince: addSeconds(feedTimestamp, -visibleForSeconds),
      }));
      return {
        dataProvenance: 'simulated' as const,
        replay: null,
        stationId,
        boardingGroupId: groupId,
        feedTimestamp,
        generatedAt: addSeconds(feedTimestamp, MODEL_LAG_SECONDS),
        trains,
        unplacedTrainCount: 0,
        terminatingTrainCount: 0,
        alerts,
        model: { ...SIMULATED_MODEL },
      };
    }, signal);
  }

  getPredictionHistory(predictionId: string, signal?: AbortSignal): Promise<PredictionHistoryPoint[]> {
    if (this.network !== 'full') return this.historyFor(predictionId, signal);
    return this.ready().then(() => this.historyFor(predictionId, signal));
  }

  private historyFor(predictionId: string, signal?: AbortSignal): Promise<PredictionHistoryPoint[]> {
    if (this.historyScenario === 'loading') return this.never(signal);
    if (this.historyScenario === 'error') {
      return this.fail(new PredictionClientError('unavailable', 'The history service did not respond.'), signal);
    }

    const [stationId, groupId, tripId] = predictionId.split(':');
    const train = this.trainsFor(stationId ?? '', groupId ?? '')?.find((t) => t.tripId === tripId);
    const script = this.network === 'full' && train ? this.full().networkHistory(predictionId) : SIMULATED_HISTORY[predictionId];
    if (!train || !script) {
      return this.fail(new PredictionClientError('not_found', `Unknown prediction ${predictionId}.`), signal);
    }

    return this.respond(() => {
      const latest = this.latestSnapshots.get(`${stationId}:${groupId}`) ?? this.currentSnapshot();
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
      () => ({
        status: this.scenario === 'live' ? 'ok' : 'degraded',
        latestFeedTimestamp: this.currentSnapshot(),
        dataProvenance: 'simulated',
        replay: null,
      }),
      signal,
    );
  }

  /** Loads the full-network fixture on first use (the demo set never calls this). */
  private ready(): Promise<void> {
    if (this.fullNetwork) return Promise.resolve();
    this.fullNetworkLoad ??= import('./fixtures/fullNetwork').then((module) => (this.fullNetwork = module));
    return this.fullNetworkLoad.then(() => undefined);
  }

  private full(): FullNetwork {
    if (!this.fullNetwork) throw new Error('The full-network fixture has not loaded.');
    return this.fullNetwork;
  }

  private trainsFor(stationId: string, groupId: string): SimulatedTrain[] | undefined {
    return this.network === 'full'
      ? this.full().networkTrains(stationId, groupId)
      : SIMULATED_TRAINS[`${stationId}:${groupId}`];
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
      if (signal?.aborted) return reject(abortError()); // aborted while the fixture loaded
      signal?.addEventListener('abort', () => reject(abortError()));
    });
  }
}

function toPrediction(
  t: SimulatedTrain,
  stationId: string,
  groupId: string,
  feedTimestamp: string,
  scenario: MockScenario,
): TrainPrediction {
  const base = {
    predictionId: `${stationId}:${groupId}:${t.tripId}`,
    tripId: t.tripId,
    lineName: t.lineName,
    headsign: t.headsign,
    carCount: t.carCount,
    currentEtaSeconds: t.etaSeconds,
    currentEtaAt: addSeconds(feedTimestamp, t.etaSeconds),
    platform: t.platform,
  };
  const served = SERVED_HORIZONS_SECONDS.some((h) => Math.abs(t.etaSeconds - h) <= HORIZON_TOLERANCE_SECONDS);
  if (scenario === 'eta-only' || (scenario === 'model-horizon' && !served)) {
    // Reviews how a train outside the model's support looks: BART's ETA only.
    return {
      ...base,
      predictionStatus: 'outside_model_horizon',
      statusReason: 'Simulated: outside the published-time horizons the model serves.',
      predictedRevisionSeconds: null,
      revisionInterval: null,
      revisionProbability: null,
      stability: null,
    };
  }
  return {
    ...base,
    predictionStatus: 'ok',
    statusReason: null,
    predictedRevisionSeconds: t.revisionSeconds,
    revisionInterval:
      scenario === 'no-interval' ? null : { lowerSeconds: t.interval[0], upperSeconds: t.interval[1], level: 0.8 },
    revisionProbability: t.probability,
    stability: classifyStability(t.probability),
  };
}

function abortError(): DOMException {
  return new DOMException('The request was aborted.', 'AbortError');
}
