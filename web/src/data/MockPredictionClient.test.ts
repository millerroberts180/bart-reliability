import { describe, expect, it } from 'vitest';
import { classifyStability } from '../domain/eta';
import { API_RECORDING } from '../test/fakeApi';
import { NETWORK_STATIONS } from './fixtures/network';
import { SIMULATED_STATIONS, SIMULATED_TRAINS } from './fixtures/simulated';
import { hasForecast, type Station } from '../domain/types';
import { MockPredictionClient } from './MockPredictionClient';
import { PredictionClientError } from './PredictionClient';

const NOW = new Date('2026-10-13T17:00:00Z');
const clock = () => NOW;

describe('MockPredictionClient', () => {
  it('returns identical responses for the same scenario and clock', async () => {
    const a = await new MockPredictionClient({ now: clock }).getPredictions('EMBR', 'to-WOAK');
    const b = await new MockPredictionClient({ now: clock }).getPredictions('EMBR', 'to-WOAK');
    expect(a).toEqual(b);
  });

  it('lists stations, each with selectable boarding groups', async () => {
    const stations = await new MockPredictionClient().listStations();
    expect(stations.map((s) => s.name)).toEqual(['Embarcadero', 'MacArthur', 'Balboa Park']);
    for (const station of stations) expect(station.boardingGroups.length).toBeGreaterThan(0);
  });

  it('returns different trains for different boarding groups, with their platforms', async () => {
    const client = new MockPredictionClient({ now: clock });
    const east = await client.getPredictions('EMBR', 'to-WOAK');
    const west = await client.getPredictions('EMBR', 'to-MONT');
    expect(east.trains.map((t) => t.headsign)).not.toEqual(west.trains.map((t) => t.headsign));
    expect(east).toMatchObject({ boardingGroupId: 'to-WOAK', unplacedTrainCount: 0, terminatingTrainCount: 0 });
    expect(new Set(east.trains.map((t) => t.platform))).toEqual(new Set(['2']));
    expect(new Set(west.trains.map((t) => t.platform))).toEqual(new Set(['1']));
  });

  it('builds consistent predictions from the feed snapshot', async () => {
    const response = await new MockPredictionClient({ now: clock }).getPredictions('EMBR', 'to-WOAK');
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
    const response = await new MockPredictionClient({ scenario: 'no-interval', now: clock }).getPredictions('EMBR', 'to-WOAK');
    expect(response.trains.length).toBeGreaterThan(0);
    for (const train of response.trains) {
      expect(train.predictionStatus).toBe('ok');
      expect(train.revisionInterval).toBeNull();
      expect(train.predictedRevisionSeconds).not.toBeNull();
    }
  });

  it('serves BART ETAs without model numbers in the eta-only scenario', async () => {
    const response = await new MockPredictionClient({ scenario: 'eta-only', now: clock }).getPredictions('EMBR', 'to-WOAK');
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

  it('forecasts only trains near 5, 10 or 15 minutes away in the model-horizon scenario', async () => {
    const response = await new MockPredictionClient({ scenario: 'model-horizon', now: clock }).getPredictions(
      'EMBR',
      'to-WOAK',
    );
    expect(response.trains.map((t) => [t.currentEtaSeconds, t.predictionStatus])).toEqual([
      [130, 'outside_model_horizon'],
      [370, 'outside_model_horizon'],
      [610, 'ok'],
      [905, 'ok'],
    ]);
  });

  it('serves an old snapshot in the stale scenario', async () => {
    const response = await new MockPredictionClient({ scenario: 'stale', now: clock }).getPredictions('EMBR', 'to-WOAK');
    expect(NOW.getTime() - Date.parse(response.feedTimestamp)).toBeGreaterThan(120_000);
  });

  it('serves no trains in the empty scenario', async () => {
    const response = await new MockPredictionClient({ scenario: 'empty', now: clock }).getPredictions('EMBR', 'to-WOAK');
    expect(response.trains).toEqual([]);
  });

  it('rejects in the error scenario and for unknown stations', async () => {
    await expect(new MockPredictionClient({ scenario: 'error' }).getPredictions('EMBR', 'to-WOAK')).rejects.toMatchObject({
      code: 'unavailable',
    });
    await expect(new MockPredictionClient().getPredictions('NOPE', 'to-WOAK')).rejects.toBeInstanceOf(PredictionClientError);
  });

  it('can abort a request that never resolves', async () => {
    const controller = new AbortController();
    const pending = new MockPredictionClient({ scenario: 'loading' }).getPredictions('EMBR', 'to-WOAK', controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });
});

describe('MockPredictionClient history', () => {
  const selectable = SIMULATED_STATIONS.flatMap((station) =>
    station.boardingGroups.map((group) => ({ stationId: station.id, groupId: group.id })),
  );

  it('gives every selectable train a history that ends exactly at its prediction', async () => {
    for (const scenario of ['live', 'stale'] as const) {
      const client = new MockPredictionClient({ scenario, now: clock });
      for (const { stationId, groupId } of selectable) {
        const response = await client.getPredictions(stationId, groupId);
        expect(response.trains).toHaveLength(SIMULATED_TRAINS[`${stationId}:${groupId}`]?.length ?? -1);
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
      await client.getPredictions('EMBR', 'to-WOAK');
      return client.getPredictionHistory(id);
    };
    expect(await load('EMBR:to-WOAK:1782')).toEqual(await load('EMBR:to-WOAK:1782'));
    expect(await load('EMBR:to-WOAK:1782')).not.toEqual(await load('EMBR:to-WOAK:2105'));
  });

  it('serves the forced history states', async () => {
    const forHistory = async (historyScenario: 'single' | 'none' | 'gaps') => {
      const client = new MockPredictionClient({ historyScenario, now: clock });
      await client.getPredictions('EMBR', 'to-WOAK');
      return client.getPredictionHistory('EMBR:to-WOAK:1782');
    };
    expect(await forHistory('single')).toHaveLength(1);
    expect(await forHistory('none')).toEqual([]);
    expect(await forHistory('gaps')).toHaveLength(12);
    await expect(
      new MockPredictionClient({ historyScenario: 'error' }).getPredictionHistory('EMBR:to-WOAK:1782'),
    ).rejects.toMatchObject({ code: 'unavailable' });
  });
});

describe('MockPredictionClient full network', () => {
  const client = () => new MockPredictionClient({ network: 'full', now: clock });

  it('serves all 50 stations, terminals with a single boarding group', async () => {
    const stations = await client().listStations();
    expect(stations).toHaveLength(50);
    const antioch = stations.find((s) => s.name === 'Antioch');
    expect(antioch?.boardingGroups).toHaveLength(1);
    expect(antioch?.endOfLine).toBe(true);
    expect(stations.find((s) => s.id === 'EMBR')?.boardingGroups).toHaveLength(2);
    expect(stations.find((s) => s.id === 'EMBR')?.endOfLine).toBe(false);
  });

  it('groups Hayward by platform side, never mixing Berryessa with Daly City or Richmond', async () => {
    const c = client();
    const hayward = (await c.listStations()).find((s) => s.id === 'HAYW');
    expect(hayward?.boardingGroups.map((g) => [g.id, g.platform, g.destinations])).toEqual([
      ['to-SHAY', '1', ['Berryessa / North San Jose']],
      ['to-BAYF', '2', ['Richmond', 'Daly City']],
    ]);
    const south = await c.getPredictions('HAYW', 'to-SHAY');
    const north = await c.getPredictions('HAYW', 'to-BAYF');
    expect(new Set(south.trains.map((t) => t.headsign))).toEqual(new Set(['Berryessa / North San Jose']));
    expect(new Set(north.trains.map((t) => t.headsign))).toEqual(new Set(['Richmond', 'Daly City']));
  });

  it('lists 20 upcoming trains per station and boarding group, in time order, deterministically', async () => {
    const a = await client().getPredictions('EMBR', 'to-WOAK');
    const b = await client().getPredictions('EMBR', 'to-WOAK');
    expect(a).toEqual(b);
    expect(a.trains).toHaveLength(20);
    const etas = a.trains.map((t) => t.currentEtaSeconds);
    expect(etas).toEqual([...etas].sort((x, y) => x - y));
    expect(new Set(a.trains.map((t) => t.predictionId)).size).toBe(20);
  });

  it('has history for generated trains, ending at their prediction', async () => {
    const c = client();
    const response = await c.getPredictions('ANTC', 'to-PCTR');
    const train = response.trains[0];
    const points = await c.getPredictionHistory(train?.predictionId ?? '');
    expect(points.at(-1)?.publishedEtaAt).toBe(train?.currentEtaAt);
  });

  it('leaves the demo set as the default', async () => {
    expect(await new MockPredictionClient().listStations()).toHaveLength(3);
  });
});

describe('MockPredictionClient boarding-group order', () => {
  // The API lists a station's groups in platform order, then by group ID
  // (docs/boarding_groups.md), and the page selects the first. The mock must list them the
  // same way, so simulated development and HTTP mode open on the same group. Only the order
  // of IDs is compared; simulated trains and numbers are not expected to match replay data.
  const groupIds = (stations: { id: string; boardingGroups: { id: string }[] }[]) =>
    Object.fromEntries(stations.map((s) => [s.id, s.boardingGroups.map((g) => g.id)]));
  const recorded = groupIds(API_RECORDING.responses['/api/v1/stations'] as Station[]);
  const network = groupIds(NETWORK_STATIONS);
  const demo = groupIds(SIMULATED_STATIONS);

  it('orders the full network’s groups exactly as the recorded API does, wherever they overlap', () => {
    const shared = Object.keys(recorded).filter((id) => id in network);
    expect(shared).toEqual(['ANTC', 'CAST', 'DBRK', 'HAYW']);
    for (const id of shared) expect(network[id], id).toEqual(recorded[id]);
  });

  it('orders the demo stations’ groups as the full network does (the API’s rule)', () => {
    expect(Object.keys(demo)).toEqual(['EMBR', 'MCAR', 'BALB']);
    for (const id of Object.keys(demo)) expect(demo[id], id).toEqual(network[id]);
    expect(demo.EMBR?.[0]).toBe('to-MONT'); // platform 1, before the East Bay's platform 2
    expect(demo.BALB?.[0]).toBe('to-DALY');
  });

  it('gives the demo and the full network the same platforms where a group has one', () => {
    const platforms = (stations: Station[]) =>
      Object.fromEntries(stations.flatMap((s) => s.boardingGroups.map((g) => [`${s.id}:${g.id}`, g.platform])));
    const full = platforms(NETWORK_STATIONS);
    for (const [key, platform] of Object.entries(platforms(SIMULATED_STATIONS))) expect(platform, key).toBe(full[key]);
  });
});
