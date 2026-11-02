// The curated showcase's own files (docs/showcase_replay.md), published beside the replay
// in public/showcase/. Their JSON Schemas are in docs/contracts/showcase/; this decoder
// checks every field the site reads, and a file that fails is rejected whole.
//
// Three ETAs, never mixed up:
// - BART published ETA: what BART said at the replay snapshot (the replay boards).
// - Model-adjusted ETA: BART's ETA plus the model's predicted revision.
// - Final published ETA: the final stable ETA BART published later. Retrospective: the
//   model did not know it, and it is not a physical arrival time.

import { DecodeError } from '../data/apiDecode';

export type Horizon = '300' | '600' | '900';
export const HORIZONS: readonly Horizon[] = ['300', '600', '900'];
export type Direction = 'later' | 'earlier' | 'unchanged';

export interface ShowcaseMeta {
  asOf: string;
  feedTimestamp: string;
  serviceDate: string;
  localTime: string;
  modelVersion: string;
  disclosure: string;
  modelScope: string;
  notLive: string;
  includedRecords: number;
  supportedForecasts: number;
  boardEntries: number;
  stationsRepresented: number;
  selectionRule: string;
  candidatesConsidered: number;
}

/** What BART later published for one train: retrospective, never a model input. */
export interface RetrospectiveRecord {
  predictionId: string;
  tripRunId: string;
  stationId: string;
  finalPublishedEtaAt: string;
  finalPublishedEtaSeconds: number;
  realizedRevisionSeconds: number;
  modelErrorSeconds: number;
  predictedDirection: Direction;
  realizedDirection: Direction;
  directionMatch: boolean;
}

export interface ChangeRow {
  rank: number;
  predictionId: string;
  tripRunId: string;
  stationId: string;
  stationName: string;
  boardingGroupId: string;
  destination: string;
  lineName: string;
  routeShortName: string | null;
  horizonSeconds: number;
  bartPublishedEtaSeconds: number;
  bartPublishedEtaAt: string;
  predictedRevisionSeconds: number;
  modelAdjustedEtaSeconds: number;
  modelAdjustedEtaAt: string;
  finalPublishedEtaSeconds: number;
  finalPublishedEtaAt: string;
  realizedRevisionSeconds: number;
  modelErrorSeconds: number;
  directionMatch: boolean;
}

export interface StationRecord {
  predictionId: string;
  boardingGroupId: string;
  destination: string;
  lineName: string;
  routeShortName: string | null;
  horizonSeconds: number;
  predictedRevisionSeconds: number;
  realizedRevisionSeconds: number;
}

export interface NetworkStation {
  stationId: string;
  stationName: string;
  x: number;
  y: number;
  routes: string[];
  supportedForecastCount: number;
  largestAbsPredictedRevisionSeconds: number | null;
  medianPredictedRevisionSeconds: number | null;
  largestAbsRealizedRevisionSeconds: number | null;
  medianRealizedRevisionSeconds: number | null;
  largestPredictedRecord: StationRecord | null;
  largestRealizedRecord: StationRecord | null;
}

/** One kept train, for reading the map line by line. */
export interface MapTrain {
  predictionId: string;
  stationId: string;
  boardingGroupId: string;
  lineName: string;
  destination: string;
  horizonSeconds: number;
  predictedRevisionSeconds: number;
  /** Retrospective: what BART later published, minus BART's ETA at the snapshot. */
  realizedRevisionSeconds: number;
}

export interface NetworkRoute {
  routeId: string;
  routeShortName: string | null;
  color: string | null;
  stationIds: string[];
}

export interface Showcase {
  meta: ShowcaseMeta;
  retrospective: Map<string, RetrospectiveRecord>;
  changes: Record<Horizon, ChangeRow[]>;
  network: { width: number; height: number; routes: NetworkRoute[]; stations: NetworkStation[]; trains: MapTrain[] };
}

type Fields = Record<string, unknown>;

