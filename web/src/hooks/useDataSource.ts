import { useCallback } from 'react';
import { clientKey } from '../data/clientKey';
import { usePredictionEnvironment } from '../data/PredictionClientContext';
import { useRequest } from './useRequest';

/** Where the page's data comes from, as the client or the API itself states it. */
export type DataSource =
  | { kind: 'simulated' }
  | { kind: 'checking' }
  | { kind: 'replay'; asOf: string }
  | { kind: 'unavailable' };

/**
 * The simulated client needs no request. For the API, health says which mode it
 * serves; only a response the API labels as historical replay is reported as such.
 */
export function useDataSource(): { source: DataSource; retry: () => void } {
  const { client } = usePredictionEnvironment();
  const load = useCallback((signal: AbortSignal) => client.getHealth(signal), [client]);
  const { state, retry } = useRequest(client.source === 'api' ? `health:${clientKey(client)}` : null, load);
  if (client.source === 'simulated') return { source: { kind: 'simulated' }, retry };
  if (state.status === 'loading') return { source: { kind: 'checking' }, retry };
  if (state.status === 'error' || !state.data.replay) return { source: { kind: 'unavailable' }, retry };
  return { source: { kind: 'replay', asOf: state.data.replay.asOf }, retry };
}
