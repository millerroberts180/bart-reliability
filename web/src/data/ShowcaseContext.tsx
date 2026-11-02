import { createContext, useCallback, useContext, type ReactNode } from 'react';
import type { Showcase } from '../domain/showcase';
import { useRequest } from '../hooks/useRequest';
import { clientKey } from './clientKey';
import type { ShowcaseSource } from './ShowcaseSource';

export type ShowcaseState =
  | { status: 'none' }
  | { status: 'loading' }
  | { status: 'error'; message: string; retry: () => void }
  | { status: 'ready'; showcase: Showcase };

const ShowcaseContext = createContext<ShowcaseState>({ status: 'none' });

/**
 * Loads the curated showcase once for the whole page. Builds without one (the simulated
 * and local-API development modes) get { status: 'none' }, and the views that need it say so.
 */
export function ShowcaseProvider({ source, children }: { source: ShowcaseSource | null; children: ReactNode }) {
  const load = useCallback((signal: AbortSignal) => (source ? source.load(signal) : Promise.reject()), [source]);
  const { state, retry } = useRequest(source ? `showcase:${clientKey(source)}` : null, load);
  const value: ShowcaseState = !source
    ? { status: 'none' }
    : state.status === 'loading'
      ? { status: 'loading' }
      : state.status === 'error'
        ? { status: 'error', message: state.error.message, retry }
        : { status: 'ready', showcase: state.data };
  return <ShowcaseContext value={value}>{children}</ShowcaseContext>;
}

export function useShowcase(): ShowcaseState {
  return useContext(ShowcaseContext);
}
