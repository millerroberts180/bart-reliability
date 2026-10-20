// Runtime checks for the local prediction API's JSON (docs/local_api.md). The API is an
// external boundary: every field the site uses is validated, and a response in an
// unrecognised data mode is rejected, so unlabelled data can never reach the page. A
// response that fails any check is rejected whole: nothing partial is shown.

import type {
  AlertCategory,
  AlertContext,
  AlertScope,
  BoardingGroup,
  DataProvenance,
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

/**
 * An ISO 8601 date and time with an explicit offset ("Z" or "+hh:mm"). A time without
 * one would be read in the visitor's own time zone, so it is refused rather than guessed.
 */
const ZONED_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/;

function timestamp(value: unknown, path: string): string {
  const text = string(value, path);
  if (!ZONED_TIMESTAMP.test(text) || Number.isNaN(Date.parse(text))) {
    throw new DecodeError(path, 'expected an ISO 8601 timestamp with a time zone');
  }
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

function nonNegative(value: unknown, path: string): number {
  const n = number(value, path);
  if (n < 0) throw new DecodeError(path, 'expected a number of at least 0');
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

/** Two items with one ID would be indistinguishable to the page (and to React). */
function unique<T>(items: T[], path: string, key: (item: T) => string, what: string): T[] {
  const seen = new Set<string>();
  for (const item of items) {
    const id = key(item);
    if (seen.has(id)) throw new DecodeError(path, `duplicate ${what} ${JSON.stringify(id)}`);
    seen.add(id);
  }
  return items;
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

function boardingGroup(value: unknown, path: string): BoardingGroup {
  const g = object(value, path);
  return {
    id: string(g.id, `${path}.id`),
    label: string(g.label, `${path}.label`),
    destinations: list(g.destinations, `${path}.destinations`, string),
    platform: nullable(g.platform, `${path}.platform`, string),
    gtfsDirectionIds: list(g.gtfsDirectionIds, `${path}.gtfsDirectionIds`, string),
  };
}

export function decodeStations(value: unknown): Station[] {
  const stations = list(value, 'stations', (v, path) => {
    const s = object(v, path);
    const groups = list(s.boardingGroups, `${path}.boardingGroups`, boardingGroup);
    return {
      id: string(s.id, `${path}.id`),
      name: string(s.name, `${path}.name`),
      boardingGroups: unique(groups, `${path}.boardingGroups`, (g) => g.id, 'boarding group'),
      endOfLine: boolean(s.endOfLine, `${path}.endOfLine`),
    };
  });
  return unique(stations, 'stations', (s) => s.id, 'station');
}

function interval(value: unknown, path: string): RevisionInterval {
  const i = object(value, path);
  const lowerSeconds = number(i.lowerSeconds, `${path}.lowerSeconds`);
  const upperSeconds = number(i.upperSeconds, `${path}.upperSeconds`);
  if (lowerSeconds > upperSeconds) throw new DecodeError(path, 'lower bound above upper bound');
  const level = number(i.level, `${path}.level`);
  // A coverage level is a fraction: 0.8 is "80%". Zero, negative or above 1 is no range.
  if (!(level > 0 && level <= 1)) throw new DecodeError(`${path}.level`, 'expected a fraction above 0 and at most 1');
  return { lowerSeconds, upperSeconds, level };
}

function train(value: unknown, path: string): TrainPrediction {
  const t = object(value, path);
  const base = {
    predictionId: string(t.predictionId, `${path}.predictionId`),
    tripId: string(t.tripId, `${path}.tripId`),
    lineName: string(t.lineName, `${path}.lineName`),
    headsign: string(t.headsign, `${path}.headsign`),
    carCount: nullable(t.carCount, `${path}.carCount`, count),
    // The board lists upcoming trains only, so an ETA is never in the past.
    currentEtaSeconds: nonNegative(t.currentEtaSeconds, `${path}.currentEtaSeconds`),
    currentEtaAt: timestamp(t.currentEtaAt, `${path}.currentEtaAt`),
    platform: nullable(t.platform, `${path}.platform`, string),
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
  const trains = list(r.trains, 'predictions.trains', train);
  return {
    ...provenance(r, 'predictions'),
    stationId: string(r.stationId, 'predictions.stationId'),
    boardingGroupId: string(r.boardingGroupId, 'predictions.boardingGroupId'),
    feedTimestamp: timestamp(r.feedTimestamp, 'predictions.feedTimestamp'),
    generatedAt: timestamp(r.generatedAt, 'predictions.generatedAt'),
    trains: unique(trains, 'predictions.trains', (t) => t.predictionId, 'prediction'),
    unplacedTrainCount: count(r.unplacedTrainCount, 'predictions.unplacedTrainCount'),
    terminatingTrainCount: count(r.terminatingTrainCount, 'predictions.terminatingTrainCount'),
    alerts: list(r.alerts, 'predictions.alerts', alert),
    model: decodeModelMetadata(r.model, 'predictions.model'),
  };
}

export function decodeHistory(value: unknown): PredictionHistoryPoint[] {
  const points = list(value, 'history', (v, path) => {
    const p = object(v, path);
    return {
      feedTimestamp: timestamp(p.feedTimestamp, `${path}.feedTimestamp`),
      publishedEtaAt: timestamp(p.publishedEtaAt, `${path}.publishedEtaAt`),
      publishedEtaSeconds: number(p.publishedEtaSeconds, `${path}.publishedEtaSeconds`),
    };
  });
  // One published ETA per snapshot: two would draw a vertical jump that never happened.
  return unique(points, 'history', (p) => new Date(p.feedTimestamp).toISOString(), 'snapshot');
}

export function decodeHealth(value: unknown): HealthStatus {
  const h = object(value, 'health');
  return {
    ...provenance(h, 'health'),
    status: oneOf(h.status, 'health.status', ['ok', 'degraded'] as const),
    latestFeedTimestamp: nullable(h.latestFeedTimestamp, 'health.latestFeedTimestamp', timestamp),
  };
}