function obj(v: unknown, path: string): Fields {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) throw new DecodeError(path, 'expected an object');
  return v as Fields;
}
function str(v: unknown, path: string): string {
  if (typeof v !== 'string' || v === '') throw new DecodeError(path, 'expected a string');
  return v;
}
function strOrNull(v: unknown, path: string): string | null {
  return v === null ? null : str(v, path);
}
function int(v: unknown, path: string): number {
  if (typeof v !== 'number' || !Number.isInteger(v)) throw new DecodeError(path, 'expected an integer');
  return v;
}
function num(v: unknown, path: string): number {
  if (typeof v !== 'number' || !Number.isFinite(v)) throw new DecodeError(path, 'expected a number');
  return v;
}
function numOrNull(v: unknown, path: string): number | null {
  return v === null ? null : num(v, path);
}
function bool(v: unknown, path: string): boolean {
  if (typeof v !== 'boolean') throw new DecodeError(path, 'expected true or false');
  return v;
}
function time(v: unknown, path: string): string {
  const s = str(v, path);
  if (Number.isNaN(Date.parse(s))) throw new DecodeError(path, 'expected a timestamp');
  return s;
}
function list(v: unknown, path: string): unknown[] {
  if (!Array.isArray(v)) throw new DecodeError(path, 'expected a list');
  return v;
}
function direction(v: unknown, path: string): Direction {
  if (v !== 'later' && v !== 'earlier' && v !== 'unchanged') throw new DecodeError(path, 'expected a direction');
  return v;
}
function header(v: unknown, path: string, schema: string): Fields {
  const o = obj(v, path);
  if (o.schemaVersion !== schema) throw new DecodeError(`${path}.schemaVersion`, `expected ${schema}`);
  if (o.dataMode !== 'historical_replay') throw new DecodeError(`${path}.dataMode`, 'expected historical_replay');
  time(o.asOf, `${path}.asOf`);
  return o;
}

export function decodeShowcaseMeta(v: unknown): ShowcaseMeta {
  const o = header(v, 'showcase', 'showcase-1');
  const counts = obj(o.counts, 'showcase.counts');
  const selection = obj(o.selection, 'showcase.selection');
  return {
    asOf: time(o.asOf, 'showcase.asOf'),
    feedTimestamp: time(o.feedTimestamp, 'showcase.feedTimestamp'),
    serviceDate: str(o.serviceDate, 'showcase.serviceDate'),
    localTime: str(o.localTime, 'showcase.localTime'),
    modelVersion: str(o.modelVersion, 'showcase.modelVersion'),
    disclosure: str(o.disclosure, 'showcase.disclosure'),
    modelScope: str(o.modelScope, 'showcase.modelScope'),
    notLive: str(o.notLive, 'showcase.notLive'),
    includedRecords: int(counts.includedRecords, 'showcase.counts.includedRecords'),
    supportedForecasts: int(counts.supportedForecasts, 'showcase.counts.supportedForecasts'),
    boardEntries: int(counts.boardEntries, 'showcase.counts.boardEntries'),
    stationsRepresented: int(counts.stationsRepresented, 'showcase.counts.stationsRepresented'),
    selectionRule: str(selection.rule, 'showcase.selection.rule'),
    candidatesConsidered: int(selection.candidatesConsidered, 'showcase.selection.candidatesConsidered'),
  };
}

export function decodeRetrospective(v: unknown): Map<string, RetrospectiveRecord> {
  const o = header(v, 'retrospective', 'showcase-retrospective-1');
  const out = new Map<string, RetrospectiveRecord>();
  list(o.records, 'retrospective.records').forEach((item, i) => {
    const p = `retrospective.records[${i}]`;
    const r = obj(item, p);
    const record: RetrospectiveRecord = {
      predictionId: str(r.predictionId, `${p}.predictionId`),
      tripRunId: str(r.tripRunId, `${p}.tripRunId`),
      stationId: str(r.stationId, `${p}.stationId`),
      finalPublishedEtaAt: time(r.finalPublishedEtaAt, `${p}.finalPublishedEtaAt`),
      finalPublishedEtaSeconds: int(r.finalPublishedEtaSeconds, `${p}.finalPublishedEtaSeconds`),
      realizedRevisionSeconds: int(r.realizedRevisionSeconds, `${p}.realizedRevisionSeconds`),
      modelErrorSeconds: int(r.modelErrorSeconds, `${p}.modelErrorSeconds`),
      predictedDirection: direction(r.predictedDirection, `${p}.predictedDirection`),
      realizedDirection: direction(r.realizedDirection, `${p}.realizedDirection`),
      directionMatch: bool(r.directionMatch, `${p}.directionMatch`),
    };
    out.set(record.predictionId, record);
  });
  return out;
}

