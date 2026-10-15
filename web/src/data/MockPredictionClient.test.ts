import { describe, expect, it } from 'vitest';
import { classifyStability } from '../domain/eta';
import { SIMULATED_STATIONS, SIMULATED_TRAINS } from './fixtures/simulated';
import { hasForecast } from '../domain/types';
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
    expect(response.dataProvenance).toBe('simulated');
    expect(response.replay).toBeNull();
    for (const train of response.trains) {
      expect(Date.parse(train.currentEtaAt) - Date.parse(response.feedTimestamp)).toBe(train.currentEtaSeconds * 1000);
      if (!hasForecast(train) || !train.revisionInterval) throw new Error('live fixtures all have a forecast and range');
      expect(train.stability).toBe(classifyStability(train.revisionProbability));
      expect(train.revisionInterval.lowerSeconds).toBeLessThanOrEqual(train.predictedRevisionSeconds);
      expect(train.revisionInterval.upperSeconds).toBeGreaterThanOrEqual(train.predictedRevisionSeconds);
    }
  });

  it('serves forecasts without a range in the no-interval scenario', async () => {
    const response = await new MockPredictionClient({ scenario: 'no-interval', now: clock }).getPredictions('EMBR', '0');
    expect(response.trains.length).toBeGreaterThan(0);
    for (const train of response.trains) {
      expect(train.predictionStatus).toBe('ok');
      expect(train.revisionInterval).toBeNull();
      expect(train.predictedRevisionSeconds).not.toBeNull();
    }
  });

  it('serves BART ETAs without model numbers in the eta-only scenario', async () => {
    const response = await new MockPredictionClient({ scenario: 'eta-only', now: clock }).getPredictions('EMBR', '0');
    expect(response.trains.length).toBeGreaterThan(0);
    for (const train of response.trains) {
      expect(train.predictionStatus).toBe('outside_model_horizon');
      expect([train.predictedRevisionSeconds, train.revisionInterval, train.revisionProbability, train.stability]).toEqual([
        null,
        null,
        null,
        null,
      ]);
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

describe('MockPredictionClient history', () => {
  const selectable = SIMULATED_STATIONS.flatMap((station) =>
    station.directions.map((direction) => ({ stationId: station.id, directionId: direction.id })),
  );

  it('gives every selectable train a history that ends exactly at its prediction', async () => {
    for (const scenario of ['live', 'stale'] as const) {
      const client = new MockPredictionClient({ scenario, now: clock });
      for (const { stationId, directionId } of selectable) {
        const response = await client.getPredictions(stationId, directionId);
        expect(response.trains).toHaveLength(SIMULATED_TRAINS[`${stationId}:${directionId}`]?.length ?? -1);
        for (const train of response.trains) {
          const points = await client.getPredictionHistory(train.predictionId);
          const last = points[points.length - 1];
          expect(last?.feedTimestamp).toBe(response.feedTimestamp);
          expect(last?.publishedEtaAt).toBe(train.currentEtaAt);
          for (const p of points) {
            // No observation after the prediction's snapshot, and internally consistent seconds.
            expect(Date.parse(p.feedTimestamp)).toBeLessThanOrEqual(Date.parse(response.feedTimestamp));
            expect((Date.parse(p.publishedEtaAt) - Date.parse(p.feedTimestamp)) / 1000).toBe(p.publishedEtaSeconds);
            expect(p.publishedEtaSeconds).toBeGreaterThan(0);
          }
        }
      }
    }
  });

  it('is deterministic and differs between trains', async () => {
    const load = async (id: string) => {
      const client = new MockPredictionClient({ now: clock });
      await client.getPredictions('EMBR', '0');
      return client.getPredictionHistory(id);
    };
    expect(await load('EMBR:0:1782')).toEqual(await load('EMBR:0:1782'));
    expect(await load('EMBR:0:1782')).not.toEqual(await load('EMBR:0:2105'));
  });

  it('serves the forced history states', async () => {
    const forHistory = async (historyScenario: 'single' | 'none' | 'gaps') => {
      const client = new MockPredictionClient({ historyScenario, now: clock });
      await client.getPredictions('EMBR', '0');
      return client.getPredictionHistory('EMBR:0:1782');
    };
    expect(await forHistory('single')).toHaveLength(1);
    expect(await forHistory('none')).toEqual([]);
    expect(await forHistory('gaps')).toHaveLength(12);
    await expect(
      new MockPredictionClient({ historyScenario: 'error' }).getPredictionHistory('EMBR:0:1782'),
    ).rejects.toMatchObject({ code: 'unavailable' });
  });
});
