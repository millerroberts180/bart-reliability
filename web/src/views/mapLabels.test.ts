import { describe, expect, it } from 'vitest';
import { keyStations, lineEnds, stationFigures } from '../domain/mapData';
import { markRadius } from '../domain/mapScale';
import { decodeNetwork, type NetworkStation } from '../domain/showcase';
import { readShowcaseFile } from '../test/publishedShowcase';
import { labelBox, LABEL_FONT, mapLabel, placeLabels, type Placement } from './mapLabels';

const network = async () => decodeNetwork(await readShowcaseFile('network-map.json'));

type Named = { id: string; box: ReturnType<typeof labelBox> };

/** Pairs of names whose boxes (glyphs plus margin) overlap. */
function overlaps(named: Named[]): string[] {
  const out: string[] = [];
  named.forEach(({ id: i, box: a }, k) =>
    named.slice(k + 1).forEach(({ id: j, box: b }) => {
      if (Math.min(a.x1, b.x1) > Math.max(a.x0, b.x0) && Math.min(a.y1, b.y1) > Math.max(a.y0, b.y0)) out.push(`${i}|${j}`);
    }),
  );
  return out;
}

function boxesOf(
  stations: NetworkStation[],
  placed: Map<string, Placement>,
  radius: (s: NetworkStation) => number,
  font: number,
  margin?: number,
): Named[] {
  return stations.flatMap((s) => {
    const place = placed.get(s.stationId);
    return place ? [{ id: s.stationId, box: labelBox(s, mapLabel(s), place, radius(s), font, margin) }] : [];
  });
}

describe('station names on the network map', () => {
  // At full size a name keeps the side that overlaps least when none is clear; the glyphs
  // themselves must still never overlap.
  it('never overlap at full size, for every line and both modes', async () => {
    const net = await network();
    for (const line of [null, 'Red', 'Orange', 'Yellow', 'Green', 'Blue'] as const) {
      const figures = stationFigures(net.trains, line);
      for (const pick of ['medianPredicted', 'medianRealized'] as const) {
        const radius = (s: NetworkStation) => markRadius(figures.get(s.stationId)?.[pick] ?? null);
        const placed = placeLabels(net.stations, () => true, radius, net.width, { height: net.height });
        expect(placed.size).toBe(net.stations.length);
        expect(overlaps(boxesOf(net.stations, placed, radius, LABEL_FONT, 0)), `${line ?? 'All'} ${pick}`).toEqual([]);
      }
    }
  });

  it('on a phone, name every line end and leave out a name rather than let it touch another', async () => {
    const net = await network();
    const keys = keyStations(net.routes);
    const ends = lineEnds(net.routes);
    expect([...ends].sort()).toEqual(['ANTC', 'BERY', 'DUBL', 'MLBR', 'OAKL', 'RICH']);
    const figures = stationFigures(net.trains, null);
    const radius = (s: NetworkStation) => markRadius(figures.get(s.stationId)?.medianPredicted ?? null);
    for (const font of [38, 44]) {
      const placed = placeLabels(net.stations, (s) => keys.has(s.stationId), radius, net.width, {
        font,
        height: net.height,
        dropOnCollision: true,
        early: ends,
      });
      for (const id of ends) expect(placed.has(id), `${id} at ${font}`).toBe(true);
      const named = boxesOf(net.stations, placed, radius, font);
      expect(overlaps(named)).toEqual([]);
      for (const { box: b } of named) {
        expect(b.x0).toBeGreaterThanOrEqual(0);
        expect(b.x1).toBeLessThanOrEqual(net.width);
        expect(b.y0).toBeGreaterThanOrEqual(0);
      }
    }
  });

  it('always name the selected station, first', async () => {
    const net = await network();
    const placed = placeLabels(net.stations, (s) => s.stationId === 'MONT', () => 10, net.width, {
      font: 44,
      dropOnCollision: true,
      first: 'MONT',
    });
    expect([...placed.keys()]).toEqual(['MONT']);
  });
});
