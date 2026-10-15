// Runtime checks for the local prediction API's JSON (docs/local_api.md). The API is an
// external boundary: every field the site uses is validated, and a response in an
// unrecognised data mode is rejected, so unlabelled data can never reach the page.

import type {
  AlertCategory,
  AlertContext,
  AlertScope,
  DataProvenance,
  Direction,
  HealthStatus,
  ModelMetadata,
  PredictionHistoryPoint,
  PredictionResponse,
  PredictionStatus,
  ReplayInfo,
  RevisionInterval,
  StabilityClass,
  Station,
  TrainPrediction,
} from '../domain/types';

export class DecodeError extends Error {
  constructor(path: string, problem: string) {
    super(`${path}: ${problem}`);
    this.name = 'DecodeError';
  }
}

type Fields = Record<string, unknown>;

function object(value: unknown, path: string): Fields {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new DecodeError(path, 'expected an object');
  return value as Fields;
}

function string(value: unknown, path: string): string {
  if (typeof value !== 'string') throw new DecodeError(path, 'expected a string');
  return value;
}

function timestamp(value: unknown, path: string): string {
  const text = string(value, path);
  if (Number.isNaN(Date.parse(text))) throw new DecodeError(path, 'expected an ISO 8601 timestamp');
  return text;
}

function number(value: unknown, path: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new DecodeError(path, 'expected a finite number');
  return value;
}

function count(value: unknown, path: string): number {
  const n = number(value, path);
  if (!Number.isInteger(n) || n < 0) throw new DecodeError(path, 'expected a whole number of at least 0');
  return n;
}

function boolean(value: unknown, path: string): boolean {
  if (typeof value !== 'boolean') throw new DecodeError(path, 'expected a boolean');
  return value;
}

function nullable<T>(value: unknown, path: string, decode: (v: unknown, p: string) => T): T | null {
  return value === null ? null : decode(value, path);
}

function list<T>(value: unknown, path: string, decode: (v: unknown, p: string) => T): T[] {
  if (!Array.isArray(value)) throw new DecodeError(path, 'expected an array');
  return value.map((item, i) => decode(item, `${path}[${i}]`));
}

function oneOf<T extends string>(value: unknown, path: string, allowed: readonly T[]): T {
  if (typeof value !== 'string' || !(allowed as readonly string[]).includes(value)) {
    throw new DecodeError(path, `expected one of ${allowed.join(', ')}`);
  }
  return value as T;
}

function mustBeNull(value: unknown, path: string): null {
  if (value !== null) throw new DecodeError(path, 'must be null for a train without a model forecast');
  return null;
}

const STABILITY: readonly StabilityClass[] = ['likely_to_hold', 'may_be_revised', 'likely_to_be_revised'];
const STATUSES: readonly PredictionStatus[] = [
  'ok',
  'outside_model_horizon',
  'outside_model_population',
  'fallback_required',
  'features_unavailable',
];
const SCOPES: readonly AlertScope[] = ['system', 'route', 'station'];
const CATEGORIES: readonly AlertCategory[] = ['planned_work', 'incident', 'unclassified'];

/** The API states its mode in every object body; only historical replay exists today. */
function provenance(body: Fields, path: string): { dataProvenance: DataProvenance; replay: ReplayInfo | null } {
  const mode = body.dataMode;
  if (mode !== 'historical_replay') {
    throw new DecodeError(`${path}.dataMode`, `unrecognised data mode ${JSON.stringify(mode)}`);
  }
  const asOf = body.replay !== undefined ? object(body.replay, `${path}.replay`).asOf : body.asOf;
  return { dataProvenance: 'historical_replay', replay: { asOf: timestamp(asOf, `${path}.asOf`) } };
}

function direction(value: unknown, path: string): Direction {
  const d = object(value, path);
  return {
    id: string(d.id, `${path}.id`),
    label: string(d.label, `${path}.label`),
    destinations: list(d.destinations, `${path}.destinations`, string),
  };
}

export function decodeStations(value: unknown): Station[] {
  return list(value, 'stations', (v, path) => {
    const s = object(v, path);
    return {
      id: string(s.id, `${path}.id`),
      name: string(s.name, `${path}.name`),
      directions: list(s.directions, `${path}.directions`, direction),
    };
  });
}

function interval(value: unknown, path: string): RevisionInterval {
  const i = object(value, path);
  const lowerSeconds = number(i.lowerSeconds, `${path}.lowerSeconds`);
  const upperSeconds = number(i.upperSeconds, `${path}.upperSeconds`);
  if (lowerSeconds > upperSeconds) throw new DecodeError(path, 'lower bound above upper bound');
  return { lowerSeconds, upperSeconds, level: number(i.level, `${path}.level`) };
}

