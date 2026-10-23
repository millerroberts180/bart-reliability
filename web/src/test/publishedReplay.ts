// Serves the published static replay (web/public/replay) to tests, as GitHub Pages serves it
// under the site's base path. Files load only when requested, like the real site.

const FILES = import.meta.glob<string>('/public/replay/**/*.json', { query: '?raw', import: 'default' });

/** The Pages build's base path plus the replay's directory. */
export const PUBLISHED_ROOT = '/bart-reliability/replay/';

export type HostResponse = { status?: number; body: string } | ((init?: RequestInit) => Promise<Response>);

export interface PublishedReplayHost {
  fetch: typeof fetch;
  /** Every path requested so far, in order, relative to the replay root. */
  requests: string[];
  /** Replace a file (by its path relative to the root) with another response. */
  respond: (file: string, response: HostResponse) => void;
  /** Read a published file (path relative to the root), as JSON. */
  read: <T = unknown>(file: string) => Promise<T>;
}

export function publishedFiles(): string[] {
  return Object.keys(FILES).map((key) => key.slice('/public/replay/'.length));
}

export function createPublishedReplayHost(root = PUBLISHED_ROOT): PublishedReplayHost {
  const overrides = new Map<string, HostResponse>();
  const requests: string[] = [];

  const read = async <T>(file: string): Promise<T> => {
    const load = FILES[`/public/replay/${file}`];
    if (!load) throw new Error(`No published file ${file}`);
    return JSON.parse(await load()) as T;
  };

  const fakeFetch: typeof fetch = async (input, init) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'https://site.test');
    if (url.origin !== 'https://site.test') throw new TypeError(`Cross-origin request to ${url.href}`);
    const file = url.pathname.startsWith(root) ? url.pathname.slice(root.length) : url.pathname;
    requests.push(file);
    if (init?.signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError');

    const override = overrides.get(file);
    if (typeof override === 'function') return override(init);
    if (override) return new Response(override.body, { status: override.status ?? 200 });
    const load = url.pathname.startsWith(root) ? FILES[`/public/replay/${file}`] : undefined;
    if (!load) return new Response('<!doctype html><title>Page not found</title>', { status: 404, headers: { 'Content-Type': 'text/html' } });
    return new Response(await load(), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };

  return { fetch: fakeFetch, requests, respond: (file, response) => overrides.set(file, response), read };
}
