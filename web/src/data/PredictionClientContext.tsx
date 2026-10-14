import { createContext, useContext, useMemo, type ReactNode } from 'react';
import type { PredictionClient } from './PredictionClient';

interface PredictionEnvironment {
  client: PredictionClient;
  /** Clock for freshness checks; injectable so tests are deterministic. */
  now: () => Date;
}

const PredictionClientContext = createContext<PredictionEnvironment | null>(null);

const systemClock = () => new Date();

export function PredictionClientProvider({
  client,
  now = systemClock,
  children,
}: {
  client: PredictionClient;
  now?: () => Date;
  children: ReactNode;
}) {
  const value = useMemo(() => ({ client, now }), [client, now]);
  return <PredictionClientContext value={value}>{children}</PredictionClientContext>;
}

export function usePredictionEnvironment(): PredictionEnvironment {
  const environment = useContext(PredictionClientContext);
  if (!environment) throw new Error('usePredictionEnvironment must be used inside PredictionClientProvider');
  return environment;
}
