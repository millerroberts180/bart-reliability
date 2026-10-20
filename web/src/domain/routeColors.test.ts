import { describe, expect, it } from 'vitest';
import { routeColor, UNKNOWN_ROUTE_COLOR } from './routeColors';

describe('routeColor', () => {
  it('uses BART’s GTFS route colours by line name', () => {
    expect(routeColor('Yellow line')).toBe('#ffff33');
    expect(routeColor('Orange line')).toBe('#ff9933');
    expect(routeColor('Red line')).toBe('#ff0000');
    expect(routeColor('Green line')).toBe('#339933');
    expect(routeColor('Blue line')).toBe('#0099cc');
  });

  it('falls back to a neutral colour for unknown lines', () => {
    expect(routeColor('Beige line')).toBe(UNKNOWN_ROUTE_COLOR);
  });
});
