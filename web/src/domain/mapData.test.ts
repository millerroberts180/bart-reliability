import { describe, expect, it } from 'vitest';
import { readShowcaseFile } from '../test/publishedShowcase';
import { keyStations, lineOf, linesWithTrains, stationFigures, stationOnLine } from './mapData';
import { decodeNetwork } from './showcase';

const network = async () => decodeNetwork(await readShowcaseFile('network-map.json'));

describe('map figures from the train records', () => {
  it('equal network-map.json’s own station figures for every line together', async () => {
    const net = await network();
    const figures = stationFigures(net.trains, null);
    for (const s of net.stations) {
      const f = figures.get(s.stationId);
      expect(f?.count ?? 0, s.stationId).toBe(s.supportedForecastCount);
      if (!f) continue;
      expect(f.medianPredicted).toBe(s.medianPredictedRevisionSeconds);
      expect(f.medianRealized).toBe(s.medianRealizedRevisionSeconds);
      expect(f.largestPredicted?.predictionId).toBe(s.largestPredictedRecord?.predictionId);
      expect(f.largestRealized?.predictionId).toBe(s.largestRealizedRecord?.predictionId);
    }
  });

  it('keep only one line’s trains when a line is chosen', async () => {
    const net = await network();
    expect(linesWithTrains(net.trains)).toEqual(['Red', 'Orange', 'Yellow', 'Green', 'Blue']);
    const yellow = stationFigures(net.trains, 'Yellow');
    const yellowTrains = net.trains.filter((t) => lineOf(t.lineName) === 'Yellow');
    expect([...yellow.values()].reduce((n, f) => n + f.count, 0)).toBe(yellowTrains.length);
    for (const id of yellow.keys()) {
      const station = net.stations.find((s) => s.stationId === id);
      expect(station && stationOnLine(station, 'Yellow'), id).toBe(true);
    }
  });

  it('names where lines meet or end as key stations, and only those', async () => {
    const keys = keyStations((await network()).routes);
    for (const id of ['RICH', 'ANTC', 'MLBR', 'BERY', 'DUBL', 'MCAR', '12TH', 'WOAK', 'LAKE', 'BAYF', 'COLS']) {
      expect(keys.has(id), id).toBe(true);
    }
    for (const id of ['ASHB', 'POWL', 'FRMT', 'CONC']) expect(keys.has(id), id).toBe(false);
  });
});
