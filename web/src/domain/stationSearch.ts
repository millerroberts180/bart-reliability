import type { Station } from './types';

/** Ordinary search results shown at once; "Browse all stations" shows the rest. */
export const SEARCH_RESULT_LIMIT = 8;

/**
 * Common names riders type that are not in the station name. Deliberately tiny: each
 * station's ID (its BART abbreviation, e.g. "EMBR") is also searchable, so only the
 * two airport codes need listing here.
 */
const COMMON_ALIASES: Record<string, string[]> = {
  SFIA: ['SFO'],
  OAKL: ['OAK'],
};

export function stationAliases(station: Station): string[] {
  return [station.id, ...(COMMON_ALIASES[station.id] ?? [])];
}

const normalize = (text: string) =>
  text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '') // "José" matches "jose"
    .toLowerCase()
    .trim();

/** Lower is better; null means no match. */
function rank(station: Station, query: string): number | null {
  const name = normalize(station.name);
  const aliases = stationAliases(station).map(normalize);
  if (aliases.includes(query)) return 0; // "sfo", "embr"
  if (name.startsWith(query)) return 1;
  if (name.split(/[\s/]+/).some((word) => word.startsWith(query))) return 2; // "oakland" → "12th Street / Oakland City Center"
  if (aliases.some((alias) => alias.startsWith(query))) return 3;
  if (name.includes(query)) return 4;
  return null;
}

export interface SearchResult {
  /** The best matches, at most `limit`. */
  stations: Station[];
  /** How many stations matched in total. */
  total: number;
}

/** Case-insensitive match on station name and aliases, best matches first, then A–Z. */
export function searchStations(stations: Station[], query: string, limit = SEARCH_RESULT_LIMIT): SearchResult {
  const q = normalize(query);
  if (!q) return { stations: [], total: 0 };
  const matches = stations
    .map((station) => ({ station, score: rank(station, q) }))
    .filter((m): m is { station: Station; score: number } => m.score !== null)
    .sort((a, b) => a.score - b.score || a.station.name.localeCompare(b.station.name));
  return { stations: matches.slice(0, limit).map((m) => m.station), total: matches.length };
}

/** Every station, alphabetical, for "Browse all stations". */
export function alphabetical(stations: Station[]): Station[] {
  return [...stations].sort((a, b) => a.name.localeCompare(b.name, 'en', { numeric: true }));
}
