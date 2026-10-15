/**
 * Route colours for the line cue, from BART's static GTFS routes.txt (route_color).
 * Presentation only: the prediction contract carries the rider-facing line name, and
 * the colour is looked up from it. The cue always sits beside the line name in text
 * and is drawn with a dark casing, so it never carries meaning by colour alone and
 * stays visible on the light background (pale yellow included). It never encodes
 * forecast quality or stability.
 */
const ROUTE_COLORS: Record<string, string> = {
  yellow: '#ffff33',
  orange: '#ff9933',
  red: '#ff0000',
  green: '#339933',
  blue: '#0099cc',
  grey: '#b0bec7',
};

/** Neutral fallback for a line without a known colour. */
export const UNKNOWN_ROUTE_COLOR = '#8a9095';

/** "Yellow line" → "#ffff33"; unknown lines get the neutral fallback. */
export function routeColor(lineName: string): string {
  const key = lineName.trim().split(/\s+/)[0]?.toLowerCase() ?? '';
  return ROUTE_COLORS[key] ?? UNKNOWN_ROUTE_COLOR;
}