function train(value: unknown, path: string): TrainPrediction {
  const t = object(value, path);
  const base = {
    predictionId: string(t.predictionId, `${path}.predictionId`),
    tripId: string(t.tripId, `${path}.tripId`),
    lineName: string(t.lineName, `${path}.lineName`),
    headsign: string(t.headsign, `${path}.headsign`),
    carCount: nullable(t.carCount, `${path}.carCount`, number),
    currentEtaSeconds: number(t.currentEtaSeconds, `${path}.currentEtaSeconds`),
    currentEtaAt: timestamp(t.currentEtaAt, `${path}.currentEtaAt`),
  };
  const status = oneOf(t.predictionStatus, `${path}.predictionStatus`, STATUSES);
  if (status === 'ok') {
    const probability = number(t.revisionProbability, `${path}.revisionProbability`);
    if (probability < 0 || probability > 1) throw new DecodeError(`${path}.revisionProbability`, 'outside 0 to 1');
    return {
      ...base,
      predictionStatus: 'ok',
      statusReason: null,
      predictedRevisionSeconds: number(t.predictedRevisionSeconds, `${path}.predictedRevisionSeconds`),
      revisionInterval: nullable(t.revisionInterval, `${path}.revisionInterval`, interval),
      revisionProbability: probability,
      stability: oneOf(t.stability, `${path}.stability`, STABILITY),
    };
  }
  return {
    ...base,
    predictionStatus: status,
    statusReason: nullable(t.statusReason, `${path}.statusReason`, string),
    predictedRevisionSeconds: mustBeNull(t.predictedRevisionSeconds, `${path}.predictedRevisionSeconds`),
    revisionInterval: mustBeNull(t.revisionInterval, `${path}.revisionInterval`),
    revisionProbability: mustBeNull(t.revisionProbability, `${path}.revisionProbability`),
    stability: mustBeNull(t.stability, `${path}.stability`),
  };
}

function alert(value: unknown, path: string): AlertContext {
  const a = object(value, path);
  return {
    alertId: string(a.alertId, `${path}.alertId`),
    scope: oneOf(a.scope, `${path}.scope`, SCOPES),
    category: oneOf(a.category, `${path}.category`, CATEGORIES),
    headerText: string(a.headerText, `${path}.headerText`),
    visibleSince: timestamp(a.visibleSince, `${path}.visibleSince`),
  };
}

export function decodeModelMetadata(value: unknown, path = 'model'): ModelMetadata {
  const m = object(value, path);
  return {
    modelVersion: string(m.modelVersion, `${path}.modelVersion`),
    trainedThrough: timestamp(m.trainedThrough, `${path}.trainedThrough`),
    revisionThresholdSeconds: number(m.revisionThresholdSeconds, `${path}.revisionThresholdSeconds`),
    simulated: boolean(m.simulated, `${path}.simulated`),
  };
}

export function decodePredictionResponse(value: unknown): PredictionResponse {
  const r = object(value, 'predictions');
  return {
    ...provenance(r, 'predictions'),
    stationId: string(r.stationId, 'predictions.stationId'),
    directionId: string(r.directionId, 'predictions.directionId'),
    feedTimestamp: timestamp(r.feedTimestamp, 'predictions.feedTimestamp'),
    generatedAt: timestamp(r.generatedAt, 'predictions.generatedAt'),
    trains: list(r.trains, 'predictions.trains', train),
    unplacedTrainCount: count(r.unplacedTrainCount, 'predictions.unplacedTrainCount'),
    alerts: list(r.alerts, 'predictions.alerts', alert),
    model: decodeModelMetadata(r.model, 'predictions.model'),
  };
}

export function decodeHistory(value: unknown): PredictionHistoryPoint[] {
  return list(value, 'history', (v, path) => {
    const p = object(v, path);
    return {
      feedTimestamp: timestamp(p.feedTimestamp, `${path}.feedTimestamp`),
      publishedEtaAt: timestamp(p.publishedEtaAt, `${path}.publishedEtaAt`),
      publishedEtaSeconds: number(p.publishedEtaSeconds, `${path}.publishedEtaSeconds`),
    };
  });
}

export function decodeHealth(value: unknown): HealthStatus {
  const h = object(value, 'health');
  return {
    ...provenance(h, 'health'),
    status: oneOf(h.status, 'health.status', ['ok', 'degraded'] as const),
    latestFeedTimestamp: nullable(h.latestFeedTimestamp, 'health.latestFeedTimestamp', timestamp),
  };
}
