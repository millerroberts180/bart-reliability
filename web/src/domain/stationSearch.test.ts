import { describe, expect, it } from 'vitest';
import { NETWORK_STATIONS } from '../data/fixtures/network';
import { alphabetical, SEARCH_RESULT_LIMIT, searchStations } from './stationSearch';

const names = (query: string) => searchStations(NETWORK_STATIONS, query).stations.map((s) => s.name);

describe('searchStations', () => {
  it('matches station names case-insensitively, prefix first', () => {
    expect(names('EMBARC')).toEqual(['Embarcadero']);
    expect(names('oakland')[0]).toBe('Oakland International Airport');
    expect(names('oakland')).toContain('12th Street / Oakland City Center'); // a later word
  });

  it('matches common aliases and BART station abbreviations', () => {
    expect(names('SFO')[0]).toBe('San Francisco International Airport');
    expect(names('oak')[0]).toBe('Oakland International Airport');
    expect(names('embr')[0]).toBe('Embarcadero');
  });

  it('ignores accents and spacing around the query', () => {
    expect(names('  san josé ')).toContain('Berryessa / North San Jose');
  });

  it(`returns at most ${SEARCH_RESULT_LIMIT} results with the full count`, () => {
    const result = searchStations(NETWORK_STATIONS, 'st');
    expect(result.stations).toHaveLength(SEARCH_RESULT_LIMIT);
    expect(result.total).toBeGreaterThan(SEARCH_RESULT_LIMIT);
  });

  it('returns nothing for an empty or unmatched query', () => {
    expect(searchStations(NETWORK_STATIONS, '   ')).toEqual({ stations: [], total: 0 });
    expect(searchStations(NETWORK_STATIONS, 'zzz')).toEqual({ stations: [], total: 0 });
  });

  it('lists every station alphabetically, numbers in numeric order', () => {
    const all = alphabetical(NETWORK_STATIONS).map((s) => s.name);
    expect(all).toHaveLength(50);
    expect(all.slice(0, 3)).toEqual(['12th Street / Oakland City Center', '16th Street / Mission', '19th Street Oakland']);
  });
});
