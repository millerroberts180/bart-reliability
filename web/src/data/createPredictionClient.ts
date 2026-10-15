import { HttpPredictionClient } from './HttpPredictionClient';
import { MockPredictionClient, type MockHistoryScenario, type MockScenario } from './MockPredictionClient';
import type { PredictionClient } from './PredictionClient';

export type DataMode = 'mock' | 'http';

/** Reads VITE_DATA_MODE; anything unrecognised falls back to simulated data. */
export function resolveDataMode(value: string | undefined): DataMode {
  return value === 'http' ? 'http' : 'mock';
}

export interface ClientOptions {
  mode: DataMode;
  apiBaseUrl?: string;
  scenario?: MockScenario;
  historyScenario?: MockHistoryScenario;
  now?: () => Date;
  latencyMs?: number;
}

export function createPredictionClient({
  mode,
  apiBaseUrl = '',
  scenario,
  historyScenario,
  now,
  latencyMs,
}: ClientOptions): PredictionClient {
  if (mode === 'http') return new HttpPredictionClient(apiBaseUrl);
  return new MockPredictionClient({
    ...(scenario && { scenario }),
    ...(historyScenario && { historyScenario }),
    ...(now && { now }),
    ...(latencyMs !== undefined && { latencyMs }),
  });
}