function changeRow(v: unknown, p: string): ChangeRow {
  const r = obj(v, p);
  return {
    rank: int(r.rank, `${p}.rank`),
    predictionId: str(r.predictionId, `${p}.predictionId`),
    tripRunId: str(r.tripRunId, `${p}.tripRunId`),
    stationId: str(r.stationId, `${p}.stationId`),
    stationName: str(r.stationName, `${p}.stationName`),
    boardingGroupId: str(r.boardingGroupId, `${p}.boardingGroupId`),
    destination: str(r.destination, `${p}.destination`),
    lineName: str(r.lineName, `${p}.lineName`),
    routeShortName: strOrNull(r.routeShortName, `${p}.routeShortName`),
    horizonSeconds: int(r.horizonSeconds, `${p}.horizonSeconds`),
    bartPublishedEtaSeconds: int(r.bartPublishedEtaSeconds, `${p}.bartPublishedEtaSeconds`),
    bartPublishedEtaAt: time(r.bartPublishedEtaAt, `${p}.bartPublishedEtaAt`),
    predictedRevisionSeconds: int(r.predictedRevisionSeconds, `${p}.predictedRevisionSeconds`),
    modelAdjustedEtaSeconds: int(r.modelAdjustedEtaSeconds, `${p}.modelAdjustedEtaSeconds`),
    modelAdjustedEtaAt: time(r.modelAdjustedEtaAt, `${p}.modelAdjustedEtaAt`),
    finalPublishedEtaSeconds: int(r.finalPublishedEtaSeconds, `${p}.finalPublishedEtaSeconds`),
    finalPublishedEtaAt: time(r.finalPublishedEtaAt, `${p}.finalPublishedEtaAt`),
    realizedRevisionSeconds: int(r.realizedRevisionSeconds, `${p}.realizedRevisionSeconds`),
    modelErrorSeconds: int(r.modelErrorSeconds, `${p}.modelErrorSeconds`),
    directionMatch: bool(r.directionMatch, `${p}.directionMatch`),
  };
}

export function decodeChanges(v: unknown): Record<Horizon, ChangeRow[]> {
  const o = header(v, 'largestChanges', 'showcase-largest-changes-1');
  const by = obj(o.byHorizon, 'largestChanges.byHorizon');
  const out = { '300': [], '600': [], '900': [] } as Record<Horizon, ChangeRow[]>;
  for (const h of HORIZONS) {
    if (by[h] === undefined) continue;
    out[h] = list(by[h], `largestChanges.byHorizon.${h}`).map((r, i) => changeRow(r, `largestChanges.byHorizon.${h}[${i}]`));
    if (out[h].some((r) => String(r.horizonSeconds) !== h)) throw new DecodeError(`largestChanges.byHorizon.${h}`, 'a row of another horizon');
  }
  return out;
}

function stationRecord(v: unknown, p: string): StationRecord | null {
  if (v === null) return null;
  const r = obj(v, p);
  return {
    predictionId: str(r.predictionId, `${p}.predictionId`),
    boardingGroupId: str(r.boardingGroupId, `${p}.boardingGroupId`),
    destination: str(r.destination, `${p}.destination`),
    lineName: str(r.lineName, `${p}.lineName`),
    routeShortName: strOrNull(r.routeShortName, `${p}.routeShortName`),
    horizonSeconds: int(r.horizonSeconds, `${p}.horizonSeconds`),
    predictedRevisionSeconds: int(r.predictedRevisionSeconds, `${p}.predictedRevisionSeconds`),
    realizedRevisionSeconds: int(r.realizedRevisionSeconds, `${p}.realizedRevisionSeconds`),
  };
}

