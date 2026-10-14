import { describe, expect, it } from 'vitest';
import { classifyStability } from '../domain/eta';
import { HttpPredictionClient } from './HttpPredictionClient';
import { MockPredictionClient } from './MockPredictionClient';
import { PredictionClientError } from './PredictionClient';

const NOW = new Date('2026-10-13T17:00:00Z');
const clock = () => NOW;

describe('MockPredictionClient', () => {
  it('returns identical responses for the same scenario and clock', async () => {
    const a = await new MockPredictionClient({ now: clock }).getPredictions('EMBR', '0');
    const b = await new MockPredictionClient({ now: clock }).getPredictions('EMBR', '0');
    expect(a).toEqual(b);
  });

  it('lists stations, each with selectable directions', async () => {
    const stations = await new MockPredictionClient().listStations();
    expect(stations.map((s) => s.name)).toEqual(['Embarcadero', 'MacArthur', 'Balboa Park']);
    for (const station of stations) expect(station.directions.length).toBeGreaterThan(0);
  });

  it('returns different trains for different directions', async () => {
    const client = new MockPredictionClient({ now: clock });
    const east = await client.getPredictions('EMBR', '0');
    const west = await client.getPredictions('EMBR', '1');
    expect(east.trains.map((t) => t.headsign)).not.toEqual(west.trains.map((t) => t.headsign));
  });

  it('builds consistent predictions from the feed snapshot', async () => {
    const response = await new MockPredictionClient({ now: clock }).getPredictions('EMBR', '0');
    expect(Date.parse(response.feedTimestamp)).toBeLessThan(NOW.getTime());
    expect(response.model.simulated).toBe(true);
    for (const train of response.trains) {
      expect(Date.parse(train.currentEtaAt) - Date.parse(response.feedTimestamp)).toBe(train.currentEtaSeconds * 1000);
      expect(train.stability).toBe(classifyStability(train.revisionProbability));
      expect(train.revisionInterval.lowerSeconds).toBeLessThanOrEqual(train.predictedRevisionSeconds);
      expect(train.revisionInterval.upperSeconds).toBeGreaterThanOrEqual(train.predictedRevisionSeconds);
    }
  });

  it('serves an old snapshot in the stale scenario', async () => {
    const response = await new MockPredictionClient({ scenario: 'stale', now: clock }).getPredictions('EMBR', '0');
    expect(NOW.getTime() - Date.parse(response.feedTimestamp)).toBeGreaterThan(120_000);
  });

  it('serves no trains in the empty scenario', async () => {
    const response = await new MockPredictionClient({ scenario: 'empty', now: clock }).getPredictions('EMBR', '0');
    expect(response.trains).toEqual([]);
  });

  it('rejects in the error scenario and for unknown stations', async () => {
    await expect(new MockPredictionClient({ scenario: 'error' }).getPredictions('EMBR', '0')).rejects.toMatchObject({
      code: 'unavailable',
    });
    await expect(new MockPredictionClient().getPredictions('NOPE', '0')).rejects.toBeInstanceOf(PredictionClientError);
  });

  it('can abort a request that never resolves', async () => {
    const controller = new AbortController();
    const pending = new MockPredictionClient({ scenario: 'loading' }).getPredictions('EMBR', '0', controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });
});

describe('HttpPredictionClient placeholder', () => {
  it('maps methods to the provisional endpoints without making requests', async () => {
    const client = new HttpPredictionClient('https://api.example.test/');
    expect(client.endpoint('/predictions', { station_id: 'EMBR', direction_id: '0' })).toBe(
      'https://api.example.test/api/v1/predictions?station_id=EMBR&direction_id=0',
    );
    await expect(client.getPredictions('EMBR', '0')).rejects.toMatchObject({ code: 'not_implemented' });
  });
});
