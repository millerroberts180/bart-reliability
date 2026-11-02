// The network map's diverging scale: how far BART's published ETA moved (or was expected
// to move) at a station. Each step has a shape and words as well as a colour, so nothing
// depends on colour alone. A later ETA runs from amber to red as the revision grows, so a
// larger miss in BART's estimate looks worse; an earlier one deepens in teal. The two stay
// distinct for the common colour-vision deficiencies.

export type MapMode = 'forecast' | 'published';
export const MAP_MODES: readonly MapMode[] = ['forecast', 'published'];
export const MAP_MODE_LABELS: Record<MapMode, string> = {
  forecast: 'Model forecast at the time',
  published: 'What BART later published',
};

export type Tone = 'earlier-strong' | 'earlier' | 'little' | 'later' | 'later-strong' | 'none';
export type Shape = 'down' | 'circle' | 'up' | 'hollow';

/** Below this many seconds either way, a revision counts as little or no change. */
export const LITTLE_CHANGE_S = 15;
/** At or beyond a minute, a revision is drawn in the strong step (the model's large-revision threshold). */
export const STRONG_CHANGE_S = 60;

export function toneOf(seconds: number | null): Tone {
  if (seconds === null) return 'none';
  if (Math.abs(seconds) < LITTLE_CHANGE_S) return 'little';
  if (seconds > 0) return seconds >= STRONG_CHANGE_S ? 'later-strong' : 'later';
  return seconds <= -STRONG_CHANGE_S ? 'earlier-strong' : 'earlier';
}

export const TONE_SHAPE: Record<Tone, Shape> = {
  'earlier-strong': 'down',
  earlier: 'down',
  little: 'circle',
  later: 'up',
  'later-strong': 'up',
  none: 'hollow',
};

/** Legend order, earlier to later, then no forecast. */
export const TONES: readonly Tone[] = ['earlier-strong', 'earlier', 'little', 'later', 'later-strong', 'none'];

export const TONE_LABELS: Record<Tone, string> = {
  'earlier-strong': 'ETA moved earlier, 1 min or more',
  earlier: 'ETA moved earlier, 15 to 59 sec',
  little: 'Little or no change, under 15 sec',
  later: 'ETA moved later, 15 to 59 sec',
  'later-strong': 'ETA moved later, 1 min or more',
  none: 'No supported forecast at this replay moment',
};

/** In forecast mode the same steps describe what the model expected. */
export function toneLabel(tone: Tone, mode: MapMode): string {
  if (mode === 'published' || tone === 'none' || tone === 'little') return TONE_LABELS[tone];
  return TONE_LABELS[tone].replace('ETA moved', 'ETA expected to move');
}

// Bubbles: area grows with the size of the revision, so 20 s and 90 s look different.
export function bubbleRadius(seconds: number): number {
  return 3 + 2.15 * Math.sqrt(Math.min(Math.abs(seconds), 240));
}

// Light to strong, evenly spaced over 15 s to 90 s, as --map-later, --map-later-mid,
// --map-later-strong, --map-earlier and --map-earlier-strong in tokens.css.
const RAMPS = {
  later: ['#f6d37c', '#e8892f', '#b8231c'],
  earlier: ['#bfe6dc', '#0a7f70'],
} as const;

function mix(a: string, b: string, t: number): string {
  const channel = (hex: string, i: number) => parseInt(hex.slice(1 + 2 * i, 3 + 2 * i), 16);
  return `#${[0, 1, 2]
    .map((i) => Math.round(channel(a, i) + (channel(b, i) - channel(a, i)) * t).toString(16).padStart(2, '0'))
    .join('')}`;
}

/** A station's mark radius: no forecast, little change, or a bubble sized by the revision. */
export function markRadius(value: number | null): number {
  if (value === null) return 5;
  if (Math.abs(value) < LITTLE_CHANGE_S) return 6;
  return bubbleRadius(value);
}

/** A colour that deepens with the size of the revision, from 15 s to 90 s and beyond. */
export function bubbleFill(seconds: number): string {
  const ramp: readonly string[] = seconds > 0 ? RAMPS.later : RAMPS.earlier;
  const t = Math.min(1, Math.max(0, (Math.abs(seconds) - LITTLE_CHANGE_S) / (90 - LITTLE_CHANGE_S)));
  const at = t * (ramp.length - 1);
  const i = Math.min(Math.floor(at), ramp.length - 2);
  return mix(ramp[i] ?? '#000000', ramp[i + 1] ?? '#000000', at - i);
}

// From these sizes on, a light chevron contrasts more with the bubble than the hue's dark
// outline colour does (later at 62 s: 3.2:1 each, the light one rising; teal stays lighter
// for longer).
const LIGHT_CHEVRON_FROM = { later: 62, earlier: 68 } as const;

/** Dark fills take a light chevron; light fills a dark one. */
export function chevronOnDark(seconds: number): boolean {
  return Math.abs(seconds) >= LIGHT_CHEVRON_FROM[seconds > 0 ? 'later' : 'earlier'];
}
