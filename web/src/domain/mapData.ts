// Station figures for the network map, computed from the showcase's train records, for
// every line together or for one line. With every line they equal network-map.json's own
// station figures (src/domain/mapData.test.ts).

import type { MapTrain, NetworkRoute, NetworkStation } from './showcase';

export const LINE_ORDER = ['Red', 'Orange', 'Yellow', 'Green', 'Blue'] as const;
export type Line = (typeof LINE_ORDER)[number];

/** "Yellow line" -> "Yellow"; null for a line the map does not offer as a filter. */
export function lineOf(lineName: string): Line | null {
  const first = lineName.split(' ')[0];
  return LINE_ORDER.find((l) => l === first) ?? null;
}

/** The lines that have trains in this replay, in the map's order. */
export function linesWithTrains(trains: MapTrain[]): Line[] {
  const present = new Set(trains.map((t) => lineOf(t.lineName)));
  return LINE_ORDER.filter((l) => present.has(l));
}

/** A route ("Red-N") belongs to a line ("Red"). */
export function routeOnLine(route: NetworkRoute, line: Line): boolean {
  return (route.routeShortName ?? '').split('-')[0] === line;
}

export interface StationFigures {
  count: number;
  medianPredicted: number | null;
  medianRealized: number | null;
  largestPredicted: MapTrain | null;
  largestRealized: MapTrain | null;
}

function median(values: number[]): number | null {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? (s[mid] ?? null) : ((s[mid - 1] ?? 0) + (s[mid] ?? 0)) / 2;
}

/** The train with the largest absolute value; ties go to the lower predictionId, as in Python. */
function largest(trains: MapTrain[], value: (t: MapTrain) => number): MapTrain | null {
  return (
    [...trains].sort((a, b) => Math.abs(value(b)) - Math.abs(value(a)) || a.predictionId.localeCompare(b.predictionId))[0] ??
    null
  );
}

export function stationFigures(trains: MapTrain[], line: Line | null): Map<string, StationFigures> {
  const byStation = new Map<string, MapTrain[]>();
  for (const t of trains) {
    if (line && lineOf(t.lineName) !== line) continue;
    byStation.set(t.stationId, [...(byStation.get(t.stationId) ?? []), t]);
  }
  const out = new Map<string, StationFigures>();
  for (const [id, ts] of byStation) {
    out.set(id, {
      count: ts.length,
      medianPredicted: median(ts.map((t) => t.predictedRevisionSeconds)),
      medianRealized: median(ts.map((t) => t.realizedRevisionSeconds)),
      largestPredicted: largest(ts, (t) => t.predictedRevisionSeconds),
      largestRealized: largest(ts, (t) => t.realizedRevisionSeconds),
    });
  }
  return out;
}

/** Stations where lines meet or end: always labelled, even on a small screen. */
export function keyStations(routes: NetworkRoute[]): Set<string> {
  return new Set([...neighboursOf(routes)].filter(([, n]) => n.size !== 2).map(([id]) => id));
}

/** Stations where a line ends: one neighbour on every route through them. */
export function lineEnds(routes: NetworkRoute[]): Set<string> {
  return new Set([...neighboursOf(routes)].filter(([, n]) => n.size === 1).map(([id]) => id));
}

function neighboursOf(routes: NetworkRoute[]): Map<string, Set<string>> {
  const neighbours = new Map<string, Set<string>>();
  for (const r of routes) {
    r.stationIds.forEach((id, i) => {
      const set = neighbours.get(id) ?? new Set<string>();
      const prev = r.stationIds[i - 1];
      const next = r.stationIds[i + 1];
      if (prev) set.add(prev);
      if (next) set.add(next);
      neighbours.set(id, set);
    });
  }
  return neighbours;
}

export function stationOnLine(station: NetworkStation, line: Line | null): boolean {
  return !line || station.routes.some((r) => r.split('-')[0] === line);
}
