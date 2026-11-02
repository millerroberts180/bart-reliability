// Serves the published showcase files (web/public/showcase) to tests, as GitHub Pages
// serves them beside the replay under the site's base path.

const FILES = import.meta.glob<string>('/public/showcase/*.json', { query: '?raw', import: 'default' });

export const SHOWCASE_ROOT = '/bart-reliability/showcase/';

export function publishedShowcaseFiles(): string[] {
  return Object.keys(FILES).map((key) => key.slice('/public/showcase/'.length));
}

export async function readShowcaseFile<T = unknown>(file: string): Promise<T> {
  const load = FILES[`/public/showcase/${file}`];
  if (!load) throw new Error(`No published showcase file ${file}`);
  return JSON.parse(await load()) as T;
}

/** A same-origin fetch for the showcase files; anything else is a 404 page. */
export function showcaseFetch(requests: string[] = [], root = SHOWCASE_ROOT): typeof fetch {
  return async (input, init) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'https://site.test');
    if (url.origin !== 'https://site.test') throw new TypeError(`Cross-origin request to ${url.href}`);
    if (init?.signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError');
    const file = url.pathname.startsWith(root) ? url.pathname.slice(root.length) : '';
    requests.push(file);
    const load = FILES[`/public/showcase/${file}`];
    if (!load) return new Response('<!doctype html><title>Page not found</title>', { status: 404 });
    return new Response(await load(), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
}
