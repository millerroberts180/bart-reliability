// Where each station's name sits beside its mark on the network schematic. A greedy pass,
// busiest stations first, puts each name on the first side where it overlaps no other
// name or mark and stays inside the map; failing that, on the side that overlaps least,
// or (when the map is drawn small) nowhere. Offsets follow each mark's radius, so a
// large bubble never covers its own name.
import type { NetworkStation } from '../domain/showcase';

export type Placement = 'right' | 'left' | 'above' | 'below' | 'above-left' | 'above-right' | 'below-left' | 'below-right';
const ORDER: readonly Placement[] = ['right', 'left', 'above', 'below', 'above-left', 'above-right', 'below-left', 'below-right'];

// Hand-placed in the Oakland and downtown San Francisco core, where every side of a mark
// is near another name. On a full-size map they are placed first and kept wherever the
// bubbles' sizes put them; the greedy pass then works around them.
const PREFERRED: Record<string, Placement> = {
  WOAK: 'above-left',
  MONT: 'right',
  POWL: 'right',
  OAKL: 'below',
  SANL: 'below-left',
};

/** Label size in viewBox units on a wide screen (Schibsted Grotesk: about 0.56em per character). */
export const LABEL_FONT = 21;

// Map labels use each station's first name part; the two airport stations get short forms.
// Two core names take two lines, so they fit beside the bubbles around them whatever size
// those bubbles are drawn.
const SHORT_LABELS: Record<string, string[]> = {
  SFIA: ['SFO Airport'],
  OAKL: ['Oakland', 'Airport'],
  WOAK: ['West', 'Oakland'],
};

/** The lines of a station's name on the map. */
export function mapLabel(station: NetworkStation): string[] {
  return SHORT_LABELS[station.stationId] ?? [station.stationName.split(' / ')[0] ?? station.stationName];
}

/** Line spacing of a multi-line name, as a multiple of the font size. */
export const LINE_HEIGHT = 1.1;

interface Box {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** Where a name's first baseline sits relative to its mark. */
export function labelOffset(
  place: Placement,
  radius = 8,
  font = LABEL_FONT,
  lines = 1,
): { x: number; y: number; textAnchor: 'start' | 'end' | 'middle'; fontSize: number } {
  const gap = radius + 6;
  const side = radius * 0.7;
  const extra = (lines - 1) * font * LINE_HEIGHT;
  const up = -gap - 2 - extra;
  const down = gap + font * 0.8;
  const middle = font * 0.35 - extra / 2;
  switch (place) {
    case 'left':
      return { x: -gap, y: middle, textAnchor: 'end', fontSize: font };
    case 'above':
      return { x: 0, y: up, textAnchor: 'middle', fontSize: font };
    case 'below':
      return { x: 0, y: down, textAnchor: 'middle', fontSize: font };
    case 'above-left':
      return { x: -side, y: up, textAnchor: 'end', fontSize: font };
    case 'above-right':
      return { x: side, y: up, textAnchor: 'start', fontSize: font };
    case 'below-left':
      return { x: -side, y: down, textAnchor: 'end', fontSize: font };
    case 'below-right':
      return { x: side, y: down, textAnchor: 'start', fontSize: font };
    default:
      return { x: gap, y: middle, textAnchor: 'start', fontSize: font };
  }
}

// The glyphs' extent (cap height above the baseline, descenders below when the name has
// any) plus a margin, so two names that would merely touch count as overlapping.
const DESCENDERS = /[gjpqy,]/;

export function labelBox(
  s: NetworkStation,
  lines: string[],
  place: Placement,
  radius: number,
  font: number,
  margin = 0.15,
): Box {
  const w = Math.max(...lines.map((line) => line.length)) * font * 0.56;
  const { x, y, textAnchor } = labelOffset(place, radius, font, lines.length);
  const left = textAnchor === 'start' ? s.x + x : textAnchor === 'end' ? s.x + x - w : s.x + x - w / 2;
  const first = s.y + y;
  const last = first + (lines.length - 1) * font * LINE_HEIGHT;
  const pad = font * margin;
  const descent = DESCENDERS.test(lines[lines.length - 1] ?? '') ? 0.22 : 0.02;
  return { x0: left - pad, y0: first - font * 0.75 - pad, x1: left + w + pad, y1: last + font * descent + pad };
}

function overlap(a: Box, b: Box): number {
  const w = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0);
  const h = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
  return w > 0 && h > 0 ? w * h : 0;
}

export interface PlaceOptions {
  font?: number;
  /** The map's height; a name may not leave the map at the top or bottom either. */
  height?: number;
  /** Leave out a name that would overlap anything, rather than place it where it overlaps least. */
  dropOnCollision?: boolean;
  /** Named first and always, whatever it overlaps. */
  first?: string | null;
  /** Stations named before the rest, such as the ends of lines on a small map. */
  early?: ReadonlySet<string>;
}

/**
 * Placements for the stations `labelled` selects. Every station's mark (of radius
 * `radiusOf`) is an obstacle, labelled or not.
 */
export function placeLabels(
  stations: NetworkStation[],
  labelled: (s: NetworkStation) => boolean,
  radiusOf: (s: NetworkStation) => number,
  width: number,
  { font = LABEL_FONT, height = Infinity, dropOnCollision = false, first = null, early = new Set() }: PlaceOptions = {},
): Map<string, Placement> {
  // A mark is round: its obstacle is the square of the same area, so a name may pass close
  // to a bubble's curve without counting as touching its corner.
  const marks: Box[] = stations.map((s) => {
    const r = radiusOf(s) * 0.886 + 1;
    return { x0: s.x - r, y0: s.y - r, x1: s.x + r, y1: s.y + r };
  });
  const placed: Box[] = [];
  const out = new Map<string, Placement>();
  const rank = (s: NetworkStation) =>
    s.stationId === first ? 0 : early.has(s.stationId) ? 1 : s.stationId in PREFERRED ? 2 : 3;
  const order = stations
    .filter(labelled)
    .sort(
      (a, b) =>
        rank(a) - rank(b) ||
        b.supportedForecastCount - a.supportedForecastCount ||
        a.stationName.localeCompare(b.stationName),
    );
  for (const s of order) {
    const own = stations.indexOf(s);
    const r = radiusOf(s);
    const text = mapLabel(s);
    const preferred = PREFERRED[s.stationId];
    if (preferred && !dropOnCollision) {
      out.set(s.stationId, preferred);
      placed.push(labelBox(s, text, preferred, r, font));
      continue;
    }
    let best: { place: Placement; cost: number } | null = null;
    for (const place of preferred ? [preferred, ...ORDER.filter((p) => p !== preferred)] : ORDER) {
      const box = labelBox(s, text, place, r, font);
      const outside = box.x0 < 0 || box.x1 > width || box.y0 < 0 || box.y1 > height ? 1e6 : 0;
      const cost =
        outside +
        placed.reduce((sum, b) => sum + overlap(box, b), 0) +
        marks.reduce((sum, m, i) => sum + (i === own ? 0 : overlap(box, m)), 0);
      if (!best || cost < best.cost) best = { place, cost };
      if (cost === 0) break;
    }
    if (dropOnCollision && best && best.cost > 0 && s.stationId !== first) continue;
    const chosen = best?.place ?? 'right';
    out.set(s.stationId, chosen);
    placed.push(labelBox(s, text, chosen, r, font));
  }
  return out;
}
