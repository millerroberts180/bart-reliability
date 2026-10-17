import { useCallback, useEffect, useState } from 'react';

export type RequestState<T> =
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: Error };

/**
 * Runs `load` whenever `key` changes (or on retry), cancelling the previous
 * request so a slow response can never overwrite a newer selection.
 * Pass key = null to skip loading.
 */
export function useRequest<T>(
  key: string | null,
  load: (signal: AbortSignal) => Promise<T>,
): { state: RequestState<T>; retry: () => void } {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ token: string; state: RequestState<T> } | null>(null);
  const token = `${key ?? ''}#${attempt}`;

  useEffect(() => {
    if (key === null) return;
    const controller = new AbortController();
    load(controller.signal).then(
      (data) => setResult({ token, state: { status: 'success', data } }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setResult({ token, state: { status: 'error', error: error instanceof Error ? error : new Error(String(error)) } });
      },
    );
    return () => controller.abort();
    // `load` is expected to change only with `key`; keying on it would refetch every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  // Any result for an older key or attempt counts as still loading.
  const state: RequestState<T> = result && result.token === token ? result.state : { status: 'loading' };
  return { state, retry };
}
