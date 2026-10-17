import recording from '../data/fixtures/apiReplay.json';

/** Responses recorded from the local API (scratch recorder, no network); keyed by path and query. */
export const API_RECORDING = recording as { _recorded: { asOf: string }; responses: Record<string, unknown> };

export const API_BASE = 'http://127.0.0.1:8000';

export interface FakeApi {
  fetch: typeof fetch;
  /** Every path and query requested so far, in order, with the base URL removed. */
  requests: string[];
  /** Replace or add a response for a path; a function receives the request init. */
  respond: (path: string, response: FakeResponse) => void;
}

export type FakeResponse = { status?: number; body: unknown } | ((init?: RequestInit) => Promise<Response>);

/**
 * A fetch that serves the recorded API responses. Unknown paths answer 404 in the
 * API's error shape, and an aborted signal rejects as the browser's fetch does.
 */
export function createFakeApi(): FakeApi {
  const overrides = new Map<string, FakeResponse>();
  const requests: string[] = [];

  const fakeFetch: typeof fetch = async (input, init) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url);
    const path = decodeURIComponent(url.pathname) + url.search;
    requests.push(path);
    if (init?.signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError');

    const override = overrides.get(path);
    if (typeof override === 'function') return override(init);
    if (override) return json(override.body, override.status ?? 200);
    if (path in API_RECORDING.responses) return json(API_RECORDING.responses[path], 200);
    return json(
      { error: { code: 'not_found', clientCode: 'not_found', message: `No route for ${path}.`, dataMode: 'historical_replay' } },
      404,
    );
  };

  return { fetch: fakeFetch, requests, respond: (path, response) => overrides.set(path, response) };
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}
