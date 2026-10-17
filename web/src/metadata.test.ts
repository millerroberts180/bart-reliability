// The page's metadata describes the historical-replay site (web/index.html). A canonical
// URL and a social image are deployment tasks (docs/website_architecture.md), so neither
// is invented here.
import { describe, expect, it } from 'vitest';
import html from '../index.html?raw';

const head = new DOMParser().parseFromString(html, 'text/html').head;
const meta = (selector: string) => head.querySelector(selector)?.getAttribute('content') ?? null;

const DESCRIPTION =
  'A historical replay of recorded BART data, with a model of how BART revises a train’s published arrival estimate before it arrives. Not live, and not a prediction of physical arrival.';
const TITLE = 'ETA Reliability · How stable are BART’s published arrival estimates?';

describe('page metadata', () => {
  it('describes a historical replay and a model of ETA revisions, never simulated or live data', () => {
    const description = meta('meta[name="description"]');
    expect(description).toBe(DESCRIPTION);
    expect(description).not.toMatch(/simulat/i);
    expect(description?.replace(/Not live/, '')).not.toMatch(/\blive\b/i);
    expect(head.querySelector('title')?.textContent).toBe(TITLE);
  });

  it('gives Open Graph and Twitter the same title and description', () => {
    expect(meta('meta[property="og:type"]')).toBe('website');
    expect(meta('meta[property="og:site_name"]')).toBe('ETA Reliability');
    expect(meta('meta[property="og:title"]')).toBe(TITLE);
    expect(meta('meta[property="og:description"]')).toBe(DESCRIPTION);
    expect(meta('meta[name="twitter:card"]')).toBe('summary');
    expect(meta('meta[name="twitter:title"]')).toBe(TITLE);
    expect(meta('meta[name="twitter:description"]')).toBe(DESCRIPTION);
  });

  it('invents no production URL or social image', () => {
    expect(head.querySelector('link[rel="canonical"]')).toBeNull();
    expect(head.querySelector('meta[property="og:url"]')).toBeNull();
    expect(head.querySelector('meta[property="og:image"], meta[name="twitter:image"]')).toBeNull();
  });
});