export function decodeNetwork(v: unknown): Showcase['network'] {
  const o = header(v, 'networkMap', 'showcase-network-map-1');
  const box = list(o.viewBox, 'networkMap.viewBox').map((n, i) => num(n, `networkMap.viewBox[${i}]`));
  if (box.length !== 4) throw new DecodeError('networkMap.viewBox', 'expected four numbers');
  const routes = list(o.routes, 'networkMap.routes').map((item, i) => {
    const p = `networkMap.routes[${i}]`;
    const r = obj(item, p);
    return {
      routeId: str(r.routeId, `${p}.routeId`),
      routeShortName: strOrNull(r.routeShortName, `${p}.routeShortName`),
      color: strOrNull(r.color, `${p}.color`),
      stationIds: list(r.stationIds, `${p}.stationIds`).map((s, j) => str(s, `${p}.stationIds[${j}]`)),
    };
  });
  const stations = list(o.stations, 'networkMap.stations').map((item, i) => {
    const p = `networkMap.stations[${i}]`;
    const s = obj(item, p);
    return {
      stationId: str(s.stationId, `${p}.stationId`),
      stationName: str(s.stationName, `${p}.stationName`),
      x: num(s.x, `${p}.x`),
      y: num(s.y, `${p}.y`),
      routes: list(s.routes, `${p}.routes`).map((r, j) => str(r, `${p}.routes[${j}]`)),
      supportedForecastCount: int(s.supportedForecastCount, `${p}.supportedForecastCount`),
      largestAbsPredictedRevisionSeconds: numOrNull(s.largestAbsPredictedRevisionSeconds, `${p}.largestAbsPredictedRevisionSeconds`),
      medianPredictedRevisionSeconds: numOrNull(s.medianPredictedRevisionSeconds, `${p}.medianPredictedRevisionSeconds`),
      largestAbsRealizedRevisionSeconds: numOrNull(s.largestAbsRealizedRevisionSeconds, `${p}.largestAbsRealizedRevisionSeconds`),
      medianRealizedRevisionSeconds: numOrNull(s.medianRealizedRevisionSeconds, `${p}.medianRealizedRevisionSeconds`),
      largestPredictedRecord: stationRecord(s.largestPredictedRecord, `${p}.largestPredictedRecord`),
      largestRealizedRecord: stationRecord(s.largestRealizedRecord, `${p}.largestRealizedRecord`),
    };
  });
  const trains = list(o.trains, 'networkMap.trains').map((item, i) => {
    const p = `networkMap.trains[${i}]`;
    const r = obj(item, p);
    return {
      predictionId: str(r.predictionId, `${p}.predictionId`),
      stationId: str(r.stationId, `${p}.stationId`),
      boardingGroupId: str(r.boardingGroupId, `${p}.boardingGroupId`),
      lineName: str(r.lineName, `${p}.lineName`),
      destination: str(r.destination, `${p}.destination`),
      horizonSeconds: int(r.horizonSeconds, `${p}.horizonSeconds`),
      predictedRevisionSeconds: int(r.predictedRevisionSeconds, `${p}.predictedRevisionSeconds`),
      realizedRevisionSeconds: int(r.realizedRevisionSeconds, `${p}.realizedRevisionSeconds`),
    };
  });
  const [, , width = 0, height = 0] = box;
  return { width, height, routes, stations, trains };
}

/** The four files must describe one replay moment. */
export function assembleShowcase(meta: ShowcaseMeta, files: { retrospective: unknown; changes: unknown; network: unknown }): Showcase {
  for (const [name, body] of Object.entries(files)) {
    if (obj(body, name).asOf !== meta.asOf) throw new DecodeError(`${name}.asOf`, 'is not the showcase’s replay time');
  }
  return {
    meta,
    retrospective: decodeRetrospective(files.retrospective),
    changes: decodeChanges(files.changes),
    network: decodeNetwork(files.network),
  };
}
