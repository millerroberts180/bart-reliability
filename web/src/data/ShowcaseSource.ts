import { assembleShowcase, decodeShowcaseMeta, type Showcase } from '../domain/showcase';
import { DecodeError } from './apiDecode';
import { PredictionClientError } from './PredictionClient';

/**
 * Where the curated showcase's files come from. Only the static build has one: the
 * files published in public/showcase/ beside the replay (docs/showcase_replay.md).
 */
export interface ShowcaseSource {
  load(signal?: AbortSignal): Promise<Showcase>;
}

const FILES = {
  meta: 'showcase.json',
  retrospective: 'retrospective.json',
  changes: 'largest-changes.json',
  network: 'network-map.json',
} as const;

/** Reads the showcase's four same-origin files under `root`, and checks they agree. */
export class StaticShowcaseSource implements ShowcaseSource {
  readonly root: string;
  private readonly fetchImpl: typeof fetch;

  constructor(root: string, { fetch: fetchImpl }: { fetch?: typeof fetch } = {}) {
    this.root = root.endsWith('/') ? root : `${root}/`;
    this.fetchImpl = fetchImpl ?? ((input, init) => globalThis.fetch(input, init));
  }

  async load(signal?: AbortSignal): Promise<Showcase> {
    const [meta, retrospective, changes, network] = await Promise.all(
      Object.values(FILES).map((file) => this.fetchJson(file, signal)),
    );
    try {
      return assembleShowcase(decodeShowcaseMeta(meta), { retrospective, changes, network });
    } catch (error) {
      if (error instanceof DecodeError) {
        throw new PredictionClientError('unavailable', `The showcase files are not in the expected form (${error.message}).`);
      }
      throw error;
    }
  }

  private async fetchJson(file: string, signal?: AbortSignal): Promise<unknown> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.root}${file}`, {
        ...(signal && { signal }),
        headers: { Accept: 'application/json' },
        credentials: 'omit',
      });
    } catch (error) {
      if (signal?.aborted || (error instanceof DOMException && error.name === 'AbortError')) throw error;
      throw new PredictionClientError('unavailable', 'The showcase could not be loaded.');
    }
    if (!response.ok) throw new PredictionClientError('unavailable', `The showcase file ${file} returned HTTP ${response.status}.`);
    try {
      return await response.json();
    } catch {
      throw new PredictionClientError('unavailable', `The showcase file ${file} is not valid JSON.`);
    }
  }
}
